import os
import json
import requests
import random
import time
import google.auth # For fetching ADC OAuth2 token
import google.auth.transport.requests # For refreshing token
from google.cloud import aiplatform  # Required for interacting with AI Platform
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value
# Removed: from ebook_generator.agents.ebook_agent import read_pdf
from ..ebook_generator.main import configure_gemini # For LLM-based prompt generation

# --- Configuration ---
# Load environment variables
PROJECT_ID = os.getenv('PROJECT_ID')
LOCATION = 'us-central1' # As specified in the endpoint
MODEL_ID = 'veo-2.0-generate-001' # As specified in the endpoint

# Load multiple API keys from .env (e.g., GEMINI_API_KEY_1, GEMINI_API_KEY_2, ...)
API_KEYS = [key for key in os.environ if key.startswith('GEMINI_API_KEY_')]
if not API_KEYS:
    print("Warning: No GEMINI_API_KEY_X found in environment variables.")
    # Consider adding a default or raising an error if keys are mandatory

# Define base directories relative to the project root (Books_and_Podcasts)
# Assuming app.py is in Books_and_Podcasts, these paths should work from there.
# If app.py is elsewhere, adjust accordingly.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Get Books_and_Podcasts dir
PODCASTS_DIR = os.path.join(BASE_DIR, 'podcasts')
OUTPUT_DIR = os.path.join(BASE_DIR, 'generated_videos')

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize AI Platform Client (once)
if not PROJECT_ID:
    print("CRITICAL ERROR: PROJECT_ID environment variable is not set. Video generator cannot initialize.")
    # Optionally raise an error to prevent the app from starting in a broken state for video gen
    # raise ValueError("PROJECT_ID environment variable is not set. Video generator cannot initialize.")
else:
    try:
        aiplatform.init(project=PROJECT_ID, location=LOCATION)
        print(f"AI Platform initialized for project: {PROJECT_ID}, location: {LOCATION}")
    except Exception as e_init:
        print(f"CRITICAL ERROR: Failed to initialize AI Platform client: {e_init}")
        # Optionally re-raise to make it fatal for app startup if video gen is critical
        # raise

# --- Helper Functions ---

def get_random_api_key():
    """Selects a random API key from the loaded keys."""
    if not API_KEYS:
        return None # Or handle error appropriately
    return random.choice(API_KEYS)

def read_markdown_file(md_path):
    """Reads content from a markdown file."""
    print(f"Reading markdown file: {md_path}")
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading markdown file {md_path}: {e}")
        return None

def generate_prompts_from_md(md_path, num_prompts=30):
    """
    Reads Markdown text and attempts to generate a specific number of prompts.
    """
    print(f"Generating prompts from Markdown using LLM: {md_path}")
    try:
        episode_text = read_markdown_file(md_path)
        if not episode_text:
            print(f"Warning: Could not extract text from {md_path} to generate prompts.")
            return []

        model = configure_gemini() # Get a Gemini model instance

        # Meta-prompt to instruct the LLM on how to generate video prompts
        meta_prompt = (
            f"You are an expert video script segmenter. Based on the following podcast episode text, generate exactly {num_prompts} short, distinct, and narratively connected video prompts suitable for a video generation AI like VEO 2. "
            f"Each prompt should describe a visual scene or a key concept to illustrate, logically following the previous one. "
            f"Ensure thematic consistency throughout the sequence. The goal is to create a mini-storyboard that visually represents the core ideas of the episode in a compelling and ordered manner.\n\n"
            f"IMPORTANT CONSTRAINTS FOR VIDEO CONTENT:\n"
            f"1. The generated videos MUST NOT contain any on-screen text. This includes titles, captions, subtitles, code snippets, or any other textual overlays.\n"
            f"2. The generated videos MUST NOT show any scenes of coding, computer screens displaying code, or software development environments.\n\n"
            f"Focus on creating prompts that are purely visually descriptive and actionable for a video AI, adhering to the constraints above. "
            f"For example, instead of 'discuss AI ethics', a better prompt might be 'Split screen: on one side, a robot gently assisting an elderly person with a daily task; on the other, a sleek, futuristic cityscape with automated vehicles moving smoothly, implying advanced AI integration.'\n\n"
            f"Return ONLY the list of prompts, each on a new line, prefixed with 'Prompt:'. Do not include numbering or any other text.\n\n"
            f"Podcast Episode Text:\n\"\"\"\n{episode_text}\n\"\"\"\n\n"
            f"Generate {num_prompts} video prompts now, strictly following all constraints:"
        )
        
        print(f"Sending meta-prompt to LLM for {md_path}...")
        response = model.generate_content(meta_prompt)

        if not response.parts:
            print(f"LLM prompt generation failed for {md_path}. No response parts.")
            return []
        
        generated_prompts_text = response.text.strip()
        
        # Parse the LLM response to extract prompts
        prompts = []
        for line in generated_prompts_text.split('\n'):
            line_strip = line.strip()
            if line_strip.lower().startswith("prompt:"):
                prompts.append(line_strip[len("prompt:"):].strip())
            elif line_strip and not prompts: # If no "Prompt:" prefix found yet, take non-empty lines as prompts (fallback)
                prompts.append(line_strip)
        
        if not prompts:
            print(f"Warning: LLM did not generate any usable prompts for {md_path}. Raw response: {generated_prompts_text}")
            return []

        # Ensure we return the correct number of prompts, truncating or padding if necessary (though LLM should follow instructions)
        if len(prompts) > num_prompts:
            prompts = prompts[:num_prompts]
        # elif len(prompts) < num_prompts and prompts: # Simple padding if LLM undershoots (less ideal)
        #     while len(prompts) < num_prompts:
        #         prompts.append(prompts[-1] + " (continued)") 

        print(f"LLM generated {len(prompts)} prompts for {md_path}.")
        
        # Save the generated prompts to a .prompts.json file
        if prompts:
            prompts_json_path = os.path.splitext(md_path)[0] + ".prompts.json"
            try:
                with open(prompts_json_path, 'w', encoding='utf-8') as f_json:
                    json.dump(prompts, f_json, indent=2)
                print(f"Successfully saved {len(prompts)} prompts to {prompts_json_path}")
            except Exception as e_save:
                print(f"Error saving prompts to {prompts_json_path}: {e_save}")
                # Decide if this should be a fatal error or just a warning
                # For now, we'll still return the prompts even if saving fails.

        return prompts

    except Exception as e:
        print(f"Error generating prompts from Markdown using LLM for {md_path}: {e}")
        return []


