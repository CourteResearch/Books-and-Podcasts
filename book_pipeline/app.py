import os
import threading
import time
from flask import Flask, render_template, send_from_directory, jsonify, request
# Import the specific pipeline functions from the agents module
from agents.ebook_agent import run_ebook_generation_pipeline
# Import the refactored podcast agent functions
from agents.podcast_agent import generate_podcast_topic, run_podcast_pipeline
import config # Import config to access directory names

# --- Flask App Setup ---
app = Flask(__name__, template_folder='frontend', static_folder='frontend', static_url_path='/frontend')

# --- Global State for Polling (Separate for each agent) ---
ebook_generation_state = {
    "is_generating": False,
    "status": "idle", # idle, running, completed, error
    "message": "Ready to generate Ebook.",
    "pdf_filename": None,
    "error": None
}
podcast_generation_state = {
    "is_generating": False, # True if *any* part of the process is running
    "status": "idle", # idle, generating_topic, awaiting_approval, generating_podcast, completed, error
    "message": "Ready to generate Podcast Series.",
    "proposed_topic": None, # Store the topic awaiting approval
    "pdf_filenames": [], # Expecting multiple PDFs for podcasts
    "error": None
}
# Use separate locks if high contention is expected, or one global lock for simplicity
generation_lock = threading.Lock()

# --- Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

# Flask handles static files automatically

# --- API Routes ---

# --- Ebook Routes ---
@app.route('/generate-ebook', methods=['POST'])
def start_ebook_generation_api():
    """API endpoint to trigger the ebook generation."""
    global ebook_generation_state
    with generation_lock:
        if ebook_generation_state["is_generating"]:
            return jsonify({"error": "Ebook generation already in progress."}), 409

        ebook_generation_state = {
            "is_generating": True, "status": "running",
            "message": "Ebook generation request received...",
            "pdf_filename": None, "error": None
        }
        print('Received start ebook generation request via API')
        thread = threading.Thread(target=run_ebook_pipeline_wrapper)
        thread.start()
        return jsonify({"message": "Ebook generation started. Poll /status-ebook for updates."}), 202

@app.route('/status-ebook')
def get_ebook_status_api():
    """API endpoint for the frontend to poll ebook generation status."""
    with generation_lock:
        return jsonify(ebook_generation_state.copy())

# --- Podcast Routes (Refactored for Approval Flow) ---

@app.route('/generate-podcast-topic', methods=['POST'])
def start_podcast_topic_generation_api():
    """API endpoint to trigger the podcast *topic* generation."""
    global podcast_generation_state
    with generation_lock:
        # Allow starting topic generation even if previous run completed/errored, but not if currently active
        if podcast_generation_state["is_generating"] and podcast_generation_state["status"] not in ["completed", "error", "idle"]:
             return jsonify({"error": f"Podcast process already active ({podcast_generation_state['status']})."}), 409

        # Reset state for new topic generation
        podcast_generation_state = {
            "is_generating": True,
            "status": "generating_topic",
            "message": "Generating potential podcast topic...",
            "proposed_topic": None,
            "pdf_filenames": [],
            "error": None
        }
        print('Received start podcast *topic* generation request via API')
        thread = threading.Thread(target=run_topic_generation_wrapper)
        thread.start()
        return jsonify({"message": "Podcast topic generation started. Poll /status-podcast for updates."}), 202


