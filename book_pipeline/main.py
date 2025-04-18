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
    PROGRESS_FILE, TOTAL_CHAPTERS, TARGET_WORD_COUNT_MIN, # Removed PROMPT_FILE
    TARGET_WORD_COUNT_MAX, FRONTEND_DIR
)

# --- Global Variables ---
# Move API key index management inside the pipeline function if needed,
# or ensure it's reset if the function can be called multiple times.
# For simplicity in a single run per server start, keep it global for now.
current_api_key_index = 0

# --- Helper Functions ---

def get_next_api_key():
    """Rotates through the API keys."""
    global current_api_key_index
    if not GEMINI_API_KEYS:
        raise ValueError("No API keys loaded. Cannot proceed.")
    key = GEMINI_API_KEYS[current_api_key_index]
    # Basic check for placeholder keys loaded from .env
    if "YOUR_API_KEY" in key:
         print(f"Warning: API Key at index {current_api_key_index} seems to be a placeholder.")
         # Depending on strictness, could raise ValueError here
    current_api_key_index = (current_api_key_index + 1) % len(GEMINI_API_KEYS)
    return key

def configure_gemini():
    """Configures the Gemini client with the next available key."""
    api_key = get_next_api_key()
    genai.configure(api_key=api_key)
    print(f"Using API Key ending with: ...{api_key[-4:]}")
    # Consider adding error handling for invalid API keys here
    return genai.GenerativeModel(GEMINI_MODEL)

# Modified update_progress to emit SocketIO events
def update_progress(socketio_instance, completed_chapters, total_chapters_for_progress):
    """Updates the progress via SocketIO."""
    try:
        progress_data = {
            'completed': completed_chapters,
            'total': total_chapters_for_progress
        }
        socketio_instance.emit('progress_update', progress_data)
        print(f"Progress Emitted: {completed_chapters}/{total_chapters_for_progress}")
        # Optionally, still write to file if direct file access is needed for some reason
        # progress_path = os.path.join(FRONTEND_DIR, PROGRESS_FILE)
        # with open(progress_path, 'w', encoding='utf-8') as f:
        #     f.write(f"{completed_chapters}/{total_chapters_for_progress}")
    except Exception as e:
        print(f"Error emitting progress update: {e}")

# --- Core Generation Functions (Modified slightly for SocketIO/Error Handling) ---

def generate_outline(socketio_instance, model, instructional_prompt):
    """Generates the book outline using the provided instructional prompt."""
    print("Generating book outline...")
    socketio_instance.emit('status_update', {'message': 'Generating book outline...'})
    try:
        response = model.generate_content(instructional_prompt)
        # Add basic check for blocked content
        if not response.parts:
             raise ValueError("Outline generation failed. The response was empty or blocked.")
        outline_text = response.text

        with open(OUTLINE_FILE, 'w', encoding='utf-8') as f:
            f.write(outline_text)
        print(f"Outline saved to {OUTLINE_FILE}")
        socketio_instance.emit('status_update', {'message': f"Outline saved to {OUTLINE_FILE}"})
        return outline_text
    except Exception as e:
        print(f"Error generating outline: {e}")
        socketio_instance.emit('generation_error', {'message': f"Error generating outline: {e}"})
        return None

def conceptualize_idea(socketio_instance, model, genre="romantic thriller"):
    """Uses Gemini to brainstorm a book title and premise."""
    print(f"Conceptualizing book idea for genre: {genre}...")
    socketio_instance.emit('status_update', {'message': f"Conceptualizing book idea ({genre})..."})
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
             raise ValueError("Conceptualization failed. The response was empty or blocked.")
        concept_text = response.text.strip()
        print(f"Generated Concept:\n{concept_text}")

        title_match = re.search(r"Title:(.*?)(?:\nPremise:|$)", concept_text, re.IGNORECASE | re.DOTALL)
        premise_match = re.search(r"Premise:(.*)", concept_text, re.IGNORECASE | re.DOTALL)

        title = title_match.group(1).strip().strip('"\'') if title_match else "Untitled Book"
        premise = premise_match.group(1).strip() if premise_match else "No premise generated."

        socketio_instance.emit('status_update', {'message': f"Concept generated: '{title}'"})
        return {"title": title, "premise": premise}
    except Exception as e:
        print(f"Error during conceptualization: {e}")
        socketio_instance.emit('generation_error', {'message': f"Error during conceptualization: {e}"})
        return None

def generate_instructional_prompt(socketio_instance, model, book_title, book_premise):
    """Generates the detailed instructional prompt for the writer AI."""
    print("Generating instructional prompt...")
    socketio_instance.emit('status_update', {'message': 'Generating detailed instructions for AI writer...'})
    # Using TOTAL_CHAPTERS from config for the prompt generation
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
        socketio_instance.emit('status_update', {'message': 'Generated detailed instructions.'})
        return instructional_prompt
    except Exception as e:
        print(f"Error generating instructional prompt: {e}")
        socketio_instance.emit('generation_error', {'message': f"Error generating instructional prompt: {e}"})
        return None

