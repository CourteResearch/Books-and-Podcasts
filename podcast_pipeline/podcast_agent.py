import google.generativeai as genai
import os
import time
import re
import shutil
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import requests # Keep for potential future use

# Import config
from config import (
    GEMINI_API_KEYS, GEMINI_MODEL, PODCAST_DIR, OUTLINE_FILE,
    NUM_EPISODES_MIN, NUM_EPISODES_MAX, TARGET_WORD_COUNT_MIN,
    TARGET_WORD_COUNT_MAX, TREND_SOURCE_HINT
)

# --- Global Variables ---
current_api_key_index = 0

# --- Helper Functions ---

def get_next_api_key():
    """Rotates through the API keys."""
    global current_api_key_index
    if not GEMINI_API_KEYS:
        raise ValueError("No API keys loaded. Cannot proceed.")
    key = GEMINI_API_KEYS[current_api_key_index]
    if "YOUR_API_KEY" in key:
         print(f"Warning: API Key at index {current_api_key_index} seems to be a placeholder.")
    current_api_key_index = (current_api_key_index + 1) % len(GEMINI_API_KEYS)
    return key

def configure_gemini():
    """Configures the Gemini client with the next available key."""
    api_key = get_next_api_key()
    genai.configure(api_key=api_key)
    print(f"Using API Key ending with: ...{api_key[-4:]}")
    return genai.GenerativeModel(GEMINI_MODEL)

# Removed update_progress function

def safe_filename(text):
    """Creates a safe filename from text."""
    text = re.sub(r'[\\/*?:"<>|]', "", text) # Remove invalid chars
    text = text.replace(' ', '_')
    return text[:100] # Limit length

# --- Core Agent Functions (Modified to remove status_update_func) ---