def start_video_generation_task(prompt):
    """
    Initiates a video generation request to the VEO 2 API (long-running).
    Returns the operation name if successful, None otherwise.
    """
    try:
        # Get Application Default Credentials
        credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req) # Refresh token if necessary
        access_token = credentials.token
        if not access_token:
            print("Error: Could not obtain OAuth2 access token.")
            return None
    except Exception as e_auth:
        print(f"Error obtaining ADC/OAuth2 token: {e_auth}")
        return None

    endpoint_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{MODEL_ID}:predictLongRunning"

    headers = {
        "Authorization": f"Bearer {access_token}", # Use OAuth2 access token
        "Content-Type": "application/json",
    }

    # Construct the payload according to typical AI Platform predict format
    # The exact 'instances' structure depends on the VEO 2 model's specific input schema.
    # This is a common pattern, but might need adjustment based on VEO 2 documentation.
    instances = [{"prompt": prompt}] # Example instance structure
    parameters = {
        # Add any specific model parameters here if needed, e.g., video length, quality
        # "duration_seconds": 8, # Example parameter
    }

    payload = {
        "instances": instances,
        "parameters": parameters,
        # Optional: Specify output location in GCS if the API supports it
        # "outputConfig": {
        #     "gcsDestination": {
        #         "outputUriPrefix": f"gs://YOUR_BUCKET_NAME/veo_output/{int(time.time())}"
        #     }
        # }
    }

    print(f"Sending request to VEO 2 API for prompt: '{prompt[:50]}...'")
    try:
        response = requests.post(endpoint_url, headers=headers, json=payload)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # Long-running operations usually return an operation object
        operation = response.json()
        operation_name = operation.get('name')
        print(f"Successfully started video generation. Operation: {operation_name}")
        return operation_name

    except requests.exceptions.RequestException as e:
        print(f"Error calling VEO 2 API: {e}")
        if e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during API call: {e}")
        return None

# Note: The actual polling and result handling will be managed in app.py using the operation_name.
# This script now focuses on preparing prompts and initiating the generation task.

# Example of how this might be called (but will be called from app.py)
# def process_single_pdf(pdf_filename):
#     pdf_path = os.path.join(PODCASTS_DIR, pdf_filename)
#     prompts = generate_prompts_from_pdf(pdf_path)
#     operation_names = []
#     for i, prompt in enumerate(prompts):
#         print(f"--- Starting video {i+1}/{len(prompts)} for {pdf_filename} ---")
#         op_name = start_video_generation_task(prompt)
#         if op_name:
#             operation_names.append(op_name)
#         time.sleep(1) # Small delay between requests if needed
#     return operation_names

# if __name__ == '__main__':
    # This main block is for testing purposes only now
    # pdf_files = [f for f in os.listdir(PODCASTS_DIR) if f.endswith('.pdf')]
    # if pdf_files:
    #     print(f"Found PDF files: {pdf_files}")
    #     all_ops = process_single_pdf(pdf_files[0]) # Process only the first PDF for testing
    #     print(f"Started operations: {all_ops}")
    # else:
    #     print(f"No PDF files found in {PODCASTS_DIR}")