def parse_outline(socketio_instance, outline_text):
    """Parses the generated outline text into a structured format."""
    print("Parsing outline...")
    socketio_instance.emit('status_update', {'message': 'Parsing generated outline...'})
    chapters = []
    try:
        # Split based on "Chapter X:" pattern, case-insensitive
        chapter_sections = re.split(r'\nChapter \d+:', '\n' + outline_text, flags=re.IGNORECASE)
        if len(chapter_sections) > 1:
            chapter_sections = chapter_sections[1:] # Skip potential text before the first chapter
        else:
            # Fallback if "Chapter X:" not found, maybe just numbered list?
            chapter_sections = re.split(r'\n\d+\.\s+', '\n' + outline_text)
            if len(chapter_sections) > 1:
                chapter_sections = chapter_sections[1:]
            else: # Give up if no clear sections found
                 raise ValueError("Could not split outline into chapters. Check outline.md format.")


        print(f"Found {len(chapter_sections)} potential chapter sections in outline.")

        for i, section in enumerate(chapter_sections):
             chapter_num = i + 1
             section = section.strip()
             if not section: continue # Skip empty sections

             # --- Refined Title Extraction ---
             title_match_label = re.search(r'Title:(.*?)(Summary:|Emotional Arc:|Key Twist:|Reveal:|$)', section, re.DOTALL | re.IGNORECASE)
             title_match_direct = re.search(r'^\s*(.*?)\s*(Summary:|Emotional Arc:|Key Twist:|Reveal:|\n)', section, re.IGNORECASE)

             if title_match_label:
                 title = title_match_label.group(1).strip().strip('*')
             elif title_match_direct:
                 potential_title = title_match_direct.group(1).strip().strip('*')
                 if not re.match(r'(Summary|Emotional Arc|Key Twist|Reveal):', potential_title, re.IGNORECASE) and len(potential_title) < 100: # Avoid long text as title
                      title = potential_title
                 else:
                      title = f"Chapter {chapter_num}"
             else:
                 title = f"Chapter {chapter_num}"

             # --- Other Details Extraction ---
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
                 "full_section": section # Keep the raw section
             })

        if not chapters:
             raise ValueError("Outline parsing failed to extract any chapter details.")

        print(f"Successfully parsed {len(chapters)} chapters.")
        socketio_instance.emit('status_update', {'message': f"Parsed {len(chapters)} chapters from outline."})
        return chapters
    except Exception as e:
        print(f"Error parsing outline: {e}")
        socketio_instance.emit('generation_error', {'message': f"Error parsing outline: {e}. Check outline.md."})
        return []

def generate_chapter(socketio_instance, model, chapter_details, book_title):
    """Generates content for a single chapter."""
    chapter_num = chapter_details['number']
    chapter_title = chapter_details['title']
    print(f"Generating Chapter {chapter_num}: {chapter_title}...")
    socketio_instance.emit('status_update', {'message': f"Generating Chapter {chapter_num}: {chapter_title}..."})

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
        # Return the details along with content for PDF generation
        return {"title": chapter_title, "content": chapter_content, "number": chapter_num} # Ensure number is returned
    except Exception as e:
        print(f"Error generating Chapter {chapter_num} ('{chapter_title}'): {e}")
        socketio_instance.emit('generation_error', {'message': f"Error generating Chapter {chapter_num}: {e}"})
        return None

def generate_pdf_book(socketio_instance, chapters_content, book_title, output_filename):
    """Combines generated chapters into a single PDF document."""
    print(f"\nGenerating PDF book: {output_filename}...")
    socketio_instance.emit('status_update', {'message': f"Generating PDF book: {output_filename}..."})
    doc = SimpleDocTemplate(output_filename, pagesize=letter,
                            leftMargin=inch, rightMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    styles['h1'].alignment = 1
    styles['h2'].alignment = 1
    story = []

    # --- Title Page ---
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph(book_title, styles['h1']))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("By: Spellbind Studios", styles['h2']))
    story.append(Spacer(1, 3*inch))
    story.append(PageBreak())

    # --- Chapters ---
    for i, chapter in enumerate(chapters_content):
        if chapter:
            title = chapter.get('title', f"Chapter {i + 1}")
            content = chapter.get('content', '')
            chapter_num = chapter.get('number', i + 1)

            # --- Chapter Title Page ---
            story.append(Spacer(1, 2.5*inch))
            story.append(Paragraph(f"Chapter {chapter_num}", styles['h2']))
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph(title, styles['h1']))
            story.append(PageBreak())

            # --- Chapter Content Page ---
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
        socketio_instance.emit('generation_complete', {'message': f"Successfully generated PDF: {output_filename}", 'pdf_filename': output_filename})
    except Exception as e:
        print(f"Error generating PDF: {e}")
        socketio_instance.emit('generation_error', {'message': f"Error generating PDF: {e}"})


