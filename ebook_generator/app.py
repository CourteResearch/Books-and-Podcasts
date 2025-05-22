import os
import os
import sys
import threading
import time
import datetime
import logging # Import logging
from flask import Flask, render_template, send_from_directory, jsonify, request

# --- Adjust sys.path to find the sibling pipeline ---
# Get the directory containing the current script (book_pipeline)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (Books-and-Podcasts)
parent_dir = os.path.dirname(current_dir)
# Add the parent directory to sys.path to allow importing from trending_podcast_pipeline
sys.path.insert(0, parent_dir)

# --- Import components from both pipelines ---
# Book/Tech Podcast Pipeline
# Import agent functions AND necessary helpers like configure_gemini
from book_pipeline.agents.ebook_agent import run_ebook_generation_pipeline, ebook_conceptualize_idea # Import concept func too
from book_pipeline.agents.podcast_agent import generate_podcast_topic, run_podcast_pipeline
from book_pipeline.main import configure_gemini
import book_pipeline.config as book_config

# --- Check Trending Pipeline Availability (Needed for UI and Download Route) ---
# We still need to know if it's available, even if routes are separate.
try:
    # Try importing something minimal from the trending pipeline to check availability
    from trending_podcast_pipeline import config as trending_config_check
    TRENDING_PIPELINE_AVAILABLE = True
    # We don't need the actual agent/fetcher imports here anymore
except ImportError as e:
    print(f"Warning (app.py): Could not import trending_podcast_pipeline components: {e}")
    print("Trending podcast functionality will be disabled.")
    TRENDING_PIPELINE_AVAILABLE = False

# --- Import the Blueprint ---
# Import after checking availability to avoid potential import errors if the check fails
if TRENDING_PIPELINE_AVAILABLE:
    try:
        from .trending_routes import trending_bp
    except ImportError as bp_e:
        print(f"ERROR: Failed to import trending_routes blueprint even though pipeline seemed available: {bp_e}")
        TRENDING_PIPELINE_AVAILABLE = False # Mark as unavailable if blueprint import fails


# --- Flask App Setup ---
app = Flask(__name__, template_folder='frontend', static_folder='frontend', static_url_path='/frontend')

# --- Register Blueprints ---
if TRENDING_PIPELINE_AVAILABLE:
    app.register_blueprint(trending_bp)
    print("Registered trending_routes blueprint.")
# Register other blueprints here if created later (e.g., for ebook, tech podcast)


# --- Global State for Polling (Ebook & Tech Podcast ONLY) ---
# Trending state is now managed within trending_routes.py
ebook_generation_state = {
    "is_generating": False, # True if any part is active
    "status": "idle", # idle, generating_concept, awaiting_approval, running, completed, error
    "message": "Ready to generate Ebook concept.",
    "proposed_title": None,
    "proposed_premise": None,
    "pdf_filename": None,
    "error": None
}
podcast_generation_state = {
    "is_generating": False, # True if *any* part of the process is running
    "status": "idle", # idle, generating_topic, awaiting_approval, generating_podcast, completed, error
    "message": "Ready to generate Podcast Series.",
    "proposed_topic": None, # Store the topic awaiting approval
    "pdf_filenames": [], # Expecting multiple PDFs for tech podcasts
    "error": None
}


# Use separate locks if high contention is expected, or one global lock for simplicity
# Keep the main lock for ebook/tech podcast state
generation_lock = threading.Lock()


# --- Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    """Serves the main HTML page."""
    # Pass availability flag to template if needed (optional)
    return render_template('index.html', trending_available=TRENDING_PIPELINE_AVAILABLE)

# Flask handles static files automatically from the 'static_folder'

# --- API Routes ---

# --- Ebook Routes (Refactored for Approval Flow) ---

@app.route('/generate-ebook-concept', methods=['POST'])
def start_ebook_concept_generation_api():
    """API endpoint to trigger the ebook *concept* generation."""
    global ebook_generation_state
    with generation_lock:
        # Allow starting concept generation only if not actively generating concept or running main pipeline
        if ebook_generation_state["status"] in ["generating_concept", "running"]:
             return jsonify({"error": f"Ebook process already active ({ebook_generation_state['status']}). Cannot start new concept generation."}), 409

        # Reset state for new concept generation
        ebook_generation_state = {
            "is_generating": True,
            "status": "generating_concept",
            "message": "Generating potential ebook concept...",
            "proposed_title": None,
            "proposed_premise": None,
            "pdf_filename": None,
            "error": None
        }
        print('Received start ebook *concept* generation request via API')
        thread = threading.Thread(target=run_ebook_concept_wrapper) # Use new wrapper
        thread.start()
        return jsonify({"message": "Ebook concept generation started. Poll /status-ebook for updates."}), 202

