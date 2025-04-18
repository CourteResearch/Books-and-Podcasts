import os
import threading
import time
from flask import Flask, render_template, send_from_directory, jsonify, request
# Removed SocketIO imports, added jsonify
# Removed CORS import as it's not needed for basic polling from same origin
from main import run_generation_pipeline

# --- Flask App Setup ---
app = Flask(__name__, template_folder='frontend', static_folder='frontend', static_url_path='/frontend')
# No SocketIO needed
# app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'a_default_secret_key_change_me')
# socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="https://books-and-podcasts.onrender.com")

# --- Global State for Polling ---
generation_status = {
    "status": "idle", # idle, running, completed, error
    "message": "Ready to generate.",
    "pdf_filename": None,
    "error": None
}
generation_lock = threading.Lock()

# --- Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

# Flask handles static files automatically via static_url_path

# --- API Routes ---
@app.route('/generate', methods=['POST'])
def start_ebook_generation_api():
    """API endpoint to trigger the ebook generation."""
    global generation_status
    with generation_lock:
        if generation_status["status"] == "running":
            return jsonify({"error": "Generation already in progress."}), 409 # Conflict

        # Reset status
        generation_status = {
            "status": "running",
            "message": "Generation request received. Starting process...",
            "pdf_filename": None,
            "error": None
        }
        print('Received start ebook generation request via API')

        # Run the pipeline in a background thread
        thread = threading.Thread(target=run_ebook_pipeline_wrapper)
        thread.start()

        return jsonify({"message": "Ebook generation started. Poll /status for updates."}), 202 # Accepted

@app.route('/status')
def get_ebook_status_api():
    """API endpoint for the frontend to poll generation status."""
    with generation_lock:
        # Return a copy to avoid race conditions if read while updating
        return jsonify(generation_status.copy())

@app.route('/download/<path:filename>')
def download_ebook_pdf_api(filename):
    """API endpoint to download the generated ebook PDF."""
    # Security: Basic check
    if '..' in filename or filename.startswith('/'):
        return jsonify({"error": "Invalid filename"}), 400
    # Serve from the app's root directory where main.py saves the PDF
    print(f"Attempting to serve Ebook PDF via API: {filename}")
    try:
        return send_from_directory(directory='.', path=filename, as_attachment=True)
    except FileNotFoundError:
        print(f"Error: Ebook PDF not found - {filename}")
        return jsonify({"error": "File not found"}), 404

# --- Wrapper for Background Task ---
def run_ebook_pipeline_wrapper():
    """Wrapper to run the pipeline and update the global status."""
    global generation_status
    try:
        # Run the refactored pipeline function
        result = run_generation_pipeline() # No longer takes socketio instance

        # Update status based on result
        with generation_lock:
            generation_status["status"] = result.get("status", "error") # completed or error
            generation_status["message"] = result.get("message", "An unknown error occurred.")
            generation_status["pdf_filename"] = result.get("pdf_filename")
            if result.get("status") == "error":
                 generation_status["error"] = result.get("message")

    except Exception as e:
        # Catch unexpected errors from the pipeline itself
        print(f"Critical error during ebook pipeline execution in wrapper: {e}")
        with generation_lock:
            generation_status["status"] = "error"
            generation_status["message"] = f"Critical pipeline error: {e}"
            generation_status["error"] = str(e)
            generation_status["pdf_filename"] = None
    finally:
        print(f"Ebook background task finished with status: {generation_status['status']}")


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Ebook Flask API server (polling)...")
    # Use Gunicorn in production via Procfile
    # Run directly with Flask's development server for local testing (debug=False for prod simulation)
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=False)