# --- Main Pipeline Function ---

def run_generation_pipeline(socketio_instance):
    """The main pipeline logic, callable from Flask."""
    global current_api_key_index
    current_api_key_index = 0 # Reset key index for each run

    try:
        print("Starting Autonomous Book Writing Pipeline...")
        socketio_instance.emit('status_update', {'message': 'Pipeline started...'})

        # 0. Auto-Clean & Initial Setup
        print("--- Step 0: Cleaning Up Previous Run ---")
        socketio_instance.emit('status_update', {'message': 'Cleaning up previous run...'})
        if os.path.exists(OUTLINE_FILE):
            try: os.remove(OUTLINE_FILE); print(f"Removed old outline: {OUTLINE_FILE}")
            except Exception as e: print(f"Warning: Could not remove {OUTLINE_FILE}: {e}")
        if os.path.exists(CHAPTERS_DIR):
            try: shutil.rmtree(CHAPTERS_DIR); print(f"Removed old chapters dir: {CHAPTERS_DIR}")
            except Exception as e: print(f"Warning: Could not remove {CHAPTERS_DIR}: {e}")
        os.makedirs(CHAPTERS_DIR, exist_ok=True)
        os.makedirs(FRONTEND_DIR, exist_ok=True)
        # Initial progress update (total will be updated after parsing)
        update_progress(socketio_instance, 0, TOTAL_CHAPTERS)

        # 1. Conceptualize Idea
        print("--- Step 1: Conceptualizing Idea ---")
        model = configure_gemini()
        book_concept = conceptualize_idea(socketio_instance, model)
        if not book_concept: return # Error handled in function

        book_title = book_concept['title']
        book_premise = book_concept['premise']
        safe_title = re.sub(r'[\\/*?:"<>|]', "", book_title)
        pdf_filename = f"{safe_title.replace(' ', '_')}.pdf"
        print(f"Proceeding with Title: '{book_title}'")

        # 2. Generate Instructional Prompt
        print("\n--- Step 2: Generating Instructional Prompt ---")
        model = configure_gemini()
        instructional_prompt = generate_instructional_prompt(socketio_instance, model, book_title, book_premise)
        if not instructional_prompt: return # Error handled in function

        # 3. Generate Outline
        print("\n--- Step 3: Generating Outline ---")
        model = configure_gemini()
        outline_text = generate_outline(socketio_instance, model, instructional_prompt)
        if not outline_text: return # Error handled in function

        # 4. Parse Outline
        print("\n--- Step 4: Parsing Outline ---")
        chapters_data = parse_outline(socketio_instance, outline_text)
        if not chapters_data: return # Error handled in function
        actual_total_chapters = len(chapters_data)
        update_progress(socketio_instance, 0, actual_total_chapters) # Update total for progress bar

        # 5. Generate Chapters
        print("\n--- Step 5: Generating Chapters ---")
        socketio_instance.emit('status_update', {'message': f"Starting generation of {actual_total_chapters} chapters..."})
        completed_chapters = 0
        all_chapters_content = []
        for i, chapter_info in enumerate(chapters_data):
            model = configure_gemini()
            chapter_result = generate_chapter(socketio_instance, model, chapter_info, book_title=book_title)
            if chapter_result:
                all_chapters_content.append(chapter_result)
                completed_chapters += 1
                update_progress(socketio_instance, completed_chapters, actual_total_chapters)
                # time.sleep(1) # Optional small delay
            else:
                # Error already emitted by generate_chapter
                print(f"Stopping pipeline due to error in chapter {chapter_info.get('number', i+1)}.")
                socketio_instance.emit('status_update', {'message': f"Stopping pipeline due to error in chapter {chapter_info.get('number', i+1)}."})
                return # Stop the whole process on chapter failure

        # 6. Completion & PDF Generation
        print("\n--- Step 6: Finalizing ---")
        if completed_chapters == actual_total_chapters:
            socketio_instance.emit('status_update', {'message': 'All chapters generated. Creating final PDF...'})
            generate_pdf_book(socketio_instance, all_chapters_content, book_title=book_title, output_filename=pdf_filename)
        else:
            # This case should ideally not be reached if we return on chapter failure
            print(f"\nBook generation incomplete. {completed_chapters}/{actual_total_chapters} chapters generated for '{book_title}'.")
            socketio_instance.emit('generation_error', {'message': f"Incomplete generation: {completed_chapters}/{actual_total_chapters} chapters."})

    except Exception as e:
        # Catch any unexpected errors during the pipeline
        print(f"An unexpected error occurred in the pipeline: {e}")
        socketio_instance.emit('generation_error', {'message': f"A critical error occurred: {e}"})

# Note: The if __name__ == "__main__": block is removed as this script
# is now intended to be imported and run via app.py