@app.route('/generate-ebook', methods=['POST'])
def start_ebook_content_generation_api():
    """API endpoint to trigger the ebook *content* generation *after* concept approval."""
    global ebook_generation_state
    data = request.get_json()
    approved_title = data.get('title')
    approved_premise = data.get('premise')

    if not approved_title or not approved_premise:
        return jsonify({"error": "Missing 'title' or 'premise' in request body."}), 400

    with generation_lock:
        # Ensure we are in the correct state to proceed
        if ebook_generation_state["status"] != "awaiting_approval":
            return jsonify({"error": f"Cannot start content generation. Current status: {ebook_generation_state['status']}."}), 409
        # Optional: Check if approved matches proposed (might be less strict than podcast)
        # if ebook_generation_state["proposed_title"] != approved_title or ebook_generation_state["proposed_premise"] != approved_premise:
        #     return jsonify({"error": "Approved concept does not match proposed concept."}), 400

        # Update state to reflect content generation starting
        ebook_generation_state.update({
            "is_generating": True,
            "status": "running", # Main pipeline running status
            "message": f"Approved concept '{approved_title}'. Starting ebook content generation...",
            "pdf_filename": None, # Reset filename
            "error": None
        })
        print(f"Received start ebook *content* generation request via API for title: {approved_title}")
        # Pass the approved concept to the main pipeline wrapper
        thread = threading.Thread(target=run_ebook_pipeline_wrapper, args=(approved_title, approved_premise))
        thread.start()
        return jsonify({"message": "Ebook content generation started. Poll /status-ebook for updates."}), 202


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
    data = request.get_json()
    provided_topic = data.get('topic')

    with generation_lock:
        # Allow starting topic generation ONLY if the status is NOT actively generating topic or content.
        # This implicitly allows starting from idle, completed, error, AND awaiting_approval.
        if podcast_generation_state["status"] in ["generating_topic", "generating_podcast"]:
             return jsonify({"error": f"Podcast process already active ({podcast_generation_state['status']}). Cannot start new topic generation."}), 409

        # Reset state for new topic generation (this runs if the above check passes)
        podcast_generation_state = {
            "is_generating": True,
            "status": "generating_topic",
            "message": "Generating potential podcast topic...",
            "proposed_topic": provided_topic if provided_topic else None,
            "pdf_filenames": [],
            "error": None
        }
        print('Received start podcast *topic* generation request via API')
        
        if provided_topic:
            # If a topic is provided, skip the topic generation and move directly to awaiting approval
            podcast_generation_state.update({
                "status": "awaiting_approval",
                "message": f"Proposed Tech Topic: '{provided_topic}'. Please approve or request another.",
                "proposed_topic": provided_topic,
                "is_generating": False
            })
            return jsonify({"message": "Podcast topic provided. Awaiting approval."}), 202
        else:
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
    """API endpoint for the frontend to poll TECH podcast generation status."""
    with generation_lock:
        return jsonify(podcast_generation_state.copy())





