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

# Import necessary components using absolute paths from the project root (book_pipeline)
from main import configure_gemini, safe_filename # Absolute import
from config import (
    PODCAST_DIR, PODCAST_OUTLINE_FILE,
    NUM_EPISODES_MIN, NUM_EPISODES_MAX, # Absolute import from config
    PODCAST_TARGET_WORD_MIN, PODCAST_TARGET_WORD_MAX,
    TREND_SOURCE_HINT
)

# ==============================================
# === PODCAST GENERATION LOGIC             ===
# ==============================================

def podcast_find_and_assess_topic(model):
    """Identifies a trending tech topic and assesses its viability."""
    print("Finding and assessing trending tech topic...")
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
        if not response.parts: raise ValueError("Podcast topic identification failed.")
        assessment_text = response.text.strip()
        print(f"Podcast Topic Assessment:\n{assessment_text}\n")
        selected_topic_match = re.search(r"Selected Topic:(.*?)(\n\n|$)", assessment_text, re.IGNORECASE | re.DOTALL)
        if not selected_topic_match:
            first_topic_match = re.search(r"1\.\s*\[?(.*?)]?:", assessment_text, re.IGNORECASE)
            if first_topic_match:
                selected_topic = first_topic_match.group(1).strip()
                print(f"Warning: Could not parse 'Selected Topic'. Using first topic: '{selected_topic}'")
            else: raise ValueError("Could not parse selected podcast topic.")
        else: selected_topic = selected_topic_match.group(1).strip().strip('*') # Also strip potential bold markers
        if "Viability Assessment" not in assessment_text or len(re.findall(r"-\s*\[", assessment_text)) < 2:
             print(f"Warning: Podcast viability assessment for '{selected_topic}' seems limited.")
        return selected_topic
    except Exception as e:
        print(f"Error finding/assessing podcast topic: {e}")
        raise