@app.route('/generate-podcast', methods=['POST'])
def start_podcast_content_generation_api():
    """API endpoint to trigger the podcast *content* generation *after* topic approval."""
    global podcast_generation_state
    data = request.get_json()
    approved_topic = data.get('topic')

    if not approved_topic:
        return jsonify({"error": "Missing 'topic' in request body."}), 400

    with generation_lock:
        # Ensure we are in the correct state to proceed
        if podcast_generation_state["status"] != "awaiting_approval":
            return jsonify({"error": f"Cannot start content generation. Current status: {podcast_generation_state['status']}."}), 409
        if podcast_generation_state["proposed_topic"] != approved_topic:
             # This check prevents starting with a topic different from the one proposed/approved
             return jsonify({"error": f"Approved topic '{approved_topic}' does not match proposed topic '{podcast_generation_state['proposed_topic']}'."}), 400

        # Update state to reflect content generation starting
        podcast_generation_state.update({
            "is_generating": True,
            "status": "generating_podcast",
            "message": f"Approved topic '{approved_topic}'. Starting podcast content generation...",
            "pdf_filenames": [], # Reset filenames for this run
            "error": None
        })
        print(f"Received start podcast *content* generation request via API for topic: {approved_topic}")
        # Pass the approved topic to the wrapper
        thread = threading.Thread(target=run_podcast_pipeline_wrapper, args=(approved_topic,))
        thread.start()
        return jsonify({"message": "Podcast content generation started. Poll /status-podcast for updates."}), 202


@app.route('/status-podcast')
def get_podcast_status_api():
    """API endpoint for the frontend to poll podcast generation status."""
    with generation_lock:
        return jsonify(podcast_generation_state.copy())


# --- Shared Download Route ---
@app.route('/download/<path:filename>')
def download_pdf_api(filename):
    """API endpoint to download a generated PDF (ebook or podcast episode)."""
    if '..' in filename or filename.startswith('/'):
        return jsonify({"error": "Invalid filename"}), 400

    # Determine if it's likely an ebook or podcast based on naming convention (or check existence)
    ebook_path = os.path.join('.', filename) # Ebooks saved in root
    podcast_path = os.path.join('.', config.PODCAST_DIR, filename) # Podcasts saved in subdir

    if os.path.exists(ebook_path) and not os.path.isdir(ebook_path):
         print(f"Attempting to serve Ebook PDF: {filename}")
         try:
             return send_from_directory(directory='.', path=filename, as_attachment=True)
         except FileNotFoundError:
             pass # Try podcast directory next
    elif os.path.exists(podcast_path):
        print(f"Attempting to serve Podcast PDF: {filename} from {config.PODCAST_DIR}")
        try:
            return send_from_directory(directory=config.PODCAST_DIR, path=filename, as_attachment=True)
        except FileNotFoundError:
             pass # File not found

    # If not found in either location
    print(f"Error: PDF not found - {filename}")
    return jsonify({"error": "File not found"}), 404


# --- Wrappers for Background Tasks ---
def run_ebook_pipeline_wrapper():
    """Wrapper to run the ebook pipeline and update the global status."""
    global ebook_generation_state
    pipeline_result = None
    pipeline_exception = None
    try:
        pipeline_result = run_ebook_generation_pipeline()
    except Exception as e:
        print(f"Critical error during ebook pipeline execution: {e}")
        pipeline_exception = e
    finally:
        with generation_lock:
            if pipeline_exception:
                ebook_generation_state.update({
                    "status": "error", "message": f"Critical pipeline error: {pipeline_exception}",
                    "error": str(pipeline_exception), "pdf_filename": None
                })
            elif pipeline_result:
                 ebook_generation_state.update({
                    "status": pipeline_result.get("status", "error"),
                    "message": pipeline_result.get("message", "Unknown completion state."),
                    "pdf_filename": pipeline_result.get("pdf_filename"),
                    "error": pipeline_result.get("message") if pipeline_result.get("status") == "error" else None
                 })
            else: # Fallback
                 ebook_generation_state.update({
                    "status": "error", "message": "Pipeline finished with unknown state.",
                    "error": "Unknown state.", "pdf_filename": None
                 })
            ebook_generation_state["is_generating"] = False
        print(f"Ebook background task finished with status: {ebook_generation_state['status']}")