# --- Shared Download Route (Updated) ---
# This route remains here as it handles downloads for all pipelines
@app.route('/download/<path:filename>')
def download_pdf_api(filename):
    """API endpoint to download a generated PDF (ebook, tech podcast, or trending podcast)."""
    if '..' in filename or filename.startswith('/'):
        return jsonify({"error": "Invalid filename"}), 400

    # Define potential directories relative to the main project root (d:/AWS KDP)
    # Note: send_from_directory needs paths relative to the Flask app's root_path,
    # which is d:/AWS KDP/Books-and-Podcasts/ebook_generator in this case.
    app_root = app.root_path
    project_root = os.path.dirname(app_root)

    # Potential locations relative to project_root
    ebook_dir = os.path.join(project_root, 'ebook_generator')
    tech_podcast_dir = os.path.join(project_root, 'tech_podcast_generator', 'podcasts')
    trending_podcast_dir = os.path.join(project_root, 'trending_podcast_generator', 'podcasts') if TRENDING_PIPELINE_AVAILABLE else None

    # Check locations in order
    # 1. Ebook (relative to ebook_dir)
    ebook_path = os.path.join(ebook_dir, filename)
    if os.path.exists(ebook_path) and not os.path.isdir(ebook_path):
        print(f"Attempting to serve Ebook PDF: {filename} from {ebook_dir}")
        try:
            # send_from_directory needs directory relative to app root or absolute path
            return send_from_directory(directory=ebook_dir, path=filename, as_attachment=True)
        except Exception as e:
            print(f"Error sending ebook file: {e}")
            pass # Try next location

    # 2. Tech Podcast (relative to tech_podcast_dir)
    tech_podcast_path = os.path.join(tech_podcast_dir, filename)
    if os.path.exists(tech_podcast_path):
        print(f"Attempting to serve Tech Podcast PDF: {filename} from {tech_podcast_dir}")
        try:
            return send_from_directory(directory=tech_podcast_dir, path=filename, as_attachment=True)
        except Exception as e:
            print(f"Error sending tech podcast file: {e}")
            pass # Try next location

    # 3. Trending Podcast (relative to trending_podcast_dir)
    if trending_podcast_dir:
        trending_podcast_path = os.path.join(trending_podcast_dir, filename)
        if os.path.exists(trending_podcast_path):
            print(f"Attempting to serve Trending Podcast File: {filename} from {trending_podcast_dir}")
            try:
                # Assuming trending podcasts are saved as .txt for now based on previous steps
                # Adjust mimetype if saving as PDF or audio later
                return send_from_directory(directory=trending_podcast_dir, path=filename, as_attachment=True, mimetype='text/plain')
            except Exception as e:
                print(f"Error sending trending podcast file: {e}")
                pass # File not found

    # If not found in any location
    print(f"Error: File not found - {filename}")
    return jsonify({"error": "File not found"}), 404


# --- Wrappers for Background Tasks ---

# Modified wrapper for main ebook pipeline (accepts concept)
def run_ebook_pipeline_wrapper(approved_title, approved_premise):
    """Wrapper to run the main ebook pipeline *after* concept approval."""
    global ebook_generation_state
    pipeline_result = None
    pipeline_exception = None
    try:
        # Pass the approved concept to the pipeline function
        pipeline_result = run_ebook_generation_pipeline(book_title=approved_title, book_premise=approved_premise)
    except Exception as e:
        print(f"Critical error during ebook *content* pipeline execution: {e}")
        pipeline_exception = e
    finally:
        with generation_lock:
            # Update state based on the main pipeline result
            if pipeline_exception:
                ebook_generation_state.update({
                    "status": "error", "message": f"Critical content pipeline error: {pipeline_exception}",
                    "error": str(pipeline_exception), "pdf_filename": None
                })
            elif pipeline_result:
                 final_status = "completed" if pipeline_result.get("status") == "success" else "error"
                 ebook_generation_state.update({
                    "status": final_status,
                    "message": pipeline_result.get("message", "Content generation finished."),
                    "pdf_filename": pipeline_result.get("pdf_filename"),
                    "error": pipeline_result.get("message") if final_status == "error" else None
                 })
            else: # Fallback
                 ebook_generation_state.update({
                    "status": "error", "message": "Content pipeline finished with unknown state.",
                    "error": "Unknown state.", "pdf_filename": None
                 })
            # Mark generation as fully stopped only after content pipeline finishes or errors out
            ebook_generation_state["is_generating"] = False
        print(f"Ebook *content* background task finished with status: {ebook_generation_state['status']}")

# --- New Wrapper for Ebook Concept Generation ---
# --- New Wrapper for Ebook Concept Generation ---
def run_ebook_concept_wrapper():
    """Wrapper to run only the ebook concept generation part."""
    global ebook_generation_state
    concept = None
    concept_exception = None
    try:
        model = configure_gemini() # Configure model for this task - NOW IMPORTED
        concept = ebook_conceptualize_idea(model) # Call the agent function - NOW IMPORTED
    except Exception as e:
        print(f"Critical error during ebook concept generation: {e}")
        concept_exception = e
    finally:
        with generation_lock:
            if concept_exception:
                ebook_generation_state.update({
                    "status": "error", "message": f"Failed to generate concept: {concept_exception}",
                    "error": str(concept_exception), "proposed_title": None, "proposed_premise": None, "is_generating": False
                })
            elif concept and concept.get('title') and concept.get('premise'):
                 ebook_generation_state.update({
                    "status": "awaiting_approval", # Move to approval state
                    "message": f"Proposed Concept: '{concept['title']}'. Please approve or request another.",
                    "proposed_title": concept['title'],
                    "proposed_premise": concept['premise'],
                    "error": None,
                    "is_generating": False # Concept generation is done, waiting for user
                 })
            else: # Fallback if function returns None or incomplete dict without error
                 ebook_generation_state.update({
                    "status": "error", "message": "Concept generation finished without a valid concept.",
                    "error": "Unknown concept generation state.", "proposed_title": None, "proposed_premise": None, "is_generating": False
                 })
        print(f"Ebook concept generation finished with status: {ebook_generation_state['status']}")


