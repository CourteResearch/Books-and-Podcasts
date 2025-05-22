import google.generativeai as genai
import os
import time
import re
import shutil
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Frame
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus.flowables import KeepInFrame
import requests # Keep for potential future use

# Import config - Use the renamed variables
from .config import ( # Use relative import
    GEMINI_API_KEYS, GEMINI_MODEL,
    # Ebook specific
    EBOOK_CHAPTERS_DIR, EBOOK_OUTLINE_FILE, EBOOK_TOTAL_CHAPTERS,
    EBOOK_TARGET_WORD_MIN, EBOOK_TARGET_WORD_MAX,
    # Podcast specific
    PODCAST_DIR, PODCAST_OUTLINE_FILE, # These should already exist with these names in config
    NUM_EPISODES_MIN, NUM_EPISODES_MAX,
    PODCAST_TARGET_WORD_MIN, PODCAST_TARGET_WORD_MAX,
    TREND_SOURCE_HINT
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

def safe_filename(text):
    """Creates a safe filename from text."""
    text = re.sub(r'[\\/*?:"<>|]', "", text) # Remove invalid chars
    text = text.replace(' ', '_')
    return text[:100] # Limit length

# ===========================================
# === EBOOK GENERATION LOGIC (Refactored) ===
# ===========================================

def ebook_generate_outline(model, instructional_prompt):
    """Generates the book outline using the provided instructional prompt."""
    print("Generating ebook outline...")
    try:
        response = model.generate_content(instructional_prompt)
        if not response.parts:
             raise ValueError("Ebook outline generation failed. Response empty/blocked.")
        outline_text = response.text
        with open(EBOOK_OUTLINE_FILE, 'w', encoding='utf-8') as f:
            f.write(outline_text)
        print(f"Ebook outline saved to {EBOOK_OUTLINE_FILE}")
        return outline_text
    except Exception as e:
        print(f"Error generating ebook outline: {e}")
        raise

def ebook_conceptualize_idea(model, genre="Thriller"):
    """Uses Gemini to brainstorm a book title and premise."""
    print(f"Conceptualizing ebook idea for genre: {genre}...")
    prompt = (
        f"You are a creative assistant. Brainstorm a compelling book concept for the genre '{genre}'. "
        f"The book should be engaging and suitable for publication on platforms like Amazon KDP. "
        f"Provide only the following, in this exact format:\n"
        f"Title: [Your Book Title Here]\n"
        f"Premise: [A 1-2 sentence gripping premise for the book]"
    )
    try:
        # Safety settings might differ for brainstorming vs writing
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            # Add others as needed
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts:
             raise ValueError("Ebook conceptualization failed. Response empty/blocked.")
        concept_text = response.text.strip()
        print(f"Generated Ebook Concept:\n{concept_text}")

        title_match = re.search(r"Title:(.*?)(?:\nPremise:|$)", concept_text, re.IGNORECASE | re.DOTALL)
        premise_match = re.search(r"Premise:(.*)", concept_text, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip().strip('"\'') if title_match else "Untitled Ebook"
        premise = premise_match.group(1).strip() if premise_match else "No premise generated."
        return {"title": title, "premise": premise}
    except Exception as e:
        print(f"Error during ebook conceptualization: {e}")
        raise

def ebook_generate_instructional_prompt(model, book_title, book_premise, genre="Thriller"):
    """Generates the detailed instructional prompt for the ebook writer AI."""
    print(f"Generating ebook instructional prompt for genre: {genre}...")
    num_chapters_to_request = EBOOK_TOTAL_CHAPTERS
    
    genre_specific_tone = "a dark, suspenseful, emotional tone consistent with a thriller"
    if genre.lower() == "romance":
        genre_specific_tone = "an emotional, heartfelt, and engaging tone consistent with a romance novel"
    elif genre.lower() == "romantic thriller": # Keep specific if explicitly chosen
        genre_specific_tone = "a dark, suspenseful, emotional tone consistent with a romantic thriller"

    prompt = (
        f"You are a prompt engineer creating instructions for an expert AI writer specializing in {genre.lower()} novels.\n"
        f"The goal is to automate the creation of a complete {num_chapters_to_request}-chapter book suitable for publication.\n\n"
        f"Book Title: \"{book_title}\"\n"
        f"Book Premise: {book_premise}\n"
        f"Genre: {genre}\n\n"
        f"Generate a detailed, structured instructional prompt for the AI writer. The prompt MUST instruct the AI writer to perform the following steps sequentially:\n"
        f"1. Create a full {num_chapters_to_request}-chapter outline for the book \"{book_title}\". Each chapter outline must include: a 1-2 sentence summary, the emotional arc (appropriate for the genre), a key plot point (e.g., twist, reveal, romantic development), and a compelling chapter title.\n"
        f"2. For each chapter (1 to {num_chapters_to_request}), write {EBOOK_TARGET_WORD_MIN}-{EBOOK_TARGET_WORD_MAX} words using the corresponding outline details. The writing should begin directly in the scene, avoid repeating context from earlier chapters, maintain {genre_specific_tone}, avoid complex jargon unless essential, and start the chapter content with its generated title as a heading.\n"
        f"3. Treat the entire process as an automated workflow and complete all chapters.\n\n"
        f"The final output should be ONLY the instructional prompt itself, ready to be given to the writer AI. Start the prompt with 'You are an expert writer...' and mention the publisher 'Spellbind Studios'."
    )
    try:
        response = model.generate_content(prompt) # Assuming default safety is okay here
        if not response.parts:
             raise ValueError("Ebook instructional prompt generation failed.")
        instructional_prompt = response.text.strip()
        print("Generated Ebook Instructional Prompt (preview):")
        print(instructional_prompt[:300] + "...")
        return instructional_prompt
    except Exception as e:
        print(f"Error generating ebook instructional prompt: {e}")
        raise

def ebook_parse_outline(outline_text, genre="Thriller"): # Added genre for context if needed later
    """Parses the generated ebook outline text into a structured format. More robust version."""
    print("Parsing ebook outline...")
    chapters = []
    try:
        # Split by lines starting with "**Chapter X:**" or "# Chapter X:"
        # This regex captures the chapter number and the content following it until the next chapter marker or end of string.
        # It also handles the initial "## 1. Outline Creation" by skipping content before the first chapter.
        chapter_pattern = re.compile(r'^\s*(?:\*{2})?Chapter\s+(?P<num>\d+):(?:\*{2})?\s*(.*?)(?=\n\s*(?:\*{2})?Chapter\s+\d+:|\Z)', re.MULTILINE | re.IGNORECASE | re.DOTALL)
        
        matches = list(chapter_pattern.finditer(outline_text))

        if not matches:
            # Fallback for outlines that might start with "# Chapter X:"
            chapter_pattern_fallback = re.compile(r'^\s*#+\s*Chapter\s+(?P<num>\d+):?\s*(.*?)(?=\n\s*#+\s*Chapter\s+\d+:|\Z)', re.MULTILINE | re.IGNORECASE | re.DOTALL)
            matches = list(chapter_pattern_fallback.finditer(outline_text))
            if not matches:
                raise ValueError("Could not split ebook outline into chapters using any known patterns.")

        for match in matches:
            chapter_num = int(match.group('num'))
            section_content = match.group(2).strip()

            # Extract Title, Summary, Emotional Arc, Twist/Reveal using more specific regex
            title_match = re.search(r'\*?\s*Title:\s*\*\s*(.*?)(?:\n|$)', section_content, re.IGNORECASE)
            summary_match = re.search(r'\*?\s*Summary:\s*\*\s*(.*?)(?=\n\s*\*?\s*(?:Emotional Arc|Twist/Reveal|Title):|\Z)', section_content, re.DOTALL | re.IGNORECASE)
            arc_match = re.search(r'\*?\s*Emotional Arc:\s*\*\s*(.*?)(?=\n\s*\*?\s*(?:Summary|Twist/Reveal|Title):|\Z)', section_content, re.DOTALL | re.IGNORECASE)
            twist_match = re.search(r'\*?\s*(?:Key Twist|Twist/Reveal):\s*\*\s*(.*?)(?=\n\s*\*?\s*(?:Summary|Emotional Arc|Title):|\Z)', section_content, re.DOTALL | re.IGNORECASE)

            title = title_match.group(1).strip() if title_match else f"Chapter {chapter_num} Title Not Found"
            summary = summary_match.group(1).strip() if summary_match else "Summary not found."
            arc = arc_match.group(1).strip() if arc_match else "Emotional Arc not found."
            twist = twist_match.group(1).strip() if twist_match else "Twist/Reveal not found."

            chapters.append({
                "number": chapter_num,
                "title": title,
                "summary": summary,
                "arc": arc,
                "twist": twist,
                "full_section": section_content
            })

        if not chapters:
            raise ValueError("Ebook outline parsing failed to extract any chapter details after processing sections.")
        
        print(f"Successfully parsed {len(chapters)} ebook chapters.")
        return chapters
    except Exception as e:
        print(f"Error parsing ebook outline: {e}")
        raise

def ebook_generate_chapter(model, chapter_details, book_title, genre="Thriller"):
    """Generates content for a single ebook chapter."""
    chapter_num = chapter_details['number']
    chapter_title = chapter_details['title']
    print(f"Generating Ebook Chapter {chapter_num}: {chapter_title} (Genre: {genre})...")

    genre_specific_tone_instruction = "Maintain a dark, suspenseful, and emotional tone."
    if genre.lower() == "romance":
        genre_specific_tone_instruction = "Maintain an emotional, heartfelt, and engaging tone, focusing on character interactions and romantic development."
    elif genre.lower() == "romantic thriller":
         genre_specific_tone_instruction = "Maintain a dark, suspenseful, and emotional tone, balancing thriller elements with romantic development."

    key_plot_point_label = "Key Twist/Reveal" if genre.lower() != "romance" else "Key Plot Point/Romantic Development"

    prompt = (
        f"You are writing Chapter {chapter_num} ('{chapter_title}') of the {genre.lower()} novel '{book_title}'.\n"
        f"Genre: {genre}\n"
        f"Chapter Title: {chapter_title}\n"
        f"Chapter Summary: {chapter_details['summary']}\n"
        f"Emotional Arc: {chapter_details['arc']}\n"
        f"{key_plot_point_label}: {chapter_details['twist']}\n\n" # 'twist' field from parsing now holds the relevant plot point
        f"Write Chapter {chapter_num} now, approximately {EBOOK_TARGET_WORD_MIN}-{EBOOK_TARGET_WORD_MAX} words. "
        f"Begin directly in the scene. {genre_specific_tone_instruction} Avoid unnecessary jargon. Do not repeat context from earlier chapters. "
        f"**Start the chapter's content directly with the title '{chapter_title}' as a heading.**"
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts: raise ValueError(f"Ebook Chapter {chapter_num} generation failed.")
        chapter_content = response.text
        os.makedirs(EBOOK_CHAPTERS_DIR, exist_ok=True)
        filename = os.path.join(EBOOK_CHAPTERS_DIR, f"chapter_{chapter_num}.md")
        with open(filename, 'w', encoding='utf-8') as f: f.write(chapter_content)
        print(f"Ebook Chapter {chapter_num} ('{chapter_title}') saved to {filename}")
        return {"title": chapter_title, "content": chapter_content, "number": chapter_num}
    except Exception as e:
        print(f"Error generating Ebook Chapter {chapter_num} ('{chapter_title}') for genre {genre}: {e}")
        raise

def ebook_generate_pdf(chapters_content, book_title, output_filename, genre="Thriller"):
    """Combines generated ebook chapters into a single PDF document with page numbers."""
    print(f"\nGenerating Ebook PDF: {output_filename}...")

    doc = SimpleDocTemplate(output_filename, pagesize=letter,
                            leftMargin=inch, rightMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    styles['h1'].alignment = 1
    styles['h2'].alignment = 1
    styles['Normal'].fontSize = 10
    styles['Normal'].leading = 12

    story = []

    # Title Page
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph(book_title, styles['h1']))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("By: Spellbind Studios", styles['h2']))
    story.append(Spacer(1, 3*inch))
    story.append(PageBreak()) # This is page 1, no number

    # Add chapters
    for i, chapter in enumerate(chapters_content):
        if chapter:
            title = chapter.get('title', f"Chapter {i + 1}")
            content = chapter.get('content', '')
            chapter_num = chapter.get('number', i + 1)

            story.append(Spacer(1, 2.5*inch))
            story.append(Paragraph(f"Chapter {chapter_num}", styles['h2']))
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph(title, styles['h1']))
            story.append(PageBreak()) # This will start a new page for each chapter

            # Remove markdown headings from content if present
            content = re.sub(r'^\s*#+\s*' + re.escape(title) + r'\s*', '', content, flags=re.IGNORECASE | re.MULTILINE).strip()

            # Split content into paragraphs and apply styles
            paragraphs = content.split('\n\n')
            for para_text in paragraphs:
                para_text = para_text.strip()
                if para_text:
                    # Basic markdown to HTML-like tags for ReportLab
                    para_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', para_text) # Bold
                    para_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', para_text)     # Italic
                    story.append(Paragraph(para_text.replace('\n', '<br/>'), styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
            story.append(PageBreak()) # Ensure next chapter starts on a new page

    # Function to add page numbers (starting from 2 for the second page)
    def page_number_callback(canvas, doc):
        page_num = doc.page # Current page number from ReportLab
        if page_num > 1: # Start numbering from the second page
            canvas.saveState()
            canvas.setFont('Times-Roman', 9)
            canvas.drawString(letter[0] / 2, 0.75 * inch, f"Page {page_num - 1}") # Adjust for 0-indexed or 1-indexed
            canvas.restoreState()

    try:
        # Build the PDF with the page numbering callback applied to all pages
        # The callback itself will handle starting numbering from the second page
        doc.build(story, onFirstPage=page_number_callback, onLaterPages=page_number_callback)
        print(f"Successfully generated Ebook PDF: {output_filename}")
    except Exception as e:
        print(f"Error generating Ebook PDF: {e}")
        raise

def run_ebook_generation_pipeline(genre_preference="Thriller"):
    """Main pipeline logic for ebook generation. Returns result dict."""
    global current_api_key_index
    current_api_key_index = 0
    # Validate genre_preference
    valid_genres = ["thriller", "romance", "romantic thriller"] # Add more as supported
    selected_genre = genre_preference.lower()
    if selected_genre not in valid_genres:
        print(f"Warning: Invalid genre '{genre_preference}' provided. Defaulting to 'Thriller'.")
        selected_genre = "thriller"
    
    print(f"Starting Autonomous Ebook Writing Pipeline for Genre: {selected_genre.capitalize()}...")
    try:
        print("Starting Autonomous Ebook Writing Pipeline...")
        print("--- Step 0: Cleaning Up Previous Ebook Run ---")
        if os.path.exists(EBOOK_OUTLINE_FILE):
            try: os.remove(EBOOK_OUTLINE_FILE); print(f"Removed old ebook outline: {EBOOK_OUTLINE_FILE}")
            except Exception as e: print(f"Warning: Could not remove {EBOOK_OUTLINE_FILE}: {e}")
        if os.path.exists(EBOOK_CHAPTERS_DIR):
            try: shutil.rmtree(EBOOK_CHAPTERS_DIR); print(f"Removed old ebook chapters dir: {EBOOK_CHAPTERS_DIR}")
            except Exception as e: print(f"Warning: Could not remove {EBOOK_CHAPTERS_DIR}: {e}")
        os.makedirs(EBOOK_CHAPTERS_DIR, exist_ok=True)

        print(f"--- Step 1: Conceptualizing Ebook Idea (Genre: {selected_genre.capitalize()}) ---")
        model = configure_gemini()
        book_concept = ebook_conceptualize_idea(model, genre=selected_genre)
        if not book_concept: raise ValueError("Failed to conceptualize ebook idea.")
        book_title = book_concept['title']
        book_premise = book_concept['premise']
        safe_title = safe_filename(book_title)
        pdf_filename = f"{safe_title}_{selected_genre.capitalize()}.pdf" # Add genre to filename
        print(f"Proceeding with Ebook Title: '{book_title}' (Genre: {selected_genre.capitalize()})")

        print(f"\n--- Step 2: Generating Ebook Instructional Prompt (Genre: {selected_genre.capitalize()}) ---")
        model = configure_gemini()
        instructional_prompt = ebook_generate_instructional_prompt(model, book_title, book_premise, genre=selected_genre)
        if not instructional_prompt: raise ValueError("Failed to generate ebook instructional prompt.")

        print(f"\n--- Step 3: Generating Ebook Outline (Genre: {selected_genre.capitalize()}) ---")
        model = configure_gemini()
        # The instructional_prompt now contains genre-specific instructions for the outline
        outline_text = ebook_generate_outline(model, instructional_prompt) 
        if not outline_text: raise ValueError(f"Failed to generate ebook outline for '{book_title}'.")

        print(f"\n--- Step 4: Parsing Ebook Outline (Genre: {selected_genre.capitalize()}) ---")
        chapters_data = ebook_parse_outline(outline_text, genre=selected_genre) 
        if not chapters_data: raise ValueError("Failed to parse ebook outline.")
        actual_total_chapters = len(chapters_data)

        print(f"\n--- Step 5: Generating Ebook Chapters (Genre: {selected_genre.capitalize()}) ---")
        completed_chapters = 0
        all_chapters_content = []
        for i, chapter_info in enumerate(chapters_data):
            print(f"--- Generating Ebook Chapter {i+1}/{actual_total_chapters} (Genre: {selected_genre.capitalize()}) ---")
            model = configure_gemini()
            chapter_result = ebook_generate_chapter(model, chapter_info, book_title=book_title, genre=selected_genre)
            if chapter_result:
                all_chapters_content.append(chapter_result)
                completed_chapters += 1
            else: raise ValueError(f"Failed to generate ebook chapter {chapter_info.get('number', i+1)} for genre {selected_genre}.")

        print(f"\n--- Step 6: Finalizing Ebook PDF (Genre: {selected_genre.capitalize()}) ---")
        if completed_chapters == actual_total_chapters:
            ebook_generate_pdf(all_chapters_content, book_title=book_title, output_filename=pdf_filename, genre=selected_genre)
            final_message = f"Successfully generated Ebook PDF: {pdf_filename} (Genre: {selected_genre.capitalize()})"
            print(final_message)
            return {"status": "success", "message": final_message, "pdf_filename": pdf_filename, "genre": selected_genre}
        else: raise RuntimeError(f"Ebook Inconsistency: Completed {completed_chapters}/{actual_total_chapters} chapters for genre {selected_genre}.")
    except Exception as e:
        error_message = f"Ebook pipeline failed for genre {selected_genre}: {e}"
        print(error_message)
        return {"status": "error", "message": error_message, "genre": selected_genre}


# ==============================================
# === PODCAST GENERATION LOGIC (Refactored) ===
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
        else: selected_topic = selected_topic_match.group(1).strip()
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
        f"Format the output clearly, starting each episode with 'Episode X: [Title]'."
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts: raise ValueError("Podcast outline generation failed.")
        outline_text = response.text.strip()
        with open(PODCAST_OUTLINE_FILE, 'w', encoding='utf-8') as f: f.write(outline_text)
        print(f"Podcast outline saved to {PODCAST_OUTLINE_FILE}")
        return outline_text
    except Exception as e:
        print(f"Error generating podcast outline: {e}")
        raise

def podcast_parse_outline(outline_text):
    """Parses the generated podcast outline text. More robust version."""
    print("Parsing podcast outline...")
    episodes = []
    episode_sections = []
    try:
        # Attempt 1: Split by the specific "Episode X:" pattern first
        sections_attempt1 = re.split(r'\nEpisode \d+:', '\n' + outline_text, flags=re.IGNORECASE)

        if len(sections_attempt1) > 1:
            episode_sections = sections_attempt1[1:] # Skip potential text before the first split
            print(f"Found {len(episode_sections)} sections using 'Episode X:' split.")
        else:
            # Attempt 2: If specific pattern fails, try splitting by lines that likely start an episode
            print("Warning: 'Episode X:' pattern not found. Trying line-based splitting...")
            potential_sections = []
            current_section_lines = []
            # Split by lines and group them based on lines starting with "Episode <num>:" or "<num>."
            lines = outline_text.strip().split('\n')
            for line in lines:
                line_strip = line.strip()
                # Check if the line looks like a new episode start marker (Episode <num>: or <num>.)
                if re.match(r'^\s*(Episode\s+\d+\s*:|\d+\.\s+)', line_strip, flags=re.IGNORECASE):
                    if current_section_lines: # Add the previously accumulated section if not empty
                        potential_sections.append("\n".join(current_section_lines))
                    current_section_lines = [line] # Start the new section with the marker line
                elif current_section_lines or line_strip: # Only append if we've already started a section OR if it's the very first non-empty line
                    current_section_lines.append(line)
            if current_section_lines: # Add the last accumulated section
                potential_sections.append("\n".join(current_section_lines))

            if potential_sections:
                 print(f"Line-based splitting found {len(potential_sections)} potential sections.")
                 episode_sections = potential_sections
            else:
                 # If both methods fail, raise the error
                 raise ValueError("Could not split podcast outline into episodes using known patterns.")

        # --- Process the identified sections ---
        for i, section in enumerate(episode_sections):
             episode_num = i + 1
             section = section.strip()
             if not section: continue

             # Extract Title: Assume title is the first line, potentially after marker
             title = f"Episode {episode_num}" # Default
             first_line = section.split('\n')[0].strip()
             # Try removing markers like "Episode X:" or "X." from the start of the first line
             title_match = re.match(r'^\s*(?:Episode\s+\d+\s*[:-])?\s*(.*?)\s*$', first_line, flags=re.IGNORECASE)
             if title_match and title_match.group(1):
                 title = title_match.group(1).strip().strip('*')

             # Extract Key Points (look for bullet points or numbered lists after "Key Points:")
             points_text = "No key points found."
             points_match = re.search(r'Key Points:(.*)', section, re.IGNORECASE | re.DOTALL)
             if points_match:
                 # Extract text after "Key Points:", strip whitespace, handle common list formats
                 raw_points = points_match.group(1).strip()
                 # Split by newline and filter for lines starting with common list markers
                 point_lines = [p.strip() for p in raw_points.split('\n') if p.strip().startswith(('-', '*', str(i+1)+'.'))]
                 if point_lines:
                     points_text = "\n".join(point_lines)

             episodes.append({
                 "number": episode_num,
                 "title": title,
                 "key_points": points_text, # Use extracted points or default
                 "full_section": section
             })

        if not episodes:
             raise ValueError("Podcast outline parsing failed to extract any episode details after splitting.")

        print(f"Successfully parsed {len(episodes)} podcast episodes.")
        return episodes
    except Exception as e:
        print(f"Error parsing podcast outline: {e}")
        raise # Re-raise the exception

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
        f"Start the content directly, perhaps with a brief intro referencing the episode title or number."
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
            print(f"--- Generating Podcast Episode {i+1}/{actual_total_episodes} ---")
            model = configure_gemini()
            pdf_path = podcast_generate_episode_pdf(model, episode_info, series_topic, actual_total_episodes)
            if pdf_path:
                all_pdf_filenames.append(os.path.basename(pdf_path))
                completed_episodes += 1
            else: raise ValueError(f"Failed to generate PDF for podcast episode {episode_info.get('number', i+1)}.")

        print("\n--- Step 5: Finalizing Podcast ---")
        if completed_episodes == actual_total_episodes:
            print("\nPodcast series generation complete!")
            final_message = f"Successfully generated {actual_total_episodes} podcast episode PDFs for '{series_topic}'."
            return {"status": "success", "message": final_message, "pdf_filenames": all_pdf_filenames}
        else: raise RuntimeError(f"Podcast Inconsistency: Completed {completed_chapters}/{actual_total_chapters} episodes.")
    except Exception as e:
        error_message = f"Podcast pipeline failed: {e}"
        print(error_message)
        return {"status": "error", "message": error_message, "pdf_filenames": all_pdf_filenames}
