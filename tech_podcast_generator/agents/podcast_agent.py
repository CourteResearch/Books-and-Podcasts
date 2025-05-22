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

# Import necessary components using relative paths
# Go up two levels (from agents -> tech_podcast_generator -> Books_and_Podcasts)
# then into ebook_generator
from ...ebook_generator.main import configure_gemini, safe_filename # Relative import
from ...ebook_generator.config import ( # Relative import from ebook_generator config
    PODCAST_DIR, PODCAST_OUTLINE_FILE,
    NUM_EPISODES_MIN, NUM_EPISODES_MAX,
    PODCAST_TARGET_WORD_MIN, PODCAST_TARGET_WORD_MAX,
    TREND_SOURCE_HINT
)

# ==============================================
# === PODCAST GENERATION LOGIC             ===
# ==============================================

def podcast_find_and_assess_topic(model):
    """Identifies several trending tech topics suitable for a YouTube podcast audience."""
    print("Finding engaging tech topics suitable for YouTube...")
    prompt = (
    f"Act like a YouTube growth strategist and tech trend analyst. Identify **5-7 ultra-specific, high-impact tech topics** that are ideal for a {NUM_EPISODES_MIN}-{NUM_EPISODES_MAX} episode podcast series designed to capture attention on **YouTube**.\n\n"
    
    f"Each topic should:\n"
    f"- Be **based on current discussions** within the **last 1–3 months** from YouTube trends, Hacker News, Reddit (/r/technology, /r/programming), or popular tech news sources ({TREND_SOURCE_HINT}).\n"
    f"- Be **SEO-optimized**: use keyword-rich titles or phrasing that aligns with how people search on YouTube.\n"
    f"- Have **clear hooks**: controversial opinions, paradigm shifts, ethical dilemmas, hype vs. reality, or deep dives into emerging technologies.\n"
    f"- Be **specific enough** to create 7-10 tightly focused episodes (e.g. 'OpenAI vs Google AI arms race' instead of 'AI evolution').\n"
    f"- Be **visually rich** and conceptually engaging for YouTube (e.g. demos, visual storytelling, diagrams, real-world case studies).\n\n"

    f"For each suggested topic:\n"
    f"- Provide a **title** that’s YouTube-optimized.\n"
    f"- Explain **why it's trending**, with a specific platform or source.\n"
    f"- Suggest **episode breakdown ideas** or angles that can span a mini-series.\n\n"

    f"**Avoid:**\n"
    f"- Broad, evergreen topics with no fresh angle.\n"
    f"- Overly academic or niche discussions with no general interest.\n"
    f"- Buzzwords without substance (e.g., 'AI is the future' with no angle).\n\n"

    f"Format:\n"
    f"1. [SEO-optimized clickable topic title]\n"
    f"   - Why it's trending right now (with source or evidence)\n"
    f"   - Multi-episode angle breakdown or key talking points\n"
    f"2. ..."
)

    try:
        # Add a safety setting to potentially reduce repetitive outputs, if supported by the model/API version
        # Note: This might need adjustment based on the specific genai library version and model capabilities.
        # Example using hypothetical 'temperature' or 'top_p' if available:
        # generation_config = genai.types.GenerationConfig(temperature=0.8, top_p=0.9)
        # response = model.generate_content(prompt, generation_config=generation_config)
        # If specific safety settings are available:
        # safety_settings=[
        #     { "category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_LOW_AND_ABOVE" },
        #     { "category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_LOW_AND_ABOVE" },
        # ]
        # response = model.generate_content(prompt, safety_settings=safety_settings)
        # --- Using default generation for now ---
        response = model.generate_content(prompt)
        if not response.parts: raise ValueError("Podcast topic identification failed.")
        topic_list_text = response.text.strip()
        print(f"Potential Podcast Topics Found:\n{topic_list_text}\n")

        # Extract topics using regex (find lines starting with number and period)
        potential_topics = re.findall(r"^\s*\d+\.\s*\[?(.*?)]?:\s*.*", topic_list_text, re.MULTILINE | re.IGNORECASE)

        if not potential_topics:
            # Fallback: Try to extract lines that seem like topics if the primary regex fails
            potential_topics = [line.split(':')[0].strip() for line in topic_list_text.split('\n') if ':' in line and len(line) > 10]
            if not potential_topics:
                raise ValueError("Could not parse any potential podcast topics from the response.")
            print(f"Warning: Used fallback topic parsing. Found: {potential_topics}")

        # Clean up extracted topic names (remove potential leading/trailing junk)
        potential_topics = [topic.strip().strip('*[]') for topic in potential_topics]

        if not potential_topics:
             raise ValueError("No valid topics extracted after cleaning.")

        # Randomly select one topic
        selected_topic = random.choice(potential_topics)
        print(f"Randomly selected topic: '{selected_topic}'")
        return selected_topic
    except Exception as e:
        print(f"Error finding/selecting podcast topic: {e}")
        raise


