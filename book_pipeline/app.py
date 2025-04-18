import os
import threading
import time
from flask import Flask, render_template, send_from_directory, jsonify, request
# Import both pipeline functions
from main import run_ebook_generation_pipeline, run_podcast_pipeline
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
    "is_generating": False,
    "status": "idle", # idle, running, completed, error
    "message": "Ready to generate Podcast Series.",
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

# --- Podcast Routes ---
@app.route('/generate-podcast', methods=['POST'])
def start_podcast_generation_api():
    """API endpoint to trigger the podcast generation."""
    global podcast_generation_state
    with generation_lock:
        if podcast_generation_state["is_generating"]:
            return jsonify({"error": "Podcast generation already in progress."}), 409

        podcast_generation_state = {
            "is_generating": True, "status": "running",
            "message": "Podcast generation request received...",
            "pdf_filenames": [], "error": None
        }
        print('Received start podcast generation request via API')
        thread = threading.Thread(target=run_podcast_pipeline_wrapper)
        thread.start()
        return jsonify({"message": "Podcast generation started. Poll /status-podcast for updates."}), 202

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

def run_podcast_pipeline_wrapper():
    """Wrapper to run the podcast pipeline and update the global status."""
    global podcast_generation_state
    pipeline_result = None
    pipeline_exception = None
    try:
        pipeline_result = run_podcast_pipeline()
    except Exception as e:
        print(f"Critical error during podcast pipeline execution: {e}")
        pipeline_exception = e
    finally:
        with generation_lock:
            if pipeline_exception:
                podcast_generation_state.update({
                    "status": "error", "message": f"Critical pipeline error: {pipeline_exception}",
                    "error": str(pipeline_exception), "pdf_filenames": []
                })
            elif pipeline_result:
                 podcast_generation_state.update({
                    "status": pipeline_result.get("status", "error"),
                    "message": pipeline_result.get("message", "Unknown completion state."),
                    "pdf_filenames": pipeline_result.get("pdf_filenames", []),
                    "error": pipeline_result.get("message") if pipeline_result.get("status") == "error" else None
                 })
            else: # Fallback
                 podcast_generation_state.update({
                    "status": "error", "message": "Pipeline finished with unknown state.",
                    "error": "Unknown state.", "pdf_filenames": []
                 })
            podcast_generation_state["is_generating"] = False
        print(f"Podcast background task finished with status: {podcast_generation_state['status']}")


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Unified Flask API server (polling)...")
    # Ensure podcast directory exists (ebook saves to root, chapters dir handled in main)
    os.makedirs(config.PODCAST_DIR, exist_ok=True)
    # Use Gunicorn in production via Procfile
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False) # Use standard port 5000