# --- Wrappers for Background Tasks ---
def run_ebook_pipeline_wrapper():
    """Wrapper to run the ebook pipeline and update the global status."""
    global ebook_generation_state
    pipeline_result = None
    pipeline_exception = None
    try:
        pipeline_result = run_ebook_generation_pipeline()
    except Exception as e:
        print(f"Critical error during ebook pipeline execution: {e}")
        pipeline_exception = e
    finally:
        with generation_lock:
            if pipeline_exception:
                ebook_generation_state.update({
                    "status": "error", "message": f"Critical pipeline error: {pipeline_exception}",
                    "error": str(pipeline_exception), "pdf_filename": None
                })
            elif pipeline_result:
                 ebook_generation_state.update({
                    "status": pipeline_result.get("status", "error"),
                    "message": pipeline_result.get("message", "Unknown completion state."),
                    "pdf_filename": pipeline_result.get("pdf_filename"),
                    "error": pipeline_result.get("message") if pipeline_result.get("status") == "error" else None
                 })
            else: # Fallback
                 ebook_generation_state.update({
                    "status": "error", "message": "Pipeline finished with unknown state.",
                    "error": "Unknown state.", "pdf_filename": None
                 })
            ebook_generation_state["is_generating"] = False
        print(f"Ebook background task finished with status: {ebook_generation_state['status']}")


# --- New Wrapper for Topic Generation ---
def run_topic_generation_wrapper():
    """Wrapper to run only the topic generation part."""
    global podcast_generation_state
    proposed_topic = None
    topic_exception = None
    try:
        proposed_topic = generate_podcast_topic() # Call the new agent function
    except Exception as e:
        print(f"Critical error during podcast topic generation: {e}")
        topic_exception = e
    finally:
        with generation_lock:
            if topic_exception:
                podcast_generation_state.update({
                    "status": "error", "message": f"Failed to generate topic: {topic_exception}",
                    "error": str(topic_exception), "proposed_topic": None, "is_generating": False
                })
            elif proposed_topic:
                 podcast_generation_state.update({
                    "status": "awaiting_approval", # Move to approval state
                    "message": f"Proposed Topic: '{proposed_topic}'. Please approve or request another.",
                    "proposed_topic": proposed_topic,
                    "error": None,
                    "is_generating": False # Topic generation is done, waiting for user
                 })
            else: # Fallback if function returns None without error
                 podcast_generation_state.update({
                    "status": "error", "message": "Topic generation finished without a topic.",
                    "error": "Unknown topic generation state.", "proposed_topic": None, "is_generating": False
                 })
        print(f"Podcast topic generation finished with status: {podcast_generation_state['status']}")


# --- Modified Wrapper for Content Generation ---
def run_podcast_pipeline_wrapper(approved_topic):
    """Wrapper to run the podcast *content* pipeline and update the global status."""
    global podcast_generation_state
    pipeline_result = None
    pipeline_exception = None
    try:
        # Pass the approved topic to the pipeline function
        pipeline_result = run_podcast_pipeline(approved_topic)
    except Exception as e:
        print(f"Critical error during podcast *content* pipeline execution: {e}")
        pipeline_exception = e
    finally:
        with generation_lock:
            if pipeline_exception:
                # Update state based on content pipeline result
                podcast_generation_state.update({
                    "status": "error", "message": f"Critical content pipeline error: {pipeline_exception}",
                    "error": str(pipeline_exception), "pdf_filenames": [] # Keep any partial results if desired
                })
            elif pipeline_result:
                 # Use 'completed' status from the pipeline result if successful
                 final_status = "completed" if pipeline_result.get("status") == "success" else "error"
                 podcast_generation_state.update({
                    "status": final_status,
                    "message": pipeline_result.get("message", "Content generation finished."),
                    "pdf_filenames": pipeline_result.get("pdf_filenames", []),
                    "error": pipeline_result.get("message") if final_status == "error" else None
                 })
            else: # Fallback
                 podcast_generation_state.update({
                    "status": "error", "message": "Content pipeline finished with unknown state.",
                    "error": "Unknown state.", "pdf_filenames": []
                 })
            # Mark generation as fully stopped only after content pipeline finishes or errors out
            podcast_generation_state["is_generating"] = False
        print(f"Podcast *content* background task finished with status: {podcast_generation_state['status']}")


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Unified Flask API server (polling)...")
    # Ensure podcast directory exists (ebook saves to root, chapters dir handled in main)
    os.makedirs(config.PODCAST_DIR, exist_ok=True)
    # Use Gunicorn in production via Procfile
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False) # Use standard port 5000
