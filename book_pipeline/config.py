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

# Directories and Files (relative to the script's execution location)
CHAPTERS_DIR = "chapters"
OUTLINE_FILE = "outline.md"
PROMPT_FILE = "../planning.md" # Assumes script runs from book_pipeline directory
PROGRESS_FILE = "progress.txt"
FRONTEND_DIR = "frontend"

# Book Details
TOTAL_CHAPTERS = 7
TARGET_WORD_COUNT_MIN = 1500
TARGET_WORD_COUNT_MAX = 2000

# API Settings (adjust as needed)
# Note: Model name might change depending on API version/availability
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash") # Load model from .env or default

# --- Podcast Specific Settings ---
PODCAST_DIR = "podcasts" # Directory to store generated PDF episodes
PODCAST_OUTLINE_FILE = "podcast_outline.md" # File to store the generated outline
NUM_EPISODES_MIN = 7
NUM_EPISODES_MAX = 10
PODCAST_TARGET_WORD_MIN = 1000 # Adjust as needed for podcast script length
PODCAST_TARGET_WORD_MAX = 1500
TREND_SOURCE_HINT = "trending technology topics, especially on YouTube or tech news sites" # Hint for topic generation
