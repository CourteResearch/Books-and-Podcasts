import os
import os
import sys
import threading
import time
import datetime
import logging # Import logging
from flask import Flask, render_template, send_from_directory, jsonify, request
from flask_cors import CORS # Import CORS

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
from Books_and_Podcasts.ebook_generator.agents.ebook_agent import run_ebook_generation_pipeline, ebook_conceptualize_idea # Import concept func
from Books_and_Podcasts.tech_podcast_generator.agents.podcast_agent import generate_podcast_topic, run_podcast_pipeline
from Books_and_Podcasts.ebook_generator.main import configure_gemini
import Books_and_Podcasts.ebook_generator.config as book_config
# Import video generator components
from Books_and_Podcasts.video_generator.video_generator import ( # Adjusted path
    generate_prompts_from_md, # Changed from generate_prompts_from_pdf
    start_video_generation_task,
    PODCASTS_DIR as VIDEO_PODCASTS_DIR, # Use specific alias to avoid confusion
    OUTPUT_DIR as VIDEO_OUTPUT_DIR,
    PROJECT_ID, # Import PROJECT_ID if needed here, or rely on video_generator's init
    LOCATION
)
from google.cloud import aiplatform # For polling operations
from google.cloud.aiplatform_v1 import JobServiceClient # More specific client for ops - UPDATED IMPORT
from google.longrunning import operations_pb2 # To work with operation objects
from google.protobuf import json_format
import google.auth # For authentication if needed directly in app
import google.auth.transport.requests
from google.cloud import storage # Import GCS client library

# --- Check Trending Pipeline Availability (Needed for UI and Download Route) ---
# We still need to know if it's available, even if routes are separate.
try:
    # Try importing something minimal from the trending pipeline to check availability
    from Books_and_Podcasts.trending_podcast_generator import config as trending_config_check
    TRENDING_PIPELINE_AVAILABLE = True
    # We don't need the actual agent/fetcher imports here anymore
except ImportError as e:
    print(f"Warning (app.py): Could not import trending_podcast_pipeline components: {e}")
    print("Trending podcast functionality will be disabled.")
    TRENDING_PIPELINE_AVAILABLE = False

# --- Import the Blueprint ---
if TRENDING_PIPELINE_AVAILABLE:
    try:
        from Books_and_Podcasts.ebook_generator.trending_routes import trending_bp
    except ImportError as bp_e:
        print(f"ERROR: Failed to import trending_routes blueprint even though pipeline seemed available: {bp_e}")
        TRENDING_PIPELINE_AVAILABLE = False # Mark as unavailable if blueprint import fails


# --- Flask App Setup ---
app = Flask(__name__, template_folder='frontend', static_folder='frontend', static_url_path='/frontend')
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}, # Allow frontend origin for API routes
                     r"/generate-*": {"origins": "http://localhost:3000"},
                     r"/status-*": {"origins": "http://localhost:3000"},
                     r"/download/*": {"origins": "http://localhost:3000"}})


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
    "current_genre": None, # Added to store the genre for the current operation
    "pdf_filename": None,
    "error": None
}
podcast_generation_state = {
    "is_generating": False, # True if any part of the process is running
    "status": "idle", # idle, generating_topic, awaiting_approval, generating_podcast, completed, error
    "message": "Ready to generate Podcast Series.",
    "proposed_topic": None, # Store the topic awaiting approval
    "pdf_filenames": [], # Expecting multiple PDFs for tech podcasts
    "error": None
}
# Add state for video generation
video_generation_state = {
    "is_generating": False,
    "status": "idle", # idle, preparing_prompts, starting_jobs, polling_jobs, completed, error
    "message": "Ready to generate videos from podcasts.",
    "operation_names": [], # List to store active Google Cloud operation names
    "video_filenames": [], # List of successfully generated local video filenames
    "error": None,
    "total_videos": 0,
    "completed_videos": 0,
}


