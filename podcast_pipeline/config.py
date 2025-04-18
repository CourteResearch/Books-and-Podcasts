import os
from dotenv import load_dotenv

load_dotenv() # Load variables from .env file

# --- API Keys ---
# Load keys from environment variables
GEMINI_API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
    os.getenv("GEMINI_API_KEY_4"),
]
# Filter out any keys that weren't loaded (i.e., are None)
GEMINI_API_KEYS = [key for key in GEMINI_API_KEYS if key]

if not GEMINI_API_KEYS:
    print("Warning: No Gemini API keys found in .env file. Please ensure GEMINI_API_KEY_1, etc. are set.")
    # Optionally, raise an error or exit if keys are mandatory
    # raise ValueError("Missing Gemini API Keys in .env file")

# --- Configuration Constants ---

# Directories and Files
PODCAST_DIR = "podcasts" # Directory to store generated PDF episodes
OUTLINE_FILE = "podcast_outline.md" # File to store the generated outline
FRONTEND_DIR = "frontend" # Assumes frontend files are in this subfolder

# Podcast Details
NUM_EPISODES_MIN = 7
NUM_EPISODES_MAX = 10
TARGET_WORD_COUNT_MIN = 1000 # Adjust as needed for podcast script length
TARGET_WORD_COUNT_MAX = 1500

# API Settings
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash") # Load model from .env or default
# Consider different models for different tasks (e.g., brainstorming vs writing) if needed

# Other settings
TREND_SOURCE_HINT = "trending technology topics, especially on YouTube or tech news sites" # Hint for topic generation