def find_and_assess_topic(model):
    """Identifies a trending tech topic and assesses its viability."""
    print("Finding and assessing trending tech topic...")
    # status_update_func('status', {'message': f"Searching for trending tech topics ({TREND_SOURCE_HINT})..."}) # Removed
    prompt = (
        f"Identify 3-5 current trending topics in technology, particularly those gaining traction on platforms like YouTube or major tech news sites ({TREND_SOURCE_HINT}). "
        f"For each topic, briefly explain why it's trending.\n"
        f"Then, select the ONE topic you think has the most potential for a {NUM_EPISODES_MIN}-{NUM_EPISODES_MAX} episode podcast series that progresses from foundational concepts to more advanced aspects. "
        f"Finally, assess the selected topic's viability: list 3-5 potential sub-topics or angles that could be covered across the series to demonstrate its depth.\n\n"
        f"Format your response clearly:\n"
        f"Trending Topics:\n"
        f"1. [Topic 1]: [Reason]\n"
        f"2. [Topic 2]: [Reason]\n"
        f"...\n\n"
        f"Selected Topic: [Selected Topic Name]\n\n"
        f"Viability Assessment (Sub-topics/Angles):\n"
        f"- [Angle 1]\n"
        f"- [Angle 2]\n"
        f"- [Angle 3]\n"
        f"..."
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts:
             raise ValueError("Topic identification failed. Response empty/blocked.")
        assessment_text = response.text.strip()
        print(f"Topic Assessment:\n{assessment_text}\n")

        selected_topic_match = re.search(r"Selected Topic:(.*?)(\n\n|$)", assessment_text, re.IGNORECASE | re.DOTALL)
        if not selected_topic_match:
            first_topic_match = re.search(r"1\.\s*\[?(.*?)]?:", assessment_text, re.IGNORECASE)
            if first_topic_match:
                selected_topic = first_topic_match.group(1).strip()
                print(f"Warning: Could not parse 'Selected Topic'. Using first topic found: '{selected_topic}'")
            else:
                raise ValueError("Could not parse selected topic from assessment.")
        else:
            selected_topic = selected_topic_match.group(1).strip()

        # status_update_func('status', {'message': f"Topic selected: '{selected_topic}'. Assessing viability..."}) # Removed

        if "Viability Assessment" not in assessment_text or len(re.findall(r"-\s*\[", assessment_text)) < 2:
             print(f"Warning: Viability assessment for '{selected_topic}' seems limited. Proceeding cautiously.")
             # status_update_func('status', {'message': f"Warning: Viability assessment for '{selected_topic}' seems limited."}) # Removed
        # else:
             # status_update_func('status', {'message': f"Topic '{selected_topic}' assessed as viable."}) # Removed

        return selected_topic
    except Exception as e:
        print(f"Error finding/assessing topic: {e}")
        # status_update_func('error', {'message': f"Error finding/assessing topic: {e}"}) # Removed
        raise

def generate_podcast_outline(model, topic, num_episodes):
    """Generates the podcast series outline."""
    print(f"Generating {num_episodes}-episode outline for topic: {topic}...")
    # status_update_func('status', {'message': f"Generating {num_episodes}-episode outline for '{topic}'..."}) # Removed
    prompt = (
        f"Create a detailed outline for a {num_episodes}-episode podcast series about '{topic}'. "
        f"The series should start with foundational concepts and progressively build towards more advanced aspects or specific applications. "
        f"Avoid making the early episodes too basic or boring for a tech-savvy audience, but ensure a logical flow.\n"
        f"For each episode (1 to {num_episodes}), provide:\n"
        f"- Episode Title: A catchy and informative title.\n"
        f"- Key Points: 3-5 bullet points summarizing the main content or discussion points for the episode.\n\n"
        f"Format the output clearly, starting each episode with 'Episode X: [Title]'."
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts:
             raise ValueError("Outline generation failed. Response empty/blocked.")
        outline_text = response.text.strip()

        with open(OUTLINE_FILE, 'w', encoding='utf-8') as f:
            f.write(outline_text)
        print(f"Podcast outline saved to {OUTLINE_FILE}")
        # status_update_func('status', {'message': f"Podcast outline saved to {OUTLINE_FILE}"}) # Removed
        return outline_text
    except Exception as e:
        print(f"Error generating podcast outline: {e}")
        # status_update_func('error', {'message': f"Error generating podcast outline: {e}"}) # Removed
        raise

def parse_podcast_outline(outline_text):
    """Parses the generated podcast outline text."""
    print("Parsing podcast outline...")
    # status_update_func('status', {'message': 'Parsing generated outline...'}) # Removed
    episodes = []
    try:
        episode_sections = re.split(r'\nEpisode \d+:', '\n' + outline_text, flags=re.IGNORECASE)
        if len(episode_sections) > 1:
            episode_sections = episode_sections[1:]
        else:
            raise ValueError("Could not split outline into episodes using 'Episode X:' pattern.")

        print(f"Found {len(episode_sections)} potential episode sections.")

        for i, section in enumerate(episode_sections):
             episode_num = i + 1
             section = section.strip()
             if not section: continue

             title_match = re.match(r'\s*(.*?)\s*(\n|$)', section)
             title = title_match.group(1).strip().strip('*') if title_match else f"Episode {episode_num}"

             points_match = re.search(r'Key Points:(.*)', section, re.IGNORECASE | re.DOTALL)
             key_points = points_match.group(1).strip() if points_match else "No key points found."

             episodes.append({
                 "number": episode_num,
                 "title": title,
                 "key_points": key_points,
                 "full_section": section
             })

        if not episodes:
             raise ValueError("Outline parsing failed to extract any episode details.")

        print(f"Successfully parsed {len(episodes)} episodes.")
        # status_update_func('status', {'message': f"Parsed {len(episodes)} episodes from outline."}) # Removed
        return episodes
    except Exception as e:
        print(f"Error parsing podcast outline: {e}")
        # status_update_func('error', {'message': f"Error parsing podcast outline: {e}. Check {OUTLINE_FILE}."}) # Removed
        raise

def generate_episode_pdf(model, episode_details, series_topic, total_episodes):
    """Generates content for a single episode and saves it as a PDF."""
    episode_num = episode_details['number']
    episode_title = episode_details['title']
    key_points = episode_details['key_points']
    print(f"Generating Episode {episode_num}/{total_episodes}: {episode_title}...")
    # status_update_func('status', {'message': f"Generating Episode {episode_num}/{total_episodes}: {episode_title}..."}) # Removed

    prompt = (
        f"You are writing the script content for Episode {episode_num} of a podcast series about '{series_topic}'.\n"
        f"Episode Title: \"{episode_title}\"\n"
        f"Key Discussion Points for this Episode:\n{key_points}\n\n"
        f"Write the content for this episode, aiming for approximately {TARGET_WORD_COUNT_MIN}-{TARGET_WORD_COUNT_MAX} words. "
        f"Structure it like a podcast segment or script, focusing on clarity and engaging language suitable for a tech audience. "
        f"Build upon concepts potentially introduced in previous episodes (assume logical progression) but focus on this episode's key points. "
        f"Start the content directly, perhaps with a brief intro referencing the episode title or number."
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts:
             raise ValueError(f"Episode {episode_num} generation failed. Response empty/blocked.")
        episode_content = response.text.strip()

        pdf_filename_base = safe_filename(f"{series_topic}_Ep{episode_num}_{episode_title}")
        pdf_filename = f"{pdf_filename_base}.pdf"
        output_path = os.path.join(PODCAST_DIR, pdf_filename)

        doc = SimpleDocTemplate(output_path, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"Episode {episode_num}: {episode_title}", styles['h1']))
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(f"(Series: {series_topic})", styles['h3']))
        story.append(Spacer(1, 0.5*inch))

        paragraphs = episode_content.split('\n\n')
        for para_text in paragraphs:
            para_text = para_text.strip()
            if para_text:
                para_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', para_text)
                para_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', para_text)
                story.append(Paragraph(para_text.replace('\n', '<br/>'), styles['Normal']))
                story.append(Spacer(1, 0.1*inch))

        doc.build(story)
        print(f"Episode {episode_num} PDF saved to {output_path}")
        return output_path # Return the full path

    except Exception as e:
        print(f"Error generating Episode {episode_num} ('{episode_title}'): {e}")
        # status_update_func('error', {'message': f"Error generating content or PDF for Episode {episode_num}: {e}"}) # Removed
        raise # Re-raise to be caught by the main loop/wrapper

# --- Main Pipeline Function (Refactored for API polling) ---

def run_podcast_pipeline():
    """The main pipeline logic, callable from Flask, returns result dict."""
    global current_api_key_index
    current_api_key_index = 0 # Reset key index

    all_pdf_filenames = [] # Store just filenames for the result

    # Wrap the entire process in a try...except block to return final status
    try:
        print("Starting Autonomous Podcast Pipeline...")
        # status_update_func('status', {'message': 'Podcast Agent started...'}) # Removed

        # 0. Auto-Clean & Initial Setup
        print("--- Step 0: Cleaning Up Previous Run ---")
        # status_update_func('status', {'message': 'Cleaning up previous run...'}) # Removed
        if os.path.exists(OUTLINE_FILE):
            try: os.remove(OUTLINE_FILE); print(f"Removed old outline: {OUTLINE_FILE}")
            except Exception as e: print(f"Warning: Could not remove {OUTLINE_FILE}: {e}")
        if os.path.exists(PODCAST_DIR):
            try: shutil.rmtree(PODCAST_DIR); print(f"Removed old podcast dir: {PODCAST_DIR}")
            except Exception as e: print(f"Warning: Could not remove {PODCAST_DIR}: {e}")
        os.makedirs(PODCAST_DIR, exist_ok=True)
        # update_progress(status_update_func, 0, 0) # Removed

        # 1. Find & Assess Topic
        print("--- Step 1: Finding Topic ---")
        model = configure_gemini()
        series_topic = find_and_assess_topic(model) # Removed status_update_func
        if not series_topic: raise ValueError("Failed to determine podcast topic.")

        # 2. Generate Outline
        print("\n--- Step 2: Generating Outline ---")
        num_episodes = random.randint(NUM_EPISODES_MIN, NUM_EPISODES_MAX)
        model = configure_gemini()
        outline_text = generate_podcast_outline(model, series_topic, num_episodes) # Removed status_update_func
        if not outline_text: raise ValueError("Failed to generate podcast outline.")

        # 3. Parse Outline
        print("\n--- Step 3: Parsing Outline ---")
        episodes_data = parse_podcast_outline(outline_text) # Removed status_update_func
        if not episodes_data: raise ValueError("Failed to parse podcast outline.")
        actual_total_episodes = len(episodes_data)
        # update_progress(status_update_func, 0, actual_total_episodes) # Removed

        # 4. Generate Episodes & PDFs
        print("\n--- Step 4: Generating Episodes ---")
        # status_update_func('status', {'message': f"Starting generation of {actual_total_episodes} podcast episodes..."}) # Removed
        completed_episodes = 0
        for i, episode_info in enumerate(episodes_data):
            print(f"--- Generating Episode {i+1}/{actual_total_episodes} ---") # Console progress
            model = configure_gemini()
            pdf_path = generate_episode_pdf(model, episode_info, series_topic, actual_total_episodes) # Removed status_update_func
            if pdf_path:
                all_pdf_filenames.append(os.path.basename(pdf_path))
                completed_episodes += 1
                # update_progress(status_update_func, completed_episodes, actual_total_episodes) # Removed
                # time.sleep(1) # Optional delay
            else:
                 raise ValueError(f"Failed to generate PDF for episode {episode_info.get('number', i+1)}.")

        # 5. Completion
        print("\n--- Step 5: Finalizing ---")
        if completed_episodes == actual_total_episodes:
            print("\nPodcast series generation complete!")
            final_message = f"Successfully generated {actual_total_episodes} podcast episode PDFs for '{series_topic}'."
            # status_update_func('status', {'message': final_message}) # Removed
            return {"status": "success", "message": final_message, "pdf_filenames": all_pdf_filenames}
        else:
            raise RuntimeError(f"Inconsistency: Completed {completed_episodes}/{actual_total_episodes} episodes.")

    except Exception as e:
        print(f"Podcast pipeline failed: {e}")
        error_message = f"Podcast pipeline failed: {e}"
        # status_update_func('error', {'message': error_message}) # Removed
        return {"status": "error", "message": error_message, "pdf_filenames": all_pdf_filenames}
