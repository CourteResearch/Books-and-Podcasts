import google.generativeai as genai
import os
import time
import re
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

# Import necessary components using relative paths
from ..main import configure_gemini, safe_filename # Relative import
from ..config import ( # Also make config import relative
    EBOOK_CHAPTERS_DIR, EBOOK_OUTLINE_FILE, EBOOK_TOTAL_CHAPTERS,
    EBOOK_TARGET_WORD_MIN, EBOOK_TARGET_WORD_MAX # Relative import from config
)

# ===========================================
# === EBOOK GENERATION LOGIC              ===
# ===========================================

def ebook_generate_outline(model, instructional_prompt):
    """Generates the book outline using the provided instructional prompt."""
    print("Generating ebook outline...")
    try:
        response = model.generate_content(instructional_prompt)
        if not response.parts:
             raise ValueError("Ebook outline generation failed. Response empty/blocked.")
        outline_text = response.text
        # Clean potential markdown section headers from the LLM response
        outline_text = re.sub(r'^\s*\*+\s*Phase \d+:.*?\*+\s*\n?', '', outline_text, flags=re.IGNORECASE | re.MULTILINE)
        outline_text = re.sub(r'^\s*\*+\s*Step \d+:.*?\*+\s*\n?', '', outline_text, flags=re.IGNORECASE | re.MULTILINE)
        with open(EBOOK_OUTLINE_FILE, 'w', encoding='utf-8') as f:
            f.write(outline_text.strip()) # Write the cleaned text
        print(f"Ebook outline saved to {EBOOK_OUTLINE_FILE}")
        return outline_text.strip()
    except Exception as e:
        print(f"Error generating ebook outline: {e}")
        raise

def ebook_conceptualize_idea(model, genre="Thriller"):
    """Uses Gemini to brainstorm a KDP-optimized book title and premise."""
    print(f"Conceptualizing KDP-optimized ebook idea for genre: {genre}...")
    prompt = (
        f"You are a KDP Publishing Strategist specializing in the '{genre}' genre. Your goal is to generate a book concept highly likely to attract readers and sell well on Amazon KDP.\n\n"
        f"Analyze current KDP trends and popular tropes within the '{genre}' genre. Consider elements like:\n"
        f"- High-stakes conflict\n"
        f"- Compelling character archetypes (e.g., enemies-to-lovers, forbidden romance, alpha hero, strong heroine)\n"
        f"- Intriguing settings\n"
        f"- Common reader expectations and hooks for '{genre}'\n"
        f"- Potential for series continuation (optional but good)\n\n"
        f"Generate ONE unique and marketable book concept. Provide ONLY the following, in this exact format:\n\n"
        f"Title: [A keyword-rich, attention-grabbing title optimized for KDP search within the '{genre}' genre]\n"
        f"Premise: [A 1-3 sentence gripping premise highlighting the core conflict, main characters, stakes, and key tropes. Make it sound like compelling ad copy for KDP.]"
        f"\n\nEnsure the concept feels fresh and avoids overly generic clichés unless given a unique, marketable twist."
    )
    try:
        # Consider adjusting generation parameters for more creativity if needed/possible
        # e.g., temperature=0.8
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}, # Adjust safety as needed for genre
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
        f"The goal is to automate the creation of a complete {num_chapters_to_request}-chapter book suitable for publication on KDP.\n\n"
        f"Book Title: \"{book_title}\"\n"
        f"Book Premise: {book_premise}\n"
        f"Genre: {genre}\n\n"
        f"Generate a detailed, structured instructional prompt for the AI writer. The prompt MUST instruct the AI writer to perform the following steps sequentially:\n"
        f"1. Create a full {num_chapters_to_request}-chapter outline for the book \"{book_title}\". Each chapter outline must include: a 1-2 sentence summary, the emotional arc (appropriate for the {genre.lower()} genre), a key plot point (e.g., twist for thriller, romantic development for romance), and a compelling chapter title (clearly labeled as 'Title:').\n"
        f"2. For each chapter (1 to {num_chapters_to_request}), write {EBOOK_TARGET_WORD_MIN}-{EBOOK_TARGET_WORD_MAX} words using the corresponding outline details. The writing should begin directly in the scene, avoid repeating context from earlier chapters, maintain {genre_specific_tone}, avoid complex jargon unless essential, and start the chapter content with its generated title as a heading (using markdown H1 format like '# Chapter Title').\n"
        f"3. Treat the entire process as an automated workflow and complete all chapters.\n\n"
        f"The final output should be ONLY the instructional prompt itself, ready to be given to the writer AI. Start the prompt with 'You are an expert writer...' and mention the publisher 'Spellbind Studios'."
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts:
             raise ValueError("Ebook instructional prompt generation failed.")
        instructional_prompt = response.text.strip()
        print("Generated Ebook Instructional Prompt (preview):")
        print(instructional_prompt[:300] + "...")
        return instructional_prompt
    except Exception as e:
        print(f"Error generating ebook instructional prompt: {e}")
        raise