# --- New function to generate only the topic ---
def generate_podcast_topic():
    """Generates and returns a potential podcast topic."""
    print("--- Step 1: Finding Podcast Topic ---")
    try:
        model = configure_gemini()
        series_topic = podcast_find_and_assess_topic(model)
        if not series_topic:
            raise ValueError("Failed to determine podcast topic.")
        print(f"Proposed Podcast Topic: '{series_topic}'")
        return series_topic
    except Exception as e:
        print(f"Error during topic generation: {e}")
        raise # Re-raise the exception to be caught by the caller

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
        
        # --- Save Markdown File ---
        md_filename_base = safe_filename(f"{series_topic}_Ep{episode_num}_{episode_title}")
        md_filename = f"{md_filename_base}.md"
        md_output_path = os.path.join(PODCAST_DIR, md_filename)
        try:
            with open(md_output_path, 'w', encoding='utf-8') as md_file:
                md_file.write(episode_content)
            print(f"Podcast Episode {episode_num} Markdown saved to {md_output_path}")
        except Exception as e_md:
            print(f"Error saving Podcast Episode {episode_num} Markdown: {e_md}")
            # Decide if this should be a fatal error or just a warning
            # For now, let PDF generation continue

        # --- PDF Generation ---
        pdf_filename_base = safe_filename(f"{series_topic}_Ep{episode_num}_{episode_title}") # Keep separate for clarity or if base needs to differ
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

# --- Modified function to run the pipeline *after* topic approval ---
def run_podcast_pipeline(series_topic):
    """Main pipeline logic for podcast generation, starting *after* topic approval.
       Accepts the approved topic as an argument. Returns result dict."""
    # Note: API key index handling might need review if calls are split across requests
    # For now, assume configure_gemini handles it per call.
    all_pdf_filenames = []
    try:
        print(f"Starting Autonomous Podcast Pipeline for topic: '{series_topic}'...")
        print("--- Step 0: Cleaning Up Previous Podcast Run ---")
        
        # Robust directory cleanup and creation
        if os.path.exists(PODCAST_OUTLINE_FILE):
            try:
                os.remove(PODCAST_OUTLINE_FILE)
                print(f"Removed old podcast outline: {PODCAST_OUTLINE_FILE}")
            except Exception as e:
                print(f"Warning: Could not remove old podcast outline {PODCAST_OUTLINE_FILE}: {e}")

        if os.path.exists(PODCAST_DIR):
            print(f"Cleaning up existing podcast directory: {PODCAST_DIR}")
            for item_name in os.listdir(PODCAST_DIR):
                item_path = os.path.join(PODCAST_DIR, item_name)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path) # Remove file or link
                        print(f"  Removed old file: {item_path}")
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path) # Remove subdirectory and its contents
                        print(f"  Removed old subdirectory: {item_path}")
                except Exception as e_clean:
                    print(f"  Warning: Could not remove item {item_path}: {e_clean}")
            # After cleaning contents, ensure the base directory itself exists.
            # os.makedirs will ensure it exists without error if it's already there.
        os.makedirs(PODCAST_DIR, exist_ok=True)
        print(f"Ensured podcast directory exists: {PODCAST_DIR}")

        # --- Step 1 (Topic Finding) is now done *before* calling this function ---
        print(f"\n--- Step 2: Generating Podcast Outline for '{series_topic}' ---")
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
