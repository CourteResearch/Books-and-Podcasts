import os
import logging # Add logging
from dotenv import load_dotenv

# --- Determine the path to the .env file within this directory ---
# Get the directory where this config.py file is located
config_dir = os.path.dirname(os.path.abspath(__file__))
# Construct the path to the .env file in the same directory
dotenv_path = os.path.join(config_dir, '.env')

# --- Load environment variables specifically from that path ---
# Pass the explicit path to load_dotenv()
loaded = load_dotenv(dotenv_path=dotenv_path)
if loaded:
    logging.info(f"Successfully loaded .env file from: {dotenv_path}")
else:
    logging.warning(f".env file not found or failed to load from: {dotenv_path}")


# --- Get API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY not found in environment variables.")
    # raise ValueError("GEMINI_API_KEY environment variable not set.")

# Get the YouTube API key from environment variables
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not YOUTUBE_API_KEY:
    logging.warning("YOUTUBE_API_KEY not found in environment variables after loading .env.")
    # raise ValueError("YOUTUBE_API_KEY environment variable not set.")
else:
    # Log confirmation, masking most of the key
    masked_key = f"...{YOUTUBE_API_KEY[-4:]}" if len(YOUTUBE_API_KEY) > 4 else "..."
    logging.info(f"YOUTUBE_API_KEY loaded successfully (ends in: {masked_key}).")


# --- Other configurations can be added below ---
# Number of trending videos to fetch and display
TRENDING_VIDEOS_COUNT = 15 # Default, can be adjusted via command line arg in app.py

# Example: Target podcast duration
PODCAST_TARGET_DURATION_MINUTES = 7 # Default, can be adjusted

# Example: Data source configurations (placeholders)
# NEWS_API_KEY = os.getenv("NEWS_API_KEY")
# RSS_FEEDS = [
#     "http://feeds.bbci.co.uk/news/rss.xml",
#     # Add more relevant US-focused feeds later
# ]