# Use separate locks if high contention is expected, or one global lock for simplicity
# Keep the main lock for ebook/tech podcast state
generation_lock = threading.Lock()
# Add a separate lock for video state as polling might happen frequently
video_state_lock = threading.Lock()


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
    data = request.get_json()
    requested_genre = data.get('genre', 'Thriller') # Default to Thriller if not provided

    with generation_lock:
        if ebook_generation_state["status"] in ["generating_concept", "running"]:
             return jsonify({"error": f"Ebook process already active ({ebook_generation_state['status']}). Cannot start new concept generation."}), 409

        ebook_generation_state = {
            "is_generating": True,
            "status": "generating_concept",
            "message": f"Generating potential ebook concept for genre: {requested_genre}...",
            "proposed_title": None,
            "proposed_premise": None,
            "current_genre": requested_genre, # Store the requested genre
            "pdf_filename": None,
            "error": None
        }
        print(f"Received start ebook *concept* generation request via API for genre: {requested_genre}")
        thread = threading.Thread(target=run_ebook_concept_wrapper, args=(requested_genre,)) # Pass genre to wrapper
        thread.start()
        return jsonify({"message": f"Ebook concept generation for {requested_genre} started. Poll /status-ebook for updates."}), 202

@app.route('/generate-ebook', methods=['POST'])
def start_ebook_content_generation_api():
    """API endpoint to trigger the ebook *content* generation *after* concept approval."""
    global ebook_generation_state
    data = request.get_json()
    approved_title = data.get('title')
    approved_premise = data.get('premise')
    # Genre should be retrieved from the state, not directly from this request
    # as it was set during concept generation.

    if not approved_title or not approved_premise:
        return jsonify({"error": "Missing 'title' or 'premise' in request body."}), 400

    with generation_lock:
        if ebook_generation_state["status"] != "awaiting_approval":
            return jsonify({"error": f"Cannot start content generation. Current status: {ebook_generation_state['status']}."}), 409
        
        current_genre_for_pipeline = ebook_generation_state.get("current_genre", "Thriller") # Fallback if not in state

        ebook_generation_state.update({
            "is_generating": True,
            "status": "running", 
            "message": f"Approved concept '{approved_title}' for genre '{current_genre_for_pipeline}'. Starting ebook content generation...",
            "pdf_filename": None, 
            "error": None
            # current_genre remains as it was
        })
        print(f"Received start ebook *content* generation request via API for title: {approved_title}, Genre: {current_genre_for_pipeline}")
        # Pass the approved concept AND genre to the main pipeline wrapper
        thread = threading.Thread(target=run_ebook_pipeline_wrapper, args=(approved_title, approved_premise, current_genre_for_pipeline))
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

# --- Video Generation Routes ---

@app.route('/generate-videos-from-podcasts', methods=['POST']) # Kept old route name for now, but behavior changes
def start_video_generation_api():
    """API endpoint to trigger video generation for a specific podcast episode."""
    global video_generation_state
    data = request.get_json()
    episode_filename = data.get('episode_filename')

    if not episode_filename:
        return jsonify({"error": "Missing 'episode_filename' in request body."}), 400
    
    # Basic validation for filename
    if not episode_filename.lower().endswith('.md') or '..' in episode_filename or '/' in episode_filename or '\\' in episode_filename:
        return jsonify({"error": "Invalid 'episode_filename'. Must be a .md file and a simple filename."}), 400

    episode_md_path = os.path.join(VIDEO_PODCASTS_DIR, episode_filename)
    if not os.path.exists(episode_md_path):
        return jsonify({"error": f"Episode file not found: {episode_filename}"}), 404

    with video_state_lock:
        if video_generation_state["is_generating"]:
            # Could enhance this to queue or manage per-episode states if multiple can run
            return jsonify({"error": "Video generation is already in progress for another task."}), 409

        # Reset state for a new run (or manage per-episode state if needed)
        video_generation_state = {
            "is_generating": True,
            "status": "preparing_prompts",
            "message": f"Starting video generation for episode: {episode_filename}...",
            "current_episode": episode_filename, # Track current episode
            "operation_names": [],
            "video_filenames": [], # Store filenames for this specific episode's videos
            "error": None,
            "total_videos": 0,
            "completed_videos": 0,
        }
        print(f"Received request to generate videos for episode: {episode_filename}")
        # Start the background task, passing the specific episode filename
        thread = threading.Thread(target=run_video_generation_wrapper, args=(episode_filename,))
        thread.start()
        return jsonify({"message": f"Video generation process initiated for {episode_filename}. Poll /status-video for updates."}), 202

@app.route('/status-video')
def get_video_status_api():
    """API endpoint for polling video generation status."""
    # No lock here initially, as polling might read while the background thread updates.
    # We'll lock inside when updating the state based on polling results.
    # Return a copy to avoid race conditions during read.
    with video_state_lock:
        state_copy = video_generation_state.copy()
    return jsonify(state_copy)

