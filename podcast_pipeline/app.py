import os
import time
import json
import threading
# Removed Queue
from flask import Flask, Response, jsonify, send_from_directory, request
# Removed CORS import
# Import the main logic function
from podcast_agent import run_podcast_pipeline
import config

# --- Flask App Setup ---
app = Flask(__name__)
# Removed SSE Queue
# Removed CORS setup

# --- Global State for Polling ---
generation_status = {
    "status": "idle", # idle, running, completed, error
    "message": "Ready to generate podcast series.",
    "pdf_filenames": [],
    "error": None
}
generation_lock = threading.Lock()

# Removed SSE Helper functions (stream_status, add_status_update)

# --- API Routes ---
@app.route('/generate', methods=['POST'])
def start_podcast_generation_api():
    """API endpoint to trigger the podcast generation."""
    global generation_status
    with generation_lock:
        if generation_status["status"] == "running":
            return jsonify({"error": "Generation already in progress."}), 409 # Conflict

        # Reset status
        generation_status = {
            "status": "running",
            "message": "Generation request received. Starting process...",
            "pdf_filenames": [],
            "error": None
        }
        print('Received start podcast generation request via API')

        # Run the pipeline in a background thread
        thread = threading.Thread(target=run_podcast_pipeline_wrapper)
        thread.start()

        return jsonify({"message": "Podcast generation started. Poll /status for updates."}), 202 # Accepted

# Removed /stream endpoint

@app.route('/download/<path:filename>')
def download_podcast_pdf_api(filename):
    """API endpoint to download a generated podcast PDF."""
    if '..' in filename or filename.startswith('/'):
        return jsonify({"error": "Invalid filename"}), 400
    podcast_directory = os.path.join('.', config.PODCAST_DIR)
    print(f"Attempting to serve Podcast PDF via API: {filename} from directory: {podcast_directory}")
    try:
        return send_from_directory(directory=podcast_directory, path=filename, as_attachment=True)
    except FileNotFoundError:
        print(f"Error: Podcast PDF not found - {filename} in {podcast_directory}")
        return jsonify({"error": "File not found"}), 404

@app.route('/status')
def get_podcast_status_api():
    """API endpoint for the frontend to poll generation status."""
    with generation_lock:
        return jsonify(generation_status.copy())

# --- Wrapper for Background Task ---
def run_podcast_pipeline_wrapper():
    """Wrapper to run the pipeline and update the global status."""
    global generation_status
    try:
        # Run the refactored pipeline function (no longer takes status_update_func)
        result = run_podcast_pipeline()

        # Update status based on result
        with generation_lock:
            generation_status["status"] = result.get("status", "error") # completed or error
            generation_status["message"] = result.get("message", "An unknown error occurred.")
            generation_status["pdf_filenames"] = result.get("pdf_filenames", [])
            if result.get("status") == "error":
                 generation_status["error"] = result.get("message")

    except Exception as e:
        # Catch unexpected errors from the pipeline itself
        print(f"Critical error during podcast pipeline execution in wrapper: {e}")
        with generation_lock:
            generation_status["status"] = "error"
            generation_status["message"] = f"Critical pipeline error: {e}"
            generation_status["error"] = str(e)
            generation_status["pdf_filenames"] = [] # Ensure empty list on critical error
    finally:
        print(f"Podcast background task finished with status: {generation_status['status']}")


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Podcast Agent Flask API server (polling)...")
    os.makedirs(config.PODCAST_DIR, exist_ok=True)
    # Use Gunicorn in production via Procfile
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5001)), debug=False) # Use different port, Debug=False