def podcast_generate_outline(model, topic, num_episodes):
    """Generates the podcast series outline."""
    print(f"Generating {num_episodes}-episode podcast outline for topic: {topic}...")
    prompt = (
        f"Create a detailed outline for a {num_episodes}-episode podcast series about '{topic}'. "
        f"The series should start with foundational concepts and progressively build towards more advanced aspects or specific applications. "
        f"Avoid making the early episodes too basic or boring for a tech-savvy audience, but ensure a logical flow.\n"
        f"For each episode (1 to {num_episodes}), provide:\n"
        f"- Episode Title: A catchy and informative title.\n"
        f"- Key Points: 3-5 bullet points summarizing the main content or discussion points for the episode.\n\n"
        f"Format the output clearly, starting each episode with '**Episode X: [Title]**' on its own line." # Updated format instruction
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts: raise ValueError("Podcast outline generation failed.")
        outline_text = response.text.strip()
        # Clean potential markdown section headers
        outline_text = re.sub(r'^\s*\*+\s*Phase \d+:.*?\*+\s*\n?', '', outline_text, flags=re.IGNORECASE | re.MULTILINE)
        outline_text = re.sub(r'^\s*\*+\s*Step \d+:.*?\*+\s*\n?', '', outline_text, flags=re.IGNORECASE | re.MULTILINE)
        with open(PODCAST_OUTLINE_FILE, 'w', encoding='utf-8') as f: f.write(outline_text.strip())
        print(f"Podcast outline saved to {PODCAST_OUTLINE_FILE}")
        return outline_text.strip()
    except Exception as e:
        print(f"Error generating podcast outline: {e}")
        raise

def podcast_parse_outline(outline_text):
    """Parses the generated podcast outline text using a line-by-line approach (v5)."""
    print("Parsing podcast outline (Line-by-Line approach v5)...")
    episodes = []
    current_episode_lines = []
    episode_num_counter = 0
    # Regex to find potential episode headers at the start of a line
    # Regex specifically for '**Episode X: Title**' or similar, allowing optional surrounding whitespace
    # It also captures the number (group 1) and title (group 2)
    header_pattern = re.compile(
        r'^\s*\*{2}Episode\s+(\d+)\s*:\s*(.*?)\s*\*{0,2}\s*$', # More specific pattern
        flags=re.IGNORECASE
    )
    # Keep numbered list pattern for potential fallback/alternative formats if needed later
    numbered_list_pattern = re.compile(r'^\s*(\d+)\.\s+(.*)')

    lines = outline_text.strip().split('\n')
    in_episode_block = False # Flag to track if we are inside a potential episode block

    for idx, line in enumerate(lines):
        line_strip = line.strip()
        if not line_strip: # Skip empty lines between blocks
            continue

        header_match = header_pattern.match(line_strip)
        numbered_match = numbered_list_pattern.match(line_strip)

        is_new_header = False
        if header_match:
            is_new_header = True
            print(f"  Line {idx}: Found 'Episode X:' pattern.")
        elif numbered_match and not in_episode_block: # Only treat numbered list as header if not already inside an episode
             # Check if the content looks like a title rather than a detail point
             potential_title = numbered_match.group(2).strip()
             if not re.match(r'(Summary|Key Points|Emotional Arc|Reveal|Title)\s*:', potential_title, re.IGNORECASE):
                  is_new_header = True
                  print(f"  Line {idx}: Found numbered list pattern potentially starting an episode.")
             else:
                  print(f"  Line {idx}: Numbered list item looks like a detail point, ignoring as header.")

        if is_new_header:
            # Process the previous block if it exists
            if current_episode_lines:
                episode_num_counter += 1
                section_text = "\n".join(current_episode_lines).strip()
                parsed_episode = parse_single_podcast_section(section_text, episode_num_counter)
                if parsed_episode:
                    episodes.append(parsed_episode)

            # Start the new episode block
            current_episode_lines = [line] # Include the header line
            in_episode_block = True
        elif in_episode_block:
            # Append line to the current episode block
            current_episode_lines.append(line)
        else:
            # Skip lines before the first recognized header
            print(f"  Skipping line {idx} before first header: '{line_strip}'")


    # Process the very last episode block after the loop finishes
    if current_episode_lines:
        episode_num_counter += 1
        section_text = "\n".join(current_episode_lines).strip()
        parsed_episode = parse_single_podcast_section(section_text, episode_num_counter)
        if parsed_episode:
            episodes.append(parsed_episode)

    if not episodes:
        raise ValueError("Podcast outline parsing failed: No episode sections could be identified.")

    print(f"Successfully parsed {len(episodes)} podcast episodes.")
    return episodes


def parse_single_podcast_section(section_text, expected_episode_num):
    """Helper function to parse details from a single episode's text block."""
    print(f"  Processing section for Episode {expected_episode_num}...")
    title = f"Episode {expected_episode_num}" # Default title
    key_points = "No key points found."
    lines = section_text.split('\n')
    first_line = lines[0].strip()

    # Extract Title from the first line (which should be the header)
    # Regex tries to capture content after potential markers like "Episode X:", "N.", "#", "**" etc.
    title_match_marker = re.match(r'^\s*(?:#\s*|\*{1,2})?(?:Episode|Chapter)\s+\d+\s*:?\*{0,2}\s*|(?:\d+\.\s+)?\s*(.*?)\s*$', first_line, flags=re.IGNORECASE)

    if title_match_marker and title_match_marker.group(1):
        potential_title = title_match_marker.group(1).strip().strip('*:') # Strip extra chars
        if potential_title and not re.match(r'(Key Points)\s*:', potential_title, re.IGNORECASE):
            title = potential_title
            print(f"    Parsed title: '{title}'")
        else: print(f"    Header line content ('{potential_title}') unusable or is 'Key Points:', using default title.")
    else: print(f"    Could not parse title from header line ('{first_line}'), using default title.")

    # Extract Key Points (look for the label and subsequent list items in the rest of the section)
    key_points_started = False
    point_lines = []
    key_points_section_match = re.search(r'Key Points:(.*)', section_text, re.IGNORECASE | re.DOTALL)
    if key_points_section_match:
        raw_points_text = key_points_section_match.group(1)
        for line in raw_points_text.split('\n'):
            line_strip = line.strip()
            if line_strip.startswith(('-', '*')) or (key_points_started and line_strip):
                 point_lines.append(line_strip)
                 key_points_started = True
            elif not key_points_started and line_strip: # First non-empty line after label
                 point_lines.append(line_strip)
                 key_points_started = True
            elif key_points_started and not line_strip:
                 continue # Allow empty lines between points

        if point_lines:
            points_text = "\n".join(point_lines).strip()
            print(f"    Extracted Key Points.")
        else:
            print(f"    'Key Points:' label found, but no list items detected after it.")
    else:
        print(f"    'Key Points:' label not found in section.")

    return {
        "number": expected_episode_num,
        "title": title,
        "key_points": points_text,
        "full_section": section_text # Keep the original block
    }


def podcast_generate_episode_pdf(model, episode_details, series_topic, total_episodes):
    """Generates content for a single podcast episode and saves it as a PDF."""
    episode_num = episode_details['number']
    episode_title = episode_details['title']
    key_points = episode_details['key_points']
    print(f"Generating Podcast Episode {episode_num}/{total_episodes}: {episode_title}...")
    prompt = (
        f"You are writing the script content for Episode {episode_num} of a podcast series about '{series_topic}'.\n"
        f"Episode Title: \"{episode_title}\"\n"
        f"Key Discussion Points for this Episode:\n{key_points}\n\n"
        f"Write the content for this episode, aiming for approximately {PODCAST_TARGET_WORD_MIN}-{PODCAST_TARGET_WORD_MAX} words. "
        f"Structure it like a podcast segment or script, focusing on clarity and engaging language suitable for a tech audience. "
        f"Build upon concepts potentially introduced in previous episodes (assume logical progression) but focus on this episode's key points. "
        f"Start the content directly, perhaps with a brief intro referencing the episode title or number. Do NOT include section headers like 'Introduction', 'Main Content', 'Conclusion' unless they are natural parts of the spoken script."
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts: raise ValueError(f"Podcast Episode {episode_num} generation failed.")
        episode_content = response.text.strip()
        pdf_filename_base = safe_filename(f"{series_topic}_Ep{episode_num}_{episode_title}")
        pdf_filename = f"{pdf_filename_base}.pdf"
        output_path = os.path.join(PODCAST_DIR, pdf_filename)
        doc = SimpleDocTemplate(output_path, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch)
        styles = getSampleStyleSheet()
        story = []
        # Simplified PDF: Just Title and Content Paragraphs
        story.append(Paragraph(f"Episode {episode_num}: {episode_title}", styles['h1']))
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
        print(f"Podcast Episode {episode_num} PDF saved to {output_path}")
        return output_path # Return the full path
    except Exception as e:
        print(f"Error generating Podcast Episode {episode_num} ('{episode_title}'): {e}")
        raise

def run_podcast_pipeline():
    """Main pipeline logic for podcast generation. Returns result dict."""
    global current_api_key_index
    current_api_key_index = 0
    all_pdf_filenames = []
    try:
        print("Starting Autonomous Podcast Pipeline...")
        print("--- Step 0: Cleaning Up Previous Podcast Run ---")
        if os.path.exists(PODCAST_OUTLINE_FILE):
            try: os.remove(PODCAST_OUTLINE_FILE); print(f"Removed old podcast outline: {PODCAST_OUTLINE_FILE}")
            except Exception as e: print(f"Warning: Could not remove {PODCAST_OUTLINE_FILE}: {e}")
        if os.path.exists(PODCAST_DIR):
            try: shutil.rmtree(PODCAST_DIR); print(f"Removed old podcast dir: {PODCAST_DIR}")
            except Exception as e: print(f"Warning: Could not remove {PODCAST_DIR}: {e}")
        os.makedirs(PODCAST_DIR, exist_ok=True)

        print("--- Step 1: Finding Podcast Topic ---")
        model = configure_gemini()
        series_topic = podcast_find_and_assess_topic(model)
        if not series_topic: raise ValueError("Failed to determine podcast topic.")

        print("\n--- Step 2: Generating Podcast Outline ---")
        num_episodes = random.randint(NUM_EPISODES_MIN, NUM_EPISODES_MAX)
        model = configure_gemini()
        outline_text = podcast_generate_outline(model, series_topic, num_episodes)
        if not outline_text: raise ValueError("Failed to generate podcast outline.")

        print("\n--- Step 3: Parsing Podcast Outline ---")
        episodes_data = podcast_parse_outline(outline_text) # Use the corrected function
        if not episodes_data: raise ValueError("Failed to parse podcast outline.")
        actual_total_episodes = len(episodes_data)

        print("\n--- Step 4: Generating Podcast Episodes ---")
        completed_episodes = 0
        for i, episode_info in enumerate(episodes_data):
            print(f"--- Generating Podcast Episode {i+1}/{actual_total_episodes} ---") # Log loop iteration
            model = configure_gemini()
            pdf_path = podcast_generate_episode_pdf(model, episode_info, series_topic, actual_total_episodes)
            if pdf_path:
                all_pdf_filenames.append(os.path.basename(pdf_path))
                completed_episodes += 1
                print(f"    Successfully generated PDF: {os.path.basename(pdf_path)}") # Log success
            else:
                # This path shouldn't be reached if generate_episode_pdf raises on error
                print(f"    Skipping PDF for episode {i+1} due to generation error.")
                raise ValueError(f"Failed to generate PDF for podcast episode {episode_info.get('number', i+1)}.")

        print("\n--- Step 5: Finalizing Podcast ---")
        if completed_episodes == actual_total_episodes:
            print(f"\nPodcast series generation complete! {completed_episodes} PDFs generated.")
            final_message = f"Successfully generated {actual_total_episodes} podcast episode PDFs for '{series_topic}'."
            return {"status": "success", "message": final_message, "pdf_filenames": all_pdf_filenames}
        else: raise RuntimeError(f"Podcast Inconsistency: Completed {completed_episodes}/{actual_total_episodes} episodes.")
    except Exception as e:
        print(f"Podcast pipeline failed: {e}")
        return {"status": "error", "message": f"Podcast pipeline failed: {e}", "pdf_filenames": all_pdf_filenames}