@app.route('/api/list-podcast-episodes', methods=['GET'])
def list_podcast_episodes_api():
    """API endpoint to list available podcast Markdown episode files."""
    if not os.path.exists(VIDEO_PODCASTS_DIR):
        return jsonify({"error": f"Podcasts directory not found: {VIDEO_PODCASTS_DIR}", "episodes": []}), 404
    
    try:
        md_files = [f for f in os.listdir(VIDEO_PODCASTS_DIR) if f.lower().endswith('.md')]
        episodes_data = []
        for md_file in md_files:
            prompts_json_file = os.path.splitext(md_file)[0] + ".prompts.json"
            # Check for existing videos (simple check, could be more sophisticated)
            # This assumes video filenames might be related to the md_file name.
            # For now, just indicate if prompts exist.
            has_prompts = os.path.exists(os.path.join(VIDEO_PODCASTS_DIR, prompts_json_file))
            episodes_data.append({
                "filename": md_file,
                "has_prompts": has_prompts,
                # "has_video": False # Placeholder for future video status check
            })
        return jsonify({"episodes": episodes_data}), 200
    except Exception as e:
        logging.error(f"Error listing podcast episodes: {e}")
        return jsonify({"error": "Failed to list podcast episodes.", "episodes": []}), 500

# --- Shared Download Route (Updated) ---
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
                pass # Try next location

    # 4. Generated Videos (relative to VIDEO_OUTPUT_DIR)
    video_path = os.path.join(VIDEO_OUTPUT_DIR, filename)
    if os.path.exists(video_path):
        print(f"Attempting to serve Generated Video: {filename} from {VIDEO_OUTPUT_DIR}")
        try:
            # Determine mimetype based on extension (simple approach)
            mimetype = 'video/mp4' if filename.lower().endswith('.mp4') else 'application/octet-stream'
            return send_from_directory(directory=VIDEO_OUTPUT_DIR, path=filename, as_attachment=True, mimetype=mimetype)
        except Exception as e:
            print(f"Error sending video file: {e}")
            pass # File not found

    # If not found in any location
    print(f"Error: File not found - {filename}")
    return jsonify({"error": "File not found"}), 404


# --- Wrappers for Background Tasks ---

# Modified wrapper for main ebook pipeline (accepts concept and genre)
def run_ebook_pipeline_wrapper(approved_title, approved_premise, genre):
    """Wrapper to run the main ebook pipeline *after* concept approval."""
    global ebook_generation_state
    pipeline_result = None
    pipeline_exception = None
    try:
        # Pass the approved concept and genre to the agent's pipeline function
        # This now calls the run_ebook_generation_pipeline from ebook_agent.py
        pipeline_result = run_ebook_generation_pipeline(book_title=approved_title, book_premise=approved_premise, genre_preference=genre)
    except Exception as e:
        print(f"Critical error during ebook *content* pipeline execution (genre: {genre}): {e}")
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
                 # The pipeline_result from ebook_agent now also includes 'genre'
                 ebook_generation_state.update({
                    "status": final_status,
                    "message": pipeline_result.get("message", f"Content generation for genre {genre} finished."),
                    "pdf_filename": pipeline_result.get("pdf_filename"),
                    "current_genre": pipeline_result.get("genre", genre), # Update genre from result if available
                    "error": pipeline_result.get("message") if final_status == "error" else None
                 })
            else: # Fallback
                 ebook_generation_state.update({
                    "status": "error", "message": f"Content pipeline for genre {genre} finished with unknown state.",
                    "error": "Unknown state.", "pdf_filename": None
                 })
            ebook_generation_state["is_generating"] = False
        print(f"Ebook *content* background task for genre {genre} finished with status: {ebook_generation_state['status']}")

