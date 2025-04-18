import google.generativeai as genai
import os
import time
import re
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from config import (
    GEMINI_API_KEYS, GEMINI_MODEL, CHAPTERS_DIR, OUTLINE_FILE,
    TOTAL_CHAPTERS, TARGET_WORD_COUNT_MIN, # Removed PROGRESS_FILE, FRONTEND_DIR
    TARGET_WORD_COUNT_MAX
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

# Removed update_progress function as real-time updates are removed

def safe_filename(text):
    """Creates a safe filename from text."""
    text = re.sub(r'[\\/*?:"<>|]', "", text) # Remove invalid chars
    text = text.replace(' ', '_')
    return text[:100] # Limit length

# --- Core Generation Functions (Modified to remove socketio) ---

def generate_outline(model, instructional_prompt):
    """Generates the book outline using the provided instructional prompt."""
    print("Generating book outline...")
    # status_update_func('status', {'message': 'Generating book outline...'}) # Removed
    try:
        response = model.generate_content(instructional_prompt)
        if not response.parts:
             raise ValueError("Outline generation failed. Response empty/blocked.")
        outline_text = response.text

        with open(OUTLINE_FILE, 'w', encoding='utf-8') as f:
            f.write(outline_text)
        print(f"Outline saved to {OUTLINE_FILE}")
        # status_update_func('status', {'message': f"Outline saved to {OUTLINE_FILE}"}) # Removed
        return outline_text
    except Exception as e:
        print(f"Error generating outline: {e}")
        # status_update_func('error', {'message': f"Error generating outline: {e}"}) # Removed
        raise # Re-raise

def conceptualize_idea(model, genre="romantic thriller"):
    """Uses Gemini to brainstorm a book title and premise."""
    print(f"Conceptualizing book idea for genre: {genre}...")
    # status_update_func('status', {'message': f"Conceptualizing book idea ({genre})..."}) # Removed
    prompt = (
        f"You are a creative assistant. Brainstorm a compelling book concept for the genre '{genre}'. "
        f"Provide only the following, in this exact format:\n"
        f"Title: [Your Book Title Here]\n"
        f"Premise: [A 1-2 sentence gripping premise for the book]"
    )
    try:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts:
             raise ValueError("Conceptualization failed. Response empty/blocked.")
        concept_text = response.text.strip()
        print(f"Generated Concept:\n{concept_text}")

        title_match = re.search(r"Title:(.*?)(?:\nPremise:|$)", concept_text, re.IGNORECASE | re.DOTALL)
        premise_match = re.search(r"Premise:(.*)", concept_text, re.IGNORECASE | re.DOTALL)

        title = title_match.group(1).strip().strip('"\'') if title_match else "Untitled Book"
        premise = premise_match.group(1).strip() if premise_match else "No premise generated."

        # status_update_func('status', {'message': f"Concept generated: '{title}'"}) # Removed
        return {"title": title, "premise": premise}
    except Exception as e:
        print(f"Error during conceptualization: {e}")
        # status_update_func('error', {'message': f"Error during conceptualization: {e}"}) # Removed
        raise

def generate_instructional_prompt(model, book_title, book_premise):
    """Generates the detailed instructional prompt for the writer AI."""
    print("Generating instructional prompt...")
    # status_update_func('status', {'message': 'Generating detailed instructions...'}) # Removed
    num_chapters_to_request = TOTAL_CHAPTERS
    prompt = (
        f"You are a prompt engineer creating instructions for an expert AI writer specializing in romantic thrillers.\n"
        f"The goal is to automate the creation of a complete {num_chapters_to_request}-chapter book.\n\n"
        f"Book Title: \"{book_title}\"\n"
        f"Book Premise: {book_premise}\n\n"
        f"Generate a detailed, structured instructional prompt for the AI writer. The prompt MUST instruct the AI writer to perform the following steps sequentially:\n"
        f"1. Create a full {num_chapters_to_request}-chapter outline for the book \"{book_title}\". Each chapter outline must include: a 1-2 sentence summary, the emotional arc, a key twist or reveal, and a compelling chapter title.\n"
        f"2. For each chapter (1 to {num_chapters_to_request}), write {TARGET_WORD_COUNT_MIN}-{TARGET_WORD_COUNT_MAX} words using the corresponding outline details. The writing should begin directly in the scene, avoid repeating context from earlier chapters, maintain a dark, suspenseful, emotional tone consistent with a romantic thriller, avoid complex jargon unless essential, and start the chapter content with its generated title as a heading.\n"
        f"3. Treat the entire process as an automated workflow and complete all chapters.\n\n"
        f"The final output should be ONLY the instructional prompt itself, ready to be given to the writer AI. Start the prompt with 'You are an expert writer...' and mention the publisher 'Spellbind Studios'."
    )
    try:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        response = model.generate_content(prompt, safety_settings=safety_settings)
        if not response.parts:
             raise ValueError("Instructional prompt generation failed. Response empty/blocked.")
        instructional_prompt = response.text.strip()
        print("Generated Instructional Prompt (preview):")
        print(instructional_prompt[:300] + "...")
        # status_update_func('status', {'message': 'Generated detailed instructions.'}) # Removed
        return instructional_prompt
    except Exception as e:
        print(f"Error generating instructional prompt: {e}")
        # status_update_func('error', {'message': f"Error generating instructional prompt: {e}"}) # Removed
        raise

def parse_outline(outline_text):
    """Parses the generated outline text into a structured format."""
    print("Parsing outline...")
    # status_update_func('status', {'message': 'Parsing generated outline...'}) # Removed
    chapters = []
    try:
        chapter_sections = re.split(r'\nChapter \d+:', '\n' + outline_text, flags=re.IGNORECASE)
        if len(chapter_sections) > 1:
            chapter_sections = chapter_sections[1:]
        else:
             raise ValueError("Could not split outline into chapters using 'Chapter X:' pattern.")

        print(f"Found {len(chapter_sections)} potential chapter sections in outline.")

        for i, section in enumerate(chapter_sections):
             chapter_num = i + 1
             section = section.strip()
             if not section: continue

             title_match_label = re.search(r'Title:(.*?)(Summary:|Emotional Arc:|Key Twist:|Reveal:|$)', section, re.DOTALL | re.IGNORECASE)
             title_match_direct = re.search(r'^\s*(.*?)\s*(Summary:|Emotional Arc:|Key Twist:|Reveal:|\n)', section, re.IGNORECASE)

             if title_match_label:
                 title = title_match_label.group(1).strip().strip('*')
             elif title_match_direct:
                 potential_title = title_match_direct.group(1).strip().strip('*')
                 if not re.match(r'(Summary|Emotional Arc|Key Twist|Reveal):', potential_title, re.IGNORECASE) and len(potential_title) < 100:
                      title = potential_title
                 else:
                      title = f"Chapter {chapter_num}"
             else:
                 title = f"Chapter {chapter_num}"

             summary_match = re.search(r'Summary:(.*?)(Title:|Emotional Arc:|Key Twist:|Reveal:|\n\n|$)', section, re.DOTALL | re.IGNORECASE)
             arc_match = re.search(r'Emotional Arc:(.*?)(Title:|Summary:|Key Twist:|Reveal:|\n\n|$)', section, re.DOTALL | re.IGNORECASE)
             twist_match = re.search(r'(?:Key Twist:|Reveal:)(.*?)(Title:|Summary:|Emotional Arc:|\n\n|$)', section, re.DOTALL | re.IGNORECASE)

             summary = summary_match.group(1).strip() if summary_match else f"Summary for Chapter {chapter_num} not found."
             arc = arc_match.group(1).strip() if arc_match else f"Emotional Arc for Chapter {chapter_num} not found."
             twist = twist_match.group(2).strip() if twist_match else f"Twist/Reveal for Chapter {chapter_num} not found."

             chapters.append({
                 "number": chapter_num,
                 "title": title,
                 "summary": summary,
                 "arc": arc,
                 "twist": twist,
                 "full_section": section
             })

        if not chapters:
             raise ValueError("Outline parsing failed to extract any chapter details.")

        print(f"Successfully parsed {len(chapters)} chapters.")
        # status_update_func('status', {'message': f"Parsed {len(chapters)} chapters from outline."}) # Removed
        return chapters
    except Exception as e:
        print(f"Error parsing outline: {e}")
        # status_update_func('error', {'message': f"Error parsing outline: {e}. Check {OUTLINE_FILE}."}) # Removed
        raise

def generate_chapter(model, chapter_details, book_title):
    """Generates content for a single chapter."""
    chapter_num = chapter_details['number']
    chapter_title = chapter_details['title']
    print(f"Generating Chapter {chapter_num}: {chapter_title}...")
    # status_update_func('status', {'message': f"Generating Chapter {chapter_num}: {chapter_title}..."}) # Removed

    prompt = (
        f"You are writing Chapter {chapter_num} ('{chapter_title}') of the romantic thriller '{book_title}'.\n"
        f"Chapter Title: {chapter_title}\n"
        f"Chapter Summary: {chapter_details['summary']}\n"
        f"Emotional Arc: {chapter_details['arc']}\n"
        f"Key Twist/Reveal: {chapter_details['twist']}\n\n"
        f"Write Chapter {chapter_num} now, approximately {TARGET_WORD_COUNT_MIN}-{TARGET_WORD_COUNT_MAX} words. "
        f"Begin directly in the scene. Maintain a dark, suspenseful, and emotional tone. Avoid unnecessary jargon. Do not repeat context from earlier chapters. "
        f"**Start the chapter's content directly with the title '{chapter_title}' as a heading.**"
    )
    try:
        response = model.generate_content(prompt)
        if not response.parts:
             raise ValueError(f"Chapter {chapter_num} generation failed. Response empty/blocked.")
        chapter_content = response.text

        os.makedirs(CHAPTERS_DIR, exist_ok=True)
        filename = os.path.join(CHAPTERS_DIR, f"chapter_{chapter_num}.md")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(chapter_content)
        print(f"Chapter {chapter_num} ('{chapter_title}') saved to {filename}")
        return {"title": chapter_title, "content": chapter_content, "number": chapter_num}
    except Exception as e:
        print(f"Error generating Chapter {chapter_num} ('{chapter_title}'): {e}")
        # status_update_func('error', {'message': f"Error generating Chapter {chapter_num}: {e}"}) # Removed
        raise

def generate_pdf_book(chapters_content, book_title, output_filename):
    """Combines generated chapters into a single PDF document."""
    print(f"\nGenerating PDF book: {output_filename}...")
    # status_update_func('status', {'message': f"Generating PDF book: {output_filename}..."}) # Removed
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

            content = re.sub(r'^\s*#+\s*' + re.escape(title) + r'\s*', '', content, flags=re.IGNORECASE | re.MULTILINE).strip()
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
        print(f"Successfully generated PDF: {output_filename}")
        # status_update_func('status', {'message': f"Successfully generated PDF: {output_filename}"}) # Removed
    except Exception as e:
        print(f"Error generating PDF: {e}")
        # status_update_func('error', {'message': f"Error generating PDF: {e}"}) # Removed
        raise


# --- Main Pipeline Function (Refactored for API polling) ---

def run_generation_pipeline():
    """The main pipeline logic, callable from Flask. Returns result dict."""
    global current_api_key_index
    current_api_key_index = 0 # Reset key index

    # Wrap the entire process in a try...except block to return final status
    try:
        print("Starting Autonomous Book Writing Pipeline...")
        # status_update_func('status', {'message': 'Pipeline started...'}) # Removed

        # 0. Auto-Clean & Initial Setup
        print("--- Step 0: Cleaning Up Previous Run ---")
        # status_update_func('status', {'message': 'Cleaning up previous run...'}) # Removed
        if os.path.exists(OUTLINE_FILE):
            try: os.remove(OUTLINE_FILE); print(f"Removed old outline: {OUTLINE_FILE}")
            except Exception as e: print(f"Warning: Could not remove {OUTLINE_FILE}: {e}")
        if os.path.exists(CHAPTERS_DIR):
            try: shutil.rmtree(CHAPTERS_DIR); print(f"Removed old chapters dir: {CHAPTERS_DIR}")
            except Exception as e: print(f"Warning: Could not remove {CHAPTERS_DIR}: {e}")
        os.makedirs(CHAPTERS_DIR, exist_ok=True)
        # No initial progress update needed

        # 1. Conceptualize Idea
        print("--- Step 1: Conceptualizing Idea ---")
        model = configure_gemini()
        book_concept = conceptualize_idea(model) # Removed status_update_func
        if not book_concept: raise ValueError("Failed to conceptualize book idea.")

        book_title = book_concept['title']
        book_premise = book_concept['premise']
        safe_title = safe_filename(book_title) # Use helper
        pdf_filename = f"{safe_title}.pdf"
        print(f"Proceeding with Title: '{book_title}'")

        # 2. Generate Instructional Prompt
        print("\n--- Step 2: Generating Instructional Prompt ---")
        model = configure_gemini()
        instructional_prompt = generate_instructional_prompt(model, book_title, book_premise) # Removed status_update_func
        if not instructional_prompt: raise ValueError("Failed to generate instructional prompt.")

        # 3. Generate Outline
        print("\n--- Step 3: Generating Outline ---")
        model = configure_gemini()
        outline_text = generate_outline(model, instructional_prompt) # Removed status_update_func
        if not outline_text: raise ValueError(f"Failed to generate outline for '{book_title}'.")

        # 4. Parse Outline
        print("\n--- Step 4: Parsing Outline ---")
        chapters_data = parse_outline(outline_text) # Removed status_update_func
        if not chapters_data: raise ValueError("Failed to parse podcast outline.")
        actual_total_chapters = len(chapters_data)
        # No progress update needed here

        # 5. Generate Chapters
        print("\n--- Step 5: Generating Chapters ---")
        # status_update_func('status', {'message': f"Starting generation of {actual_total_chapters} chapters..."}) # Removed
        completed_chapters = 0
        all_chapters_content = []
        for i, chapter_info in enumerate(chapters_data):
            # Add simple console progress indicator
            print(f"--- Generating Chapter {i+1}/{actual_total_chapters} ---")
            model = configure_gemini()
            chapter_result = generate_chapter(model, chapter_info, book_title=book_title) # Removed status_update_func
            if chapter_result:
                all_chapters_content.append(chapter_result)
                completed_chapters += 1
                # update_progress(status_update_func, completed_chapters, actual_total_chapters) # Removed
                # time.sleep(1) # Optional delay
            else:
                 raise ValueError(f"Failed to generate chapter {chapter_info.get('number', i+1)}.")

        # 6. Completion & PDF Generation
        print("\n--- Step 6: Finalizing ---")
        if completed_chapters == actual_total_chapters:
            # status_update_func('status', {'message': 'All chapters generated. Creating final PDF...'}) # Removed
            generate_pdf_book(all_chapters_content, book_title=book_title, output_filename=pdf_filename) # Removed status_update_func
            final_message = f"Successfully generated PDF: {pdf_filename}"
            print(final_message)
            return {"status": "success", "message": final_message, "pdf_filename": pdf_filename}
        else:
            raise RuntimeError(f"Inconsistency: Completed {completed_chapters}/{actual_total_chapters} chapters.")

    except Exception as e:
        # Catch any exception from the steps above
        print(f"Ebook pipeline failed: {e}")
        error_message = f"Ebook pipeline failed: {e}"
        # status_update_func('error', {'message': error_message}) # Removed
        # Return error status
        return {"status": "error", "message": error_message}