# --- Wrapper for Tech Podcast Topic Generation ---
def run_topic_generation_wrapper():
    """Wrapper to run only the TECH podcast topic generation part."""
    global podcast_generation_state # Uses the original podcast state
    proposed_topic = None
    topic_exception = None
    try:
        proposed_topic = generate_podcast_topic() # Call the book_pipeline agent function
    except Exception as e:
        print(f"Critical error during TECH podcast topic generation: {e}")
        topic_exception = e
    finally:
        with generation_lock:
            # Update podcast_generation_state (same logic as before)
            if topic_exception:
                podcast_generation_state.update({
                    "status": "error", "message": f"Failed to generate tech topic: {topic_exception}",
                    "error": str(topic_exception), "proposed_topic": None, "is_generating": False
                })
            elif proposed_topic:
                 podcast_generation_state.update({
                    "status": "awaiting_approval",
                    "message": f"Proposed Tech Topic: '{proposed_topic}'. Please approve or request another.",
                    "proposed_topic": proposed_topic, "error": None, "is_generating": False # Topic generation done, waiting for user
                 })
            else: # Fallback
                 podcast_generation_state.update({
                    "status": "error", "message": "Tech topic generation finished without a topic.",
                    "error": "Unknown topic generation state.", "proposed_topic": None, "is_generating": False
                 })
        print(f"TECH podcast topic generation finished with status: {podcast_generation_state['status']}")


# --- Wrapper for Tech Podcast Content Generation ---
def run_podcast_pipeline_wrapper(approved_topic):
    """Wrapper to run the TECH podcast *content* pipeline and update the global status."""
    global podcast_generation_state # Uses the original podcast state
    pipeline_result = None
    pipeline_exception = None
    try:
        # Pass the approved topic to the book_pipeline function
        pipeline_result = run_podcast_pipeline(approved_topic)
    except Exception as e:
        print(f"Critical error during TECH podcast *content* pipeline execution: {e}")
        pipeline_exception = e
    finally:
        with generation_lock:
            # Update podcast_generation_state (same logic as before)
            if pipeline_exception:
                podcast_generation_state.update({
                    "status": "error", "message": f"Critical tech content pipeline error: {pipeline_exception}",
                    "error": str(pipeline_exception), "pdf_filenames": []
                })
            elif pipeline_result:
                 final_status = "completed" if pipeline_result.get("status") == "success" else "error"
                 podcast_generation_state.update({
                    "status": final_status,
                    "message": pipeline_result.get("message", "Tech content generation finished."),
                    "pdf_filenames": pipeline_result.get("pdf_filenames", []),
                    "error": pipeline_result.get("message") if final_status == "error" else None
                 })
            else: # Fallback
                 podcast_generation_state.update({
                    "status": "error", "message": "Tech content pipeline finished with unknown state.",
                    "error": "Unknown state.", "pdf_filenames": []
                 })
            podcast_generation_state["is_generating"] = False # Mark tech process as fully done
        print(f"TECH podcast *content* background task finished with status: {podcast_generation_state['status']}")

# --- Trending Podcast Wrappers ---
# REMOVED - Now handled by the 'trending_bp' blueprint in trending_routes.py


# --- Configure Logging ---
# Configure root logger to show INFO level messages
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    stream=sys.stderr) # Log to stderr (console)

# Optionally, reduce verbosity of noisy libraries like werkzeug
# logging.getLogger('werkzeug').setLevel(logging.WARNING)


# --- Main Execution ---
if __name__ == '__main__':
    logging.info("Starting Unified Flask API server (polling)...")
    # Ensure directories exist (relative to project root)
    project_root = os.path.dirname(app.root_path)
    os.makedirs(os.path.join(project_root, 'tech_podcast_generator', 'podcasts'), exist_ok=True)
    if TRENDING_PIPELINE_AVAILABLE:
        os.makedirs(os.path.join(project_root, 'trending_podcast_generator', 'podcasts'), exist_ok=True)

    # Use Gunicorn in production via Procfile or similar
    # Debug=False is important for production and prevents auto-reloading issues with threads
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