# --- New Wrapper for Ebook Concept Generation (accepts genre) ---
def run_ebook_concept_wrapper(genre_to_conceptualize):
    """Wrapper to run only the ebook concept generation part for a specific genre."""
    global ebook_generation_state
    concept = None
    concept_exception = None
    try:
        model = configure_gemini() 
        # Call the ebook_conceptualize_idea from ebook_agent.py, passing the genre
        concept = ebook_conceptualize_idea(model, genre=genre_to_conceptualize) 
    except Exception as e:
        print(f"Critical error during ebook concept generation for genre {genre_to_conceptualize}: {e}")
        concept_exception = e
    finally:
        with generation_lock:
            # current_genre should already be set in ebook_generation_state by the API route
            # We're just confirming it here or using the passed-in one as a fallback.
            current_genre_in_state = ebook_generation_state.get("current_genre", genre_to_conceptualize)

            if concept_exception:
                ebook_generation_state.update({
                    "status": "error", "message": f"Failed to generate concept for genre {current_genre_in_state}: {concept_exception}",
                    "error": str(concept_exception), "proposed_title": None, "proposed_premise": None, 
                    "current_genre": current_genre_in_state, "is_generating": False
                })
            elif concept and concept.get('title') and concept.get('premise'):
                 ebook_generation_state.update({
                    "status": "awaiting_approval", 
                    "message": f"Proposed Concept for {current_genre_in_state}: '{concept['title']}'. Please approve or request another.",
                    "proposed_title": concept['title'],
                    "proposed_premise": concept['premise'],
                    "current_genre": current_genre_in_state, # Ensure it's correctly stored
                    "error": None,
                    "is_generating": False 
                 })
            else: 
                 ebook_generation_state.update({
                    "status": "error", "message": f"Concept generation for genre {current_genre_in_state} finished without a valid concept.",
                    "error": "Unknown concept generation state.", "proposed_title": None, "proposed_premise": None,
                    "current_genre": current_genre_in_state, "is_generating": False
                 })
        print(f"Ebook concept generation for genre {ebook_generation_state.get('current_genre')} finished with status: {ebook_generation_state['status']}")


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
        concept_exception = e
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
                 final_status = "completed" if pipeline_result.get("status") == "success" else "error" # Corrected condition and removed extra comma from message default
                 podcast_generation_state.update({
                    "status": final_status,
                    "message": pipeline_result.get("message", "Tech content generation finished."),
                    "pdf_filenames": pipeline_result.get("pdf_filenames", []),
                    "error": pipeline_result.get("message") if final_status == "error" else None
                 }) # Corrected closing parenthesis placement
            else: # Fallback
                 podcast_generation_state.update({
                    "status": "error", "message": "Tech content pipeline finished with unknown state.",
                    "error": "Unknown state.", "pdf_filenames": []
                 })
            podcast_generation_state["is_generating"] = False # Mark tech process as fully done
        print(f"TECH podcast *content* background task finished with status: {podcast_generation_state['status']}")

# --- Trending Podcast Wrappers ---
# REMOVED - Now handled by the 'trending_bp' blueprint in trending_routes.py

# --- GCS Download Helper ---
def download_blob(gcs_uri, destination_file_name):
    """Downloads a blob from the bucket using GCS URI."""
    # GCS URI format: gs://bucket-name/object-name
    if not gcs_uri.startswith("gs://"):
        print(f"Error: Invalid GCS URI format: {gcs_uri}")
        return False
    
    try:
        storage_client = storage.Client() # Assumes Application Default Credentials
        
        path_parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name = path_parts[0]
        source_blob_name = path_parts[1] if len(path_parts) > 1 else None

        if not source_blob_name:
             print(f"Error: Could not parse blob name from GCS URI: {gcs_uri}")
             return False

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)

        # Ensure destination directory exists
        os.makedirs(os.path.dirname(destination_file_name), exist_ok=True)
        
        blob.download_to_filename(destination_file_name)

        print(f"Blob {source_blob_name} downloaded from {bucket_name} to {destination_file_name}.")
        return True
    except Exception as e:
        print(f"Error downloading from GCS {gcs_uri} to {destination_file_name}: {e}")
        return False

