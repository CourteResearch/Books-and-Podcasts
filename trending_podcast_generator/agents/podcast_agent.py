import google.generativeai as genai
import os
from Books_and_Podcasts.trending_podcast_pipeline import config

# Configure the Gemini API key
if config.GEMINI_API_KEY:
    genai.configure(api_key=config.GEMINI_API_KEY)
else:
    print("Error: Gemini API Key not configured. Please set GEMINI_API_KEY in .env")
    # Consider raising an exception or exiting if the key is critical
    # exit()

# Initialize the Gemini Model (specify 1.5 Pro)
# Make sure the model name 'gemini-1.5-pro-latest' is correct for your access
try:
    model = genai.GenerativeModel('gemini-2.0-flash')
    print("Gemini model initialized successfully.")
except Exception as e:
    print(f"Error initializing Gemini model: {e}")
    model = None # Ensure model is None if initialization fails

def generate_podcast_script(topic_name: str, fetched_content: str, target_duration_minutes: int) -> str:
    """
    Generates a podcast script using Gemini based on fetched content.

    Args:
        topic_name: The name of the trending topic.
        fetched_content: The text content fetched from recent sources.
        target_duration_minutes: The desired length of the podcast in minutes.

    Returns:
        The generated podcast script as a string, or an error message.
    """
    if not model:
        return "Error: Gemini model not initialized."
    if not fetched_content:
        return "Error: No content provided to generate script from."

    print(f"Generating podcast script for '{topic_name}' ({target_duration_minutes} mins)...")

    # --- Prompt Engineering ---
    # Craft a detailed prompt for Gemini 1.5 Pro
    # Incorporate the fetched content and desired duration.
    # Instruct it on the desired tone, format (e.g., intro, segments, outro),
    # and target audience (e.g., general US audience).
    prompt = f"""
    You are a podcast script writer specializing in creating engaging, concise summaries of trending news topics for a general US audience.

    Topic: {topic_name}

    Recent Information Gathered:
    --- START CONTENT ---
    {fetched_content}
    --- END CONTENT ---

    Task:
    Generate a podcast script based *only* on the 'Recent Information Gathered' provided above.
    The target duration for the spoken podcast is approximately {target_duration_minutes} minutes.
    Structure the script with:
    1.  A brief, catchy introduction (~15-30 seconds).
    2.  One or two main segments discussing the key points from the content (~{target_duration_minutes*60 - 60} seconds total).
    3.  A concise concluding summary and outro (~15-30 seconds).

    Tone: Informative, engaging, objective, and easy to understand. Avoid jargon where possible or explain it simply.
    Format: Provide the script text clearly, indicating any sound effects or music cues if desired (e.g., "[Intro Music Fade In]").

    Output only the script content.
    """

    try:
        # Use the generate_content method
        response = model.generate_content(prompt)

        # Access the text part of the response
        # Handle potential lack of text or other response issues gracefully
        if response.parts:
             script = "".join(part.text for part in response.parts)
             print("Podcast script generated successfully.")
             return script
        elif response.prompt_feedback:
             # Handle content blocking or other safety issues
             print(f"Content generation blocked: {response.prompt_feedback}")
             return f"Error: Content generation failed due to safety filters: {response.prompt_feedback}"
        else:
             # Handle other potential errors or empty responses
             print("Error: Received an empty or unexpected response from Gemini.")
             # You might want to inspect the full 'response' object here for debugging
             # print(response)
             return "Error: Failed to generate script. Received an unexpected response."

    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        # Consider more specific error handling based on potential API errors
        return f"Error: An exception occurred during script generation: {e}"

# Example usage (for testing purposes)
if __name__ == '__main__':
    # This block will only run when the script is executed directly
    # Replace with actual test content and topic
    test_content = "This is some sample content about a trending topic that happened today."
    test_topic = "Sample Trending Topic"
    test_duration = 5
    
    # Make sure the config is loaded correctly when running directly
    # You might need to adjust the path to .env if running from a different directory
    # Example: load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))
    
    if config.GEMINI_API_KEY: # Check again if running directly
         script = generate_podcast_script(test_topic, test_content, test_duration)
         print("\n--- Generated Script ---")
         print(script)
    else:
         print("\nCannot run test: GEMINI_API_KEY not found.")
