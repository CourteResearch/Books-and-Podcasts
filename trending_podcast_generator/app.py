import argparse
import os
import datetime
import sys

# Import necessary components from the current package
from . import config  # Use relative import for config
from .agents import podcast_agent # Use relative import for agent
from . import data_fetcher # Use relative import for data_fetcher

def get_user_choice(videos: list) -> dict | None:
    """
    Prompts the user to select a video from the list and returns the selected video dict.
    """
    print("\nPlease select a video title to generate a podcast about:")
    for i, video in enumerate(videos):
        print(f"{i + 1}. {video['title']}")

    while True:
        try:
            choice = input(f"Enter the number (1-{len(videos)}) of your choice, or 'q' to quit: ")
            if choice.lower() == 'q':
                return None
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(videos):
                return videos[choice_index]
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(videos)}.")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except EOFError: # Handle Ctrl+D or unexpected end of input
             print("\nInput stream closed. Exiting selection.")
             return None


def main(duration_minutes: int):
    """
    Main function to orchestrate the trending podcast generation based on user selection.
    """
    print("--- Starting Trending Podcast Generation ---")

    # 1. Check for API Keys
    if not config.YOUTUBE_API_KEY:
        print("CRITICAL ERROR: YOUTUBE_API_KEY is not set in the .env file. Please configure it.")
        sys.exit(1) # Exit if YouTube key is missing
    if not config.GEMINI_API_KEY:
        print("CRITICAL ERROR: GEMINI_API_KEY is not set in the .env file. Please configure it.")
        sys.exit(1) # Exit if Gemini key is missing

    # 2. Fetch Trending Videos
    print("\nStep 1: Fetching trending YouTube videos...")
    # You might want to make region_code configurable later
    trending_videos = data_fetcher.fetch_trending_youtube_videos(
        api_key=config.YOUTUBE_API_KEY,
        region_code='US', # Example region
        max_results=config.TRENDING_VIDEOS_COUNT # Use config for count
    )

    if not trending_videos:
        print("Failed to fetch trending videos or none were found. Exiting.")
        return

    # 3. Get User Selection
    print("\nStep 2: Select a topic...")
    selected_video = get_user_choice(trending_videos)

    if selected_video is None:
        print("No video selected. Exiting.")
        return

    selected_title = selected_video['title']
    selected_id = selected_video['id'] # Keep the ID in case we need it later
    print(f"\nSelected topic: '{selected_title}' (ID: {selected_id})")


    # 4. Generate Podcast Script
    print("\nStep 3: Generating podcast script...")
    # NOTE: Passing title as fetched_content. May need refinement later.
    # Consider fetching video description/transcript in the future for better context.
    script = podcast_agent.generate_podcast_script(
        topic_name=selected_title,
        fetched_content=selected_title, # Using title as placeholder content
        target_duration_minutes=duration_minutes
    )

    if not script or script.startswith("Error:"):
        print(f"Failed to generate script for '{selected_title}'.")
        print(f"Reason: {script}")
        return # Stop processing if script generation failed

    # 5. Save the Script
    print("\nStep 4: Saving script...")
    # Create a filename-safe version of the topic and add timestamp
    safe_topic_name = "".join(c if c.isalnum() else "_" for c in selected_title)[:50] # Limit length
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    script_filename = f"{safe_topic_name}_{timestamp}.txt"
    script_filepath = os.path.join("Books-and-Podcasts", "trending_podcast_pipeline", "podcasts", script_filename)

    try:
        # Ensure the podcasts directory exists
        os.makedirs(os.path.dirname(script_filepath), exist_ok=True)
        with open(script_filepath, "w", encoding="utf-8") as f:
            f.write(script)
        print(f"Script saved successfully to: {script_filepath}")
    except Exception as e:
        print(f"Error saving script to {script_filepath}: {e}")
        return

    # 6. (Future Step) Generate Audio
    print("\nStep 5: Generating audio (Not Implemented)...")
    # audio_filepath = generate_audio_from_script(script, selected_title) # Placeholder
    # if audio_filepath:
    #     print(f"Audio saved successfully to: {audio_filepath}")
    # else:
    #     print("Audio generation failed.")

    print(f"\n--- Finished Trending Podcast Generation for: '{selected_title}' ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a short podcast on a trending YouTube video topic.")
    # Removed the "topic" argument
    parser.add_argument(
        "-d", "--duration",
        type=int,
        default=config.PODCAST_TARGET_DURATION_MINUTES, # Use default from config
        help=f"Target duration of the podcast in minutes (default: {config.PODCAST_TARGET_DURATION_MINUTES})."
    )
    # Add argument for number of videos to show?
    parser.add_argument(
        "-n", "--num_videos",
        type=int,
        default=config.TRENDING_VIDEOS_COUNT, # Use default from config
        help=f"Number of trending videos to fetch and display (default: {config.TRENDING_VIDEOS_COUNT})."
    )


    args = parser.parse_args()

    # Update config based on args before calling main
    config.PODCAST_TARGET_DURATION_MINUTES = args.duration
    config.TRENDING_VIDEOS_COUNT = args.num_videos


    # Basic validation for duration
    if config.PODCAST_TARGET_DURATION_MINUTES <= 0:
        print("Error: Duration must be a positive number of minutes.")
    elif config.TRENDING_VIDEOS_COUNT <= 0:
         print("Error: Number of videos must be positive.")
    else:
        # API Key checks are now inside main()
        main(config.PODCAST_TARGET_DURATION_MINUTES) # Pass duration only