# --- Wrapper for Video Generation ---
def run_video_generation_wrapper(episode_md_filename):
    """Wrapper for video generation process for a single podcast Markdown file."""
    global video_generation_state
    all_operation_names = []
    operation_to_details_map = {} # To map op_name to episode and prompt index
    total_prompts_to_generate = 0

    try:
        # --- Phase 1: Generate or Load Prompts for the specified episode ---
        with video_state_lock: # Ensure status update is atomic
            video_generation_state["status"] = "preparing_prompts"
            video_generation_state["message"] = f"Preparing prompts for {episode_md_filename}..."
        
        md_path = os.path.join(VIDEO_PODCASTS_DIR, episode_md_filename)
        prompts_json_path = os.path.splitext(md_path)[0] + ".prompts.json"
        
        prompts_for_episode = []
        if os.path.exists(prompts_json_path):
            try:
                with open(prompts_json_path, 'r', encoding='utf-8') as f_json:
                    prompts_for_episode = json.load(f_json)
                print(f"Loaded {len(prompts_for_episode)} prompts from existing file: {prompts_json_path}")
            except Exception as e_load:
                print(f"Error loading prompts from {prompts_json_path}: {e_load}. Will attempt to regenerate.")
                prompts_for_episode = [] # Ensure regeneration

        if not prompts_for_episode:
            print(f"No pre-existing prompts found or failed to load for {episode_md_filename}. Generating new prompts...")
            num_prompts_to_generate_per_episode = 10 # Could be configurable
            prompts_for_episode = generate_prompts_from_md(md_path, num_prompts=num_prompts_to_generate_per_episode)
        
        # We are processing prompts for a single episode, so all_prompts becomes prompts_for_episode
        # The tuple structure (prompt, origin_md_file, index) is still useful
        all_prompts_with_origin = [(p, episode_md_filename, i) for i, p in enumerate(prompts_for_episode)]
        
        total_prompts_to_generate = len(all_prompts_with_origin)
        if total_prompts_to_generate == 0:
             with video_state_lock:
                video_generation_state.update({
                    "status": "error", "message": "Could not generate any prompts from the PDF files.",
                    "error": "Prompt generation failed.", "is_generating": False
                })
             print("Video Gen Error: No prompts generated.")
             return

        with video_state_lock:
            video_generation_state["status"] = "starting_jobs"
            video_generation_state["message"] = f"Generated {total_prompts_to_generate} prompts. Starting VEO 2 generation jobs..."
            video_generation_state["total_videos"] = total_prompts_to_generate

        # --- Phase 2: Start VEO 2 Jobs ---
        print(f"Starting {total_prompts_to_generate} VEO 2 jobs...")
        for prompt, md_origin, prompt_index in all_prompts_with_origin:
            # md_origin will always be episode_md_filename here
            op_name = start_video_generation_task(prompt) # Call the function that starts the VEO task
            if op_name:
                all_operation_names.append(op_name)
                operation_to_details_map[op_name] = {"episode_file": md_origin, "prompt_index": prompt_index}
                print(f"  Video job started for {md_origin}, prompt {prompt_index + 1}. Operation: {op_name}")
            else:
                print(f"Warning: Failed to start video generation job for a prompt from {episode_md_filename}, index {prompt_index}.")
                # Optionally update state to reflect partial failure immediately
            time.sleep(1) # Small delay between API calls

        if not all_operation_names:
            with video_state_lock:
                video_generation_state.update({
                    "status": "error", "message": "Failed to start any VEO 2 generation jobs.",
                    "error": "API job start failed.", "is_generating": False
                })
            print("Video Gen Error: Failed to start any jobs.")
            return

        with video_state_lock:
            video_generation_state["status"] = "polling_jobs"
            video_generation_state["message"] = f"Started {len(all_operation_names)} VEO 2 jobs. Now polling for completion..."
            video_generation_state["operation_names"] = all_operation_names

        # --- Phase 3: Poll for Completion (Simplified Polling Loop) ---
        # A more robust implementation would use a separate poller thread or task queue status checks.
        # This simple loop runs within the initial thread.
        print(f"Polling {len(all_operation_names)} operations...")
        completed_ops = set()
        final_video_files = []
        max_polling_time = 3600 # Max 1 hour polling (adjust as needed)
        start_time = time.time()

        # Initialize AI Platform Job Service Client for polling
        # Use credentials directly if needed, otherwise relies on application default credentials
        # credentials, project = google.auth.default()
        # client_options = {"api_endpoint": f"{LOCATION}-aiplatform.googleapis.com"}
        # client = JobServiceClient(credentials=credentials, client_options=client_options)
        # Simpler polling via requests for now, assuming operation name is full path
        ops_client = aiplatform.gapic.OperationsClient(client_options={"api_endpoint": f"{LOCATION}-aiplatform.googleapis.com"})


        while len(completed_ops) < len(all_operation_names) and (time.time() - start_time) < max_polling_time:
            current_completed_count = 0
            ops_still_running = []
            error_occurred = False
            error_message = ""

            for op_name in all_operation_names:
                if op_name in completed_ops:
                    current_completed_count +=1
                    continue # Skip already completed ops

                try:
                    # Use OperationsClient to get operation status
                    operation = ops_client.get_operation(name=op_name) # op_name should be full path like 'projects/.../operations/...'

                    if operation.done:
                        completed_ops.add(op_name)
                        current_completed_count += 1
                        if operation.error.code != 0: # Check if operation failed
                            print(f"Operation {op_name} failed: {operation.error.message}")
                            error_occurred = True
                            error_message += f"Job {op_name} failed. "
                        else:
                            print(f"Operation {op_name} succeeded.")
                            # Process successful operation result
                            # The result structure depends on the VEO 2 API's long-running operation metadata/response schema.
                            # Assuming the response contains a GCS URI for the generated video.
                            response_dict = json_format.MessageToDict(operation.response) # Convert protobuf response to dict
                            # --- TODO: Adapt the following based on actual VEO 2 response ---
                            gcs_uri = response_dict.get("outputVideoGcsUri", None) 
                            if gcs_uri:
                                print(f"Video generated at GCS URI: {gcs_uri} for operation {op_name}")
                                
                                # Retrieve episode details for naming
                                job_details = operation_to_details_map.get(op_name)
                                if job_details:
                                    episode_base_name = os.path.splitext(job_details["episode_file"])[0]
                                    segment_number = job_details["prompt_index"] + 1
                                    local_filename = f"{episode_base_name}_segment_{segment_number}.mp4"
                                else: # Fallback if details not found (should not happen)
                                    local_filename = f"{os.path.splitext(os.path.basename(gcs_uri))[0]}_{int(time.time())}.mp4"
                                
                                local_path = os.path.join(VIDEO_OUTPUT_DIR, local_filename)
                                
                                if download_blob(gcs_uri, local_path):
                                    final_video_files.append(local_filename) 
                                    print(f"  Successfully downloaded and saved: {local_filename}")
                                else:
                                    print(f"Error: Failed to download video from {gcs_uri} for {local_filename}")
                                    error_occurred = True # Mark error if download fails
                                    error_message += f"Download failed for {gcs_uri}. "
                            else:
                                print(f"Warning: Operation {op_name} succeeded but no output URI found in response: {response_dict}")
                                error_occurred = True
                                error_message += f"Job {op_name} finished without output. "
                    else:
                         ops_still_running.append(op_name) # Keep polling this one

                except Exception as e:
                    print(f"Error polling operation {op_name}: {e}")
                    completed_ops.add(op_name) # Stop polling this op after error
                    current_completed_count += 1
                    error_occurred = True
                    error_message += f"Polling error for {op_name}. "

            # Update state after checking all ops in this polling interval
            with video_state_lock:
                video_generation_state["completed_videos"] = len(final_video_files) # Count successful downloads
                video_generation_state["video_filenames"] = final_video_files
                if error_occurred:
                     video_generation_state["error"] = (video_generation_state.get("error") or "") + error_message
                if len(completed_ops) == len(all_operation_names): # All jobs finished (success or fail)
                    video_generation_state["status"] = "completed" if not video_generation_state["error"] else "error"
                    video_generation_state["message"] = f"Video generation finished. {len(final_video_files)} videos ready." if video_generation_state["status"] == "completed" else f"Video generation finished with errors. {video_generation_state['error']}"
                    video_generation_state["is_generating"] = False
                    print(f"Video generation finished. Final status: {video_generation_state['status']}")
                else:
                    video_generation_state["message"] = f"Polling... {len(completed_ops)}/{len(all_operation_names)} jobs completed. {len(final_video_files)} videos ready."

            if video_generation_state["status"] in ["completed", "error"]:
                break # Exit polling loop

            time.sleep(15) # Wait before next polling interval (adjust as needed)

        # --- Final State Update after Polling Loop ---
        with video_state_lock:
            if video_generation_state["status"] not in ["completed", "error"]:
                # If loop finished due to timeout
                video_generation_state["status"] = "error"
                video_generation_state["message"] = "Video generation timed out while polling."
                video_generation_state["error"] = "Polling timeout."
                video_generation_state["is_generating"] = False
                print("Video generation polling timed out.")
            # Ensure is_generating is false if loop finishes
            video_generation_state["is_generating"] = False


    except Exception as e:
        print(f"Critical error during video generation wrapper: {e}")
        with video_state_lock:
            video_generation_state.update({
                "status": "error", "message": f"Critical error: {e}",
                "error": str(e), "is_generating": False, "operation_names": [], "video_filenames": []
            })

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

    # Ensure video output directory exists
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

    # Use Gunicorn in production via Procfile or similar
    # Debug=False is important for production and prevents auto-reloading issues with threads
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
