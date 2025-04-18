import os
import threading
from flask import Flask, render_template, send_from_directory, url_for
from flask_socketio import SocketIO, emit
from flask_cors import CORS # Import CORS
# Import the refactored main logic function
from main import run_generation_pipeline

# --- Flask App Setup ---
# Explicitly set static_url_path to match the directory name
app = Flask(__name__, template_folder='frontend', static_folder='frontend', static_url_path='/frontend')
# It's good practice to set a secret key for SocketIO
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'a_default_secret_key_change_me')
# Initialize CORS for the Flask app (optional, but can be good practice)
# CORS(app)
# Initialize SocketIO with CORS settings
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="https://books-and-podcasts.onrender.com") # Allow specific origin

# --- Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

# Remove the explicit static file route - Flask will handle it via static_url_path
# @app.route('/frontend/<path:filename>')
# def frontend_static(filename):
#     return send_from_directory(app.static_folder, filename)

# --- SocketIO Events ---
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status_update', {'message': 'Connected to server. Ready to generate.'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('start_generation')
def handle_start_generation(data):
    """Handles the request from the frontend to start the book generation."""
    print('Received start generation request')
    emit('status_update', {'message': 'Generation request received. Starting process...'})

    # --- Run the main generation logic in a background thread ---
    # This prevents the web server from freezing during the long generation process
    # We need to refactor main.py to have a callable function `run_generation_pipeline`
    # that accepts the socketio instance to emit progress.

    # Placeholder for the actual call - requires main.py refactoring
    # thread = threading.Thread(target=run_generation_pipeline, args=(socketio,))
    # thread.start()

    # --- Use socketio helper to run in background ---
    socketio.start_background_task(run_generation_pipeline, socketio)
    print("Started background task for book generation.")


# --- Add route to serve generated PDFs ---
# This allows the frontend to link to the generated PDF
@app.route('/download/<path:filename>')
def download_file(filename):
    # Security consideration: Ensure filename is safe, maybe check against a list of generated files
    # For simplicity now, directly serve from the app's root directory where the PDF is saved
    return send_from_directory(directory='.', path=filename, as_attachment=True)


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Flask server with SocketIO...")
    # Use host='0.0.0.0' to make it accessible on the network (important for Render)
    # Debug should be False in production
    socketio.run(app, host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True, allow_unsafe_werkzeug=True)