def ebook_parse_outline(outline_text, genre="Thriller"):
    """Parses the generated ebook outline text into a structured format. Iteratively tries patterns."""
    print(f"Parsing ebook outline for genre: {genre}...")
    chapters = []

    # 1. Isolate the Outline Section
    outline_section_match = re.search(r'(?:##\s*1\.?\s*Outline Creation|###\s*Outline|^\s*\*+\s*Outline\s*\*+)\s*\n(.*?)(?:\n##\s*2\.?\s*Chapter Writing|\Z)', outline_text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if outline_section_match:
        outline_content = outline_section_match.group(1).strip()
        print("Isolated outline section for parsing.")
    else:
        outline_content = outline_text.strip()
        print("No specific outline section markers found, parsing entire content.")

    if not outline_content.strip():
        # If after isolation and stripping, the content is empty, no point proceeding.
        debug_original_outline_preview = outline_text[:500] + ("..." if len(outline_text) > 500 else "")
        print(f"DEBUG: Original outline_text resulted in empty outline_content. Original preview:\n---\n{debug_original_outline_preview}\n---")
        raise ValueError("Outline content is empty after isolation and stripping.")

    # 2. Find all chapter sections using iterative pattern matching with re.finditer
    # Define patterns from most specific/likely to more general
    # Named group 'num' for chapter number, 'header' for the full matched header text
    chapter_marker_patterns = [
        re.compile(r'^(?P<header>\s*\*{2}Chapter\s+(?P<num>\d+):\*{2}\s*)$', re.MULTILINE | re.IGNORECASE),      # **Chapter X:** (entire line)
        re.compile(r'^(?P<header>\s*#+\s*Chapter\s+(?P<num>\d+):?\s*)$', re.MULTILINE | re.IGNORECASE),        # # Chapter X: or ## Chapter X:
        re.compile(r'^(?P<header>\s*Chapter\s+(?P<num>\d+):?\s*)$', re.MULTILINE | re.IGNORECASE),             # Chapter X:
        re.compile(r'^(?P<header>\s*(?P<num>\d+)\.\s*(?!Summary:|Emotional Arc:|Title:|Key Twist|Key Plot Point).*\S.*)$', re.MULTILINE | re.IGNORECASE) # N. Some Title (ensure it's not a list item)
    ]

    processed_chapter_sections = [] # Store as (chapter_num, section_text_for_details)
    
    for idx, pattern in enumerate(chapter_marker_patterns):
        print(f"Trying chapter marker pattern index {idx}: {pattern.pattern}")
        matches = list(pattern.finditer(outline_content))
        
        if matches:
            print(f"Found {len(matches)} markers with pattern index {idx}.")
            for i, current_match in enumerate(matches):
                try:
                    chapter_num_str = current_match.group('num')
                    chapter_num = int(chapter_num_str)
                except (IndexError, ValueError):
                    print(f"Warning: Could not extract chapter number from match using pattern {idx}. Match: '{current_match.group(0)}'")
                    continue

                # Content for this chapter starts after the current marker's full match
                # and ends at the start of the next marker's full match, or end of string.
                content_start_pos = current_match.end()
                content_end_pos = matches[i+1].start() if (i + 1) < len(matches) else len(outline_content)
                
                section_text_for_details = outline_content[content_start_pos:content_end_pos].strip()
                processed_chapter_sections.append((chapter_num, section_text_for_details))
            
            if processed_chapter_sections: # If this pattern yielded results, use them and stop.
                break 
    
    if not processed_chapter_sections:
        debug_outline_preview = outline_content[:1000] + ("..." if len(outline_content) > 1000 else "")
        print(f"DEBUG: outline_content being parsed when all chapter marker patterns failed:\n---\n{debug_outline_preview}\n---")
        raise ValueError("Could not split ebook outline into chapters using any known patterns. Review logged outline_content.")

    # 3. Process Each Chapter Section for details (Summary, Title, etc.)
    print(f"Processing {len(processed_chapter_sections)} identified chapter sections for details...")
    for chapter_num, section_content in processed_chapter_sections:
        try:
            print(f"  Processing Chapter {chapter_num}...")
            # More flexible regex for extracting details, allowing for variations in bolding of labels
            title_regex = r"^\s*\*\s*(?:\*{0,2}Title\*{0,2})\s*:\s*(.*?)\s*$"
            summary_regex = r"^\s*\*\s*(?:\*{0,2}Summary\*{0,2})\s*:\s*(.*?)\s*$"
            arc_regex = r"^\s*\*\s*(?:\*{0,2}Emotional Arc\*{0,2})\s*:\s*(.*?)\s*$"
            twist_label_regex_part = "(?:Twist/Reveal|Key Plot Point/Romantic Development)"
            twist_regex = rf"^\s*\*\s*(?:\*{0,2}{twist_label_regex_part}\*{0,2})\s*:\s*(.*?)\s*$"

            title_match = re.search(title_regex, section_content, re.MULTILINE | re.IGNORECASE)
            summary_match = re.search(summary_regex, section_content, re.MULTILINE | re.IGNORECASE)
            arc_match = re.search(arc_regex, section_content, re.MULTILINE | re.IGNORECASE)
            twist_match = re.search(twist_regex, section_content, re.MULTILINE | re.IGNORECASE)

            title = title_match.group(1).strip() if title_match else f"Chapter {chapter_num} Title Not Found"
            summary = summary_match.group(1).strip() if summary_match else "Summary not found."
            arc = arc_match.group(1).strip() if arc_match else "Arc not found."

            twist_or_plot_point_label = "Key Twist/Reveal" if genre.lower() != "romance" else "Key Plot Point/Romantic Development"
            twist = twist_match.group(1).strip() if twist_match else f"{twist_or_plot_point_label} not found."

            print(f"    Title: '{title}' (Raw match: {title_match is not None})")
            chapters.append({"number": chapter_num, "title": title, "summary": summary, "arc": arc, "twist": twist, "full_section": section_content})

        except Exception as parse_err:
            print(f"Error processing details for chapter {chapter_num}: {parse_err}")
            # Optionally add a placeholder chapter or skip
            chapters.append({"number": chapter_num, "title": f"Chapter {chapter_num} (Parsing Error)", "summary": "Error", "arc": "Error", "twist": "Error", "full_section": section_content})

    # Stop processing if we have more chapters than expected (e.g., due to extra text)
    if len(chapters) > EBOOK_TOTAL_CHAPTERS:
        print(f"Warning: Parsed {len(chapters)} chapters, limiting to configured {EBOOK_TOTAL_CHAPTERS}.")
        chapters = chapters[:EBOOK_TOTAL_CHAPTERS]

    if not chapters: raise ValueError("Ebook outline parsing failed to extract any chapter details after splitting.")
    print(f"Successfully parsed {len(chapters)} ebook chapters.")
    return chapters
    # except Exception as e: # Keep broad exception catch for now
    #     print(f"Error parsing ebook outline: {e}")
    #     raise # Re-raise to be caught by the main pipeline

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
        f"**Start the chapter's content directly with the title '{chapter_title}' as a heading (using markdown # format).**"
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

def ebook_generate_pdf(chapters_content, book_title, output_filename, genre="Thriller"): # Added genre for context if needed later
    """Combines generated ebook chapters into a single PDF document."""
    print(f"\nGenerating Ebook PDF: {output_filename}...")
    doc = SimpleDocTemplate(output_filename, pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    styles['h1'].alignment = 1
    styles['h2'].alignment = 1
    story = []
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph(book_title, styles['h1']))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("By: Spellbind Studios", styles['h2']))
    story.append(Spacer(1, 3*inch))
    story.append(PageBreak())
    for i, chapter in enumerate(chapters_content):
        if chapter:
            title = chapter.get('title', f"Chapter {i + 1}")
            content = chapter.get('content', '')
            chapter_num = chapter.get('number', i + 1)
            story.append(Spacer(1, 2.5*inch))
            story.append(Paragraph(f"Chapter {chapter_num}", styles['h2']))
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph(title, styles['h1']))
            story.append(PageBreak())
            # Remove the markdown H1 title if the LLM added it
            content = re.sub(r'^\s*#\s*' + re.escape(title) + r'\s*', '', content, flags=re.IGNORECASE | re.MULTILINE).strip()
            paragraphs = content.split('\n\n')
            for para_text in paragraphs:
                para_text = para_text.strip()
                if para_text:
                    para_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', para_text)
                    para_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', para_text)
                    story.append(Paragraph(para_text.replace('\n', '<br/>'), styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
            story.append(PageBreak())
    try:
        doc.build(story)
        print(f"Successfully generated Ebook PDF: {output_filename}")
    except Exception as e:
        print(f"Error generating Ebook PDF: {e}")
        raise

# Modified to accept optional pre-defined concept AND genre
def run_ebook_generation_pipeline(book_title=None, book_premise=None, genre_preference="Thriller"):
    """Main pipeline logic for ebook generation. Returns result dict.
       If book_title and book_premise are provided, skips conceptualization.
       Uses genre_preference to tailor content.
    """
    global current_api_key_index # Assuming this is for API key rotation, keep it global if needed by configure_gemini
    current_api_key_index = 0 # Reset for each pipeline run

    # Validate genre_preference
    valid_genres = ["thriller", "romance", "romantic thriller"] # Ensure this list is comprehensive
    selected_genre = genre_preference.lower()
    if selected_genre not in valid_genres:
        print(f"Warning: Invalid genre '{genre_preference}' provided to ebook_agent. Defaulting to 'Thriller'.")
        selected_genre = "thriller"

    try:
        print(f"Starting Autonomous Ebook Writing Pipeline (Agent) for Genre: {selected_genre.capitalize()}...")
        print("--- Step 0: Cleaning Up Previous Ebook Run ---")
        if os.path.exists(EBOOK_OUTLINE_FILE): # EBOOK_OUTLINE_FILE should be imported from config
            try: os.remove(EBOOK_OUTLINE_FILE); print(f"Removed old ebook outline: {EBOOK_OUTLINE_FILE}")
            except Exception as e: print(f"Warning: Could not remove {EBOOK_OUTLINE_FILE}: {e}")
        if os.path.exists(EBOOK_CHAPTERS_DIR): # EBOOK_CHAPTERS_DIR should be imported from config
            try: shutil.rmtree(EBOOK_CHAPTERS_DIR); print(f"Removed old ebook chapters dir: {EBOOK_CHAPTERS_DIR}")
            except Exception as e: print(f"Warning: Could not remove {EBOOK_CHAPTERS_DIR}: {e}")
        os.makedirs(EBOOK_CHAPTERS_DIR, exist_ok=True)

        # --- Step 1: Conceptualize OR Use Provided Concept (Genre-Aware) ---
        if not book_title or not book_premise:
            print(f"--- Step 1a: Conceptualizing Ebook Idea (Genre: {selected_genre.capitalize()}) ---")
            model = configure_gemini() # configure_gemini should be imported from ..main
            book_concept = ebook_conceptualize_idea(model, genre=selected_genre)
            if not book_concept: raise ValueError("Failed to conceptualize ebook idea.")
            book_title = book_concept['title']
            book_premise = book_concept['premise']
            print(f"Generated Ebook Concept - Title: '{book_title}' (Genre: {selected_genre.capitalize()})")
        else:
            print(f"--- Step 1b: Using Provided Ebook Concept (Genre: {selected_genre.capitalize()}) ---")
            print(f"Title: '{book_title}'")
            print(f"Premise: '{book_premise}'")

        if not book_title or not book_premise:
             raise ValueError("Missing book title or premise to proceed with generation.")

        safe_title = safe_filename(book_title) # safe_filename should be imported from ..main
        pdf_filename = f"{safe_title}_{selected_genre.capitalize()}.pdf" # Add genre to filename

        print(f"\n--- Step 2: Generating Ebook Instructional Prompt (Genre: {selected_genre.capitalize()}) ---")
        model = configure_gemini()
        instructional_prompt = ebook_generate_instructional_prompt(model, book_title, book_premise, genre=selected_genre)
        if not instructional_prompt: raise ValueError("Failed to generate ebook instructional prompt.")

        print(f"\n--- Step 3: Generating Ebook Outline (Based on Genre-Aware Prompt) ---")
        model = configure_gemini()
        outline_text = ebook_generate_outline(model, instructional_prompt)
        if not outline_text: raise ValueError(f"Failed to generate ebook outline for '{book_title}'.")

        print(f"\n--- Step 4: Parsing Ebook Outline (Genre: {selected_genre.capitalize()}) ---")
        chapters_data = ebook_parse_outline(outline_text, genre=selected_genre)
        if not chapters_data: raise ValueError("Failed to parse ebook outline.")
        actual_total_chapters = len(chapters_data)

        if actual_total_chapters > EBOOK_TOTAL_CHAPTERS: # EBOOK_TOTAL_CHAPTERS from config
            print(f"Warning: Parsed {actual_total_chapters} chapters, but limiting generation to {EBOOK_TOTAL_CHAPTERS} as per config.")
            chapters_data = chapters_data[:EBOOK_TOTAL_CHAPTERS]
            actual_total_chapters = EBOOK_TOTAL_CHAPTERS

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
            final_message = f"Successfully generated Ebook PDF: {pdf_filename} ({completed_chapters} chapters, Genre: {selected_genre.capitalize()})"
            print(final_message)
            return {"status": "success", "message": final_message, "pdf_filename": pdf_filename, "genre": selected_genre}
        else: raise RuntimeError(f"Ebook Inconsistency: Completed {completed_chapters}/{actual_total_chapters} chapters for genre {selected_genre}.")
    except Exception as e:
        error_message = f"Ebook pipeline (Agent) failed for genre {selected_genre}: {e}"
        print(error_message)
        return {"status": "error", "message": error_message, "genre": selected_genre}
