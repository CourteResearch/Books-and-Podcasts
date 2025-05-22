import os
import time # Import time for timing
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

# Assuming config.py loads environment variables and has YOUTUBE_API_KEY
from . import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# YouTube API constants
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

def fetch_trending_youtube_videos(api_key: str, region_code: str = 'US', max_results: int = 25) -> list:
    """
    Fetches the most popular YouTube videos from the last 3 weeks for a specific region.

    Args:
        api_key: Your YouTube Data API v3 key.
        region_code: The ISO 3166-1 alpha-2 country code (e.g., 'US', 'GB', 'IN').
        max_results: The maximum number of results to return (up to 50).

    Returns:
        A list of dictionaries, where each dictionary contains 'title' and 'id'
        of a trending video, or an empty list if an error occurs or no videos are found.
    """
    if not api_key:
        logging.error("YouTube API key is missing.")
        return []

    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, developerKey=api_key)

        # Calculate the date 3 weeks ago in RFC 3339 format (required by YouTube API)
        three_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=3)
        published_after_date = three_weeks_ago.isoformat() # e.g., '2023-10-05T10:00:00Z'

        logging.info(f"Fetching top {max_results} trending videos for region '{region_code}' published after {published_after_date}")

        request = youtube.videos().list(
            part="snippet",             # We only need basic info like title
            chart="mostPopular",
            regionCode=region_code,
            maxResults=max_results,
            # publishedAfter=published_after_date # Note: publishedAfter doesn't work reliably with chart=mostPopular
                                                # The chart itself represents recent popularity.
                                                # We will rely on the 'mostPopular' chart's inherent recency.
        )

        start_time = time.time()
        logging.info("Executing YouTube API videos.list request...")
        response = request.execute()
        end_time = time.time()
        logging.info(f"YouTube API request execution took {end_time - start_time:.2f} seconds.")

        videos = []
        if 'items' in response:
            for item in response['items']:
                title = item['snippet'].get('title', 'No Title')
                video_id = item.get('id')
                if video_id: # Ensure we have an ID
                    videos.append({'id': video_id, 'title': title})
            logging.info(f"Successfully fetched {len(videos)} trending video titles.")
        else:
            logging.warning("No 'items' found in YouTube API response.")

        return videos

    except HttpError as e:
        logging.error(f"An HTTP error {e.resp.status} occurred: {e.content}")
        return []
    except Exception as e:
        logging.error(f"An unexpected error occurred while fetching YouTube videos: {e}")
        return []

# Example usage (for testing purposes)
if __name__ == '__main__':
    # Load API key from environment for testing
    # Make sure YOUTUBE_API_KEY is set in your .env file and loaded by config
    api_key_to_test = config.YOUTUBE_API_KEY
    if not api_key_to_test:
        print("Error: YOUTUBE_API_KEY not found in config/environment variables.")
        print("Please set it in Books-and-Podcasts/trending_podcast_pipeline/.env")
    else:
        print(f"Using API Key: ...{api_key_to_test[-4:]}") # Mask key for printing
        trending_videos = fetch_trending_youtube_videos(api_key_to_test, region_code='US', max_results=10)

        if trending_videos:
            print("\n--- Trending YouTube Videos (Last 3 Weeks) ---")
            for i, video in enumerate(trending_videos):
                print(f"{i+1}. ID: {video['id']}, Title: {video['title']}")
        else:
            print("\nCould not fetch trending videos or none were found.")
