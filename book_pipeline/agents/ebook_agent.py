import google.generativeai as genai
import os
import time
import re
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

# Import necessary components using absolute paths from the project root (book_pipeline)
from main import configure_gemini, safe_filename # Absolute import
from config import (
    EBOOK_CHAPTERS_DIR, EBOOK_OUTLINE_FILE, EBOOK_TOTAL_CHAPTERS,
    EBOOK_TARGET_WORD_MIN, EBOOK_TARGET_WORD_MAX # Absolute import from config
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

def ebook_conceptualize_idea(model, genre="romantic thriller"):
    """Uses Gemini to brainstorm a book title and premise."""
    print(f"Conceptualizing ebook idea for genre: {genre}...")
    prompt = (
        f"You are a creative assistant. Brainstorm a compelling book concept for the genre '{genre}'. "
        f"Provide only the following, in this exact format:\n"
        f"Title: [Your Book Title Here]\n"
        f"Premise: [A 1-2 sentence gripping premise for the book]"
    )
    try:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
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

def ebook_generate_instructional_prompt(model, book_title, book_premise):
    """Generates the detailed instructional prompt for the ebook writer AI."""
    print("Generating ebook instructional prompt...")
    num_chapters_to_request = EBOOK_TOTAL_CHAPTERS
    prompt = (
        f"You are a prompt engineer creating instructions for an expert AI writer specializing in romantic thrillers.\n"
        f"The goal is to automate the creation of a complete {num_chapters_to_request}-chapter book.\n\n"
        f"Book Title: \"{book_title}\"\n"
        f"Book Premise: {book_premise}\n\n"
        f"Generate a detailed, structured instructional prompt for the AI writer. The prompt MUST instruct the AI writer to perform the following steps sequentially:\n"
        f"1. Create a full {num_chapters_to_request}-chapter outline for the book \"{book_title}\". Each chapter outline must include: a 1-2 sentence summary, the emotional arc, a key twist or reveal, and a compelling chapter title (clearly labeled as 'Title:').\n" # Emphasize label
        f"2. For each chapter (1 to {num_chapters_to_request}), write {EBOOK_TARGET_WORD_MIN}-{EBOOK_TARGET_WORD_MAX} words using the corresponding outline details. The writing should begin directly in the scene, avoid repeating context from earlier chapters, maintain a dark, suspenseful, emotional tone consistent with a romantic thriller, avoid complex jargon unless essential, and start the chapter content with its generated title as a heading (using markdown H1 format like '# Chapter Title').\n" # Specify heading format
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

def ebook_parse_outline(outline_text):
    """Parses the generated ebook outline text into a structured format. Final robust version 2."""
    print("Parsing ebook outline...")
    chapters = []
    # Use findall to capture the content *between* chapter markers or after the last marker
    # Pattern looks for start of line, optional # or **, "Chapter", number, colon, optional **, then captures everything until the next chapter marker or end of string
    pattern = r'^\s*(?:#|\*{1,2})\s*Chapter\s+(\d+):\s*(.*?)\n(.*?)(?=^\s*(?:#|\*{1,2})\s*Chapter\s+\d+:|\Z)'
    matches = re.findall(pattern, outline_text, re.MULTILINE | re.IGNORECASE | re.DOTALL)

    if not matches:
        # Fallback: Try parsing based on numbered list if Chapter X fails
        print("Warning: 'Chapter X:' pattern not found. Trying numbered list splitting...")
        pattern = r'^\s*(\d+)\.\s+(.*?)\n(.*?)(?=^\s*\d+\.\s+|\Z)'
        matches = re.findall(pattern, outline_text, re.MULTILINE | re.DOTALL)
        if not matches:
            raise ValueError("Could not split ebook outline into chapters using known patterns ('# Chapter X:', '**Chapter X:**', or 'N.').")
        print(f"Found {len(matches)} sections using numbered list split.")
        # Reformat matches to match the expected structure (number, title, content)
        matches = [(match[0], match[1], match[2]) for match in matches] # number, title, content

    print(f"Processing {len(matches)} identified sections...")
    for match in matches:
        try:
            chapter_num_str, first_line_content, section_content = match
            chapter_num = int(chapter_num_str) # Chapter number from the regex match
            section = (first_line_content + "\n" + section_content).strip() # Reconstruct section for detail parsing

            # --- Refined Title Extraction ---
            title = first_line_content.strip().strip('*') # Title is usually the rest of the marker line
            print(f"  Processing Chapter {chapter_num}, Title: '{title}'")

            # Extract other details
            summary_match = re.search(r'Summary\s*:(.*?)(Title:|Emotional Arc:|Key Twist:|Reveal:|\n\n|$)', section, re.DOTALL | re.IGNORECASE)
            arc_match = re.search(r'Emotional Arc\s*:(.*?)(Title:|Summary:|Key Twist:|Reveal:|\n\n|$)', section, re.DOTALL | re.IGNORECASE)
            twist_match = re.search(r'(?:Key Twist|Reveal)\s*:(.*?)(Title:|Summary:|Emotional Arc:|\n\n|$)', section, re.DOTALL | re.IGNORECASE)

            summary = summary_match.group(1).strip() if summary_match else "Summary not found."
            arc = arc_match.group(1).strip() if arc_match else "Arc not found."
            twist = twist_match.group(1).strip() if twist_match else "Twist not found."

            chapters.append({"number": chapter_num, "title": title, "summary": summary, "arc": arc, "twist": twist, "full_section": section})

        except Exception as parse_err:
            print(f"Error processing section for chapter {chapter_num}: {parse_err}")
            # Optionally skip this chapter or raise the error depending on desired robustness
            # continue

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

def ebook_generate_chapter(model, chapter_details, book_title):
    """Generates content for a single ebook chapter."""
    chapter_num = chapter_details['number']
    chapter_title = chapter_details['title']
    print(f"Generating Ebook Chapter {chapter_num}: {chapter_title}...")
    prompt = (
        f"You are writing Chapter {chapter_num} ('{chapter_title}') of the romantic thriller '{book_title}'.\n"
        f"Chapter Title: {chapter_title}\n"
        f"Chapter Summary: {chapter_details['summary']}\n"
        f"Emotional Arc: {chapter_details['arc']}\n"
        f"Key Twist/Reveal: {chapter_details['twist']}\n\n"
        f"Write Chapter {chapter_num} now, approximately {EBOOK_TARGET_WORD_MIN}-{EBOOK_TARGET_WORD_MAX} words. "
        f"Begin directly in the scene. Maintain a dark, suspenseful, and emotional tone. Avoid unnecessary jargon. Do not repeat context from earlier chapters. "
        f"**Start the chapter's content directly with the title '{chapter_title}' as a heading (using markdown # format).**" # Specify heading format
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
        print(f"Error generating Ebook Chapter {chapter_num} ('{chapter_title}'): {e}")
        raise

def ebook_generate_pdf(chapters_content, book_title, output_filename):
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

def run_ebook_generation_pipeline():
    """Main pipeline logic for ebook generation. Returns result dict."""
    global current_api_key_index
    current_api_key_index = 0
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

        print("--- Step 1: Conceptualizing Ebook Idea ---")
        model = configure_gemini()
        book_concept = ebook_conceptualize_idea(model)
        if not book_concept: raise ValueError("Failed to conceptualize ebook idea.")
        book_title = book_concept['title']
        book_premise = book_concept['premise']
        safe_title = safe_filename(book_title)
        pdf_filename = f"{safe_title}.pdf"
        print(f"Proceeding with Ebook Title: '{book_title}'")

        print("\n--- Step 2: Generating Ebook Instructional Prompt ---")
        model = configure_gemini()
        instructional_prompt = ebook_generate_instructional_prompt(model, book_title, book_premise)
        if not instructional_prompt: raise ValueError("Failed to generate ebook instructional prompt.")

        print("\n--- Step 3: Generating Ebook Outline ---")
        model = configure_gemini()
        outline_text = ebook_generate_outline(model, instructional_prompt)
        if not outline_text: raise ValueError(f"Failed to generate ebook outline for '{book_title}'.")

        print("\n--- Step 4: Parsing Ebook Outline ---")
        chapters_data = ebook_parse_outline(outline_text) # Use corrected function
        if not chapters_data: raise ValueError("Failed to parse ebook outline.")
        actual_total_chapters = len(chapters_data) # Use the actual count parsed

        # Ensure we don't generate more chapters than requested, even if parsing found more
        if actual_total_chapters > EBOOK_TOTAL_CHAPTERS:
            print(f"Warning: Parsed {actual_total_chapters} chapters, but limiting generation to {EBOOK_TOTAL_CHAPTERS} as per config.")
            chapters_data = chapters_data[:EBOOK_TOTAL_CHAPTERS]
            actual_total_chapters = EBOOK_TOTAL_CHAPTERS


        print("\n--- Step 5: Generating Ebook Chapters ---")
        completed_chapters = 0
        all_chapters_content = []
        # Loop through the potentially truncated chapters_data
        for i, chapter_info in enumerate(chapters_data):
            print(f"--- Generating Ebook Chapter {i+1}/{actual_total_chapters} ---")
            model = configure_gemini()
            chapter_result = ebook_generate_chapter(model, chapter_info, book_title=book_title)
            if chapter_result:
                all_chapters_content.append(chapter_result)
                completed_chapters += 1
            else: raise ValueError(f"Failed to generate ebook chapter {chapter_info.get('number', i+1)}.")

        print("\n--- Step 6: Finalizing Ebook PDF ---")
        # Check against the number of chapters we actually tried to generate
        if completed_chapters == actual_total_chapters:
            ebook_generate_pdf(all_chapters_content, book_title=book_title, output_filename=pdf_filename)
            final_message = f"Successfully generated Ebook PDF: {pdf_filename} ({completed_chapters} chapters)"
            print(final_message)
            return {"status": "success", "message": final_message, "pdf_filename": pdf_filename}
        else: raise RuntimeError(f"Ebook Inconsistency: Completed {completed_chapters}/{actual_total_chapters} chapters.")
    except Exception as e:
        print(f"Ebook pipeline failed: {e}")
        return {"status": "error", "message": f"Ebook pipeline failed: {e}"}
