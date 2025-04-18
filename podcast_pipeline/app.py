import os
import time
import json
import threading
from queue import Queue
from flask import Flask, Response, jsonify, send_from_directory, request
from flask_cors import CORS # Import CORS
# Import the main logic function
from podcast_agent import run_podcast_pipeline
import config

# --- Flask App Setup ---
app = Flask(__name__)
# Configure CORS to allow requests from your frontend domain
CORS(app, resources={r"/*": {"origins": "https://books-and-podcasts.onrender.com"}})
# Simple in-memory queue to hold status messages for SSE clients
status_queue = Queue()
# Store results (e.g., list of generated PDF filenames)
results = {}
# Lock for managing access to results and generation status
generation_lock = threading.Lock()
is_generating = False

# --- Helper for SSE ---
def stream_status():
    """Generator function for Server-Sent Events."""
    while True:
        # Wait for a message in the queue
        message_data = status_queue.get()
        if message_data is None: # Use None as a signal to stop
            break
        # Format as SSE message: data: json_string\n\n
        yield f"data: {json.dumps(message_data)}\n\n"
        status_queue.task_done() # Mark message as processed

def add_status_update(message_type, data):
    """Adds a status update to the queue for SSE."""
    status_queue.put({"type": message_type, "data": data})

# --- API Routes ---
@app.route('/generate', methods=['POST'])
def start_generation_api():
    """API endpoint to trigger the podcast generation."""
    global is_generating, results
    with generation_lock:
        if is_generating:
            return jsonify({"error": "Generation already in progress."}), 409 # Conflict

        is_generating = True
        results = {} # Clear previous results
        # Clear the queue in case of previous aborted runs
        while not status_queue.empty():
            try: status_queue.get_nowait()
            except Queue.Empty: break
            status_queue.task_done()

        print('Received start generation request via API')
        add_status_update('status', {'message': 'Generation request received. Starting process...'})

        # Run the pipeline in a background thread, passing the status update function
        thread = threading.Thread(target=run_podcast_pipeline_wrapper)
        thread.start()

        return jsonify({"message": "Podcast generation started. Monitor /stream for updates."}), 202 # Accepted

@app.route('/stream')
def stream():
    """Endpoint for Server-Sent Events stream."""
    # Ensure correct MIME type for SSE
    return Response(stream_status(), mimetype='text/event-stream')

@app.route('/download/<path:filename>')
def download_file_api(filename):
    """API endpoint to download a generated PDF."""
    # Security: Basic check
    if '..' in filename or filename.startswith('/'):
        return jsonify({"error": "Invalid filename"}), 400
    podcast_directory = os.path.join('.', config.PODCAST_DIR)
    print(f"Attempting to serve PDF via API: {filename} from directory: {podcast_directory}")
    try:
        return send_from_directory(directory=podcast_directory, path=filename, as_attachment=True)
    except FileNotFoundError:
        print(f"Error: File not found - {filename} in {podcast_directory}")
        return jsonify({"error": "File not found"}), 404

@app.route('/status')
def get_status():
    """API endpoint to check current generation status and results."""
    with generation_lock:
        status_data = {
            "is_generating": is_generating,
            "results": results # Contains filenames upon completion or error message
        }
        return jsonify(status_data)

# --- Wrapper for Background Task ---
def run_podcast_pipeline_wrapper():
    """Wrapper to run the pipeline and handle status updates/completion."""
    global is_generating, results
    try:
        # Pass our status update function to the pipeline
        pipeline_results = run_podcast_pipeline(add_status_update)
        with generation_lock:
            results = pipeline_results if pipeline_results else {"error": "Pipeline finished with no results."}
    except Exception as e:
        print(f"Error during pipeline execution in wrapper: {e}")
        with generation_lock:
            results = {"error": f"Pipeline failed: {e}"}
        add_status_update('error', {'message': f"Pipeline failed: {e}"})
    finally:
        with generation_lock:
            is_generating = False
        add_status_update('finished', results) # Signal completion/error details
        status_queue.put(None) # Signal SSE generator to stop
        print("Background generation task finished.")


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Podcast Agent Flask API server...")
    os.makedirs(config.PODCAST_DIR, exist_ok=True)
    # Use Gunicorn in production via Procfile
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5001)), debug=False) # Debug=False for production/Gunicorn
