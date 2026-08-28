import streamlit as st
from google import genai
from google.genai import types
import pdfplumber
import docx
import json
from PIL import Image
import io

# Initialize Gemini Client using Streamlit Secret
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def process_file_input(uploaded_files):
    """
    Processes single or multiple uploaded files.
    Returns payload list for Gemini and display metadata.
    """
    payload_parts = []
    display_images = []
    text_content = ""

    # Sort files by name so Page 1, Page 2 process in natural order
    sorted_files = sorted(uploaded_files, key=lambda x: x.name)

    for file in sorted_files:
        filename = file.name.lower()

        if filename.endswith(('.png', '.jpg', '.jpeg')):
            img = Image.open(file)
            display_images.append((file.name, img))
            
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format=img.format if img.format else 'PNG')
            
            payload_parts.append(
                types.Part.from_bytes(
                    data=img_byte_arr.getvalue(),
                    mime_type=file.type
                )
            )
        elif filename.endswith('.pdf'):
            with pdfplumber.open(file) as pdf:
                extracted = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
                text_content += f"\n--- File: {file.name} ---\n" + extracted
        elif filename.endswith('.docx'):
            doc = docx.Document(file)
            extracted = "\n".join([p.text for p in doc.paragraphs])
            text_content += f"\n--- File: {file.name} ---\n" + extracted
        else:
            extracted = str(file.read(), "utf-8")
            text_content += f"\n--- File: {file.name} ---\n" + extracted

    if text_content:
        payload_parts.append(f"STUDENT ESSAY TEXT:\n{text_content}")

    return payload_parts, display_images

def generate_text_report(student_name, syllabus, prompt_text, data):
    report = f"WRITING EVALUATION & PARAGRAPH CORRECTION REPORT\n"
    report += f"="*50 + "\n"
    report += f"Student/Submission : {student_name}\n"
    report += f"Syllabus           : {syllabus}\n"
    report += f"Total Score        : {data.get('overall_score', 0)} / {data.get('max_score', 0)}\n"
    report += f"="*50 + "\n\n"
    
    report += "PARAGRAPH-BY-PARAGRAPH ANALYSIS & CORRECTIONS:\n"
    report += "-"*50 + "\n"
    for item in data.get('paragraph_analysis', []):
        report += f"Paragraph {item.get('paragraph_number')}:\n"
        report += f"Original: {item.get('original_text')}\n"
        report += f"What's Wrong: {item.get('whats_wrong')}\n"
        report += f"Correction: {item.get('corrected_text')}\n\n"

    report += "CRITERIA BREAKDOWN:\n"
    report += "-"*50 + "\n"
    for item in data.get('breakdown', []):
        report += f"- {item.get('criterion')}: {item.get('score')}/{item.get('max')}\n"
        report += f"  Notes: {item.get('feedback')}\n\n"
        
    report += "KEY STRENGTHS:\n"
    for s in data.get('strengths', []):
        report += f"- {s}\n"
        
    report += "\nAREAS FOR IMPROVEMENT:\n"
    for i in data.get('improvements', []):
        report += f"- {i}\n"
        
    return report

# Interface Setup
st.set_page_config(page_title="SPM & IGCSE Multi-Page Essay Marker", layout="wide")
st.title("📝 Automated Writing Marker & Paragraph Corrector")

# Sidebar Controls
syllabus = st.sidebar.selectbox("Select Syllabus", ["SPM 1119", "IGCSE 0500"])
task_prompt = st.sidebar.text_area("The Question (Optional)", help="Paste the essay topic or exam question here.")

# Multi-File Upload Enabled (accept_multiple_files=True)
uploaded_files = st.file_uploader(
    "Upload Student Essay Pages (.png, .jpg, .jpeg, .pdf, .docx, .txt)", 
    type=["png", "jpg", "jpeg", "pdf", "docx", "txt"],
    accept_multiple_files=True
)

if uploaded_files and st.button("Mark Essay"):
    payload_parts, display_images = process_file_input(uploaded_files)
    
    # Display image previews side-by-side or in columns
    if display_images:
        st.subheader("📷 Uploaded Essay Pages")
        cols = st.columns(min(len(display_images), 3))
        for idx, (img_name, img_obj) in enumerate(display_images):
            with cols[idx % 3]:
                st.image(img_obj, caption=f"Page {idx+1}: {img_name}", use_column_width=True)
    
    system_instruction = f"""
    You are an official examiner for {syllabus}. 
    Evaluate the provided student essay against official rubric standards. 
    The submission may contain MULTIPLE IMAGES representing continuous pages of the same essay. 
    Read all pages sequentially from top to bottom before marking.

    Perform a thorough paragraph-by-paragraph breakdown pointing out errors (grammar, vocabulary, tone, punctuation, coherence) and providing exact corrected rewrites for each paragraph across all uploaded pages.
    
    Return JSON ONLY matching this structure:
    {{
      "overall_score": 0,
      "max_score": 0,
      "paragraph_analysis": [
        {{
          "paragraph_number": 1,
          "original_text": "Exact text from paragraph 1",
          "whats_wrong": "Bullet points or brief explanation of what is wrong with this paragraph",
          "corrected_text": "Polished and corrected version of paragraph 1"
        }}
      ],
      "breakdown": [
        {{"criterion": "Criterion Name", "score": 0, "max": 0, "feedback": "Detailed notes referencing text."}}
      ],
      "strengths": ["Strength 1"],
      "improvements": ["Improvement 1"]
    }}
    """
    
    with st.spinner("Processing multi-page submission and evaluating essay..."):
        try:
            contents_payload = []
            if task_prompt:
                contents_payload.append(f"THE QUESTION / ASSIGNMENT PROMPT:\n{task_prompt}\n\n")
            
            contents_payload.append("STUDENT ESSAY PAGES (READ SEQUENTIALLY):")
            contents_payload.extend(payload_parts)

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents_payload,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            
            data = json.loads(response.text)
            
            # Display Overall Score
            st.markdown("---")
            st.header(f"Total Score: {data['overall_score']} / {data['max_score']}")
            
            # Display Paragraph-by-Paragraph Corrections
            st.subheader("✍️ Paragraph-by-Paragraph Corrections")
            for item in data.get('paragraph_analysis', []):
                with st.expander(f"📌 Paragraph {item['paragraph_number']} Analysis & Correction", expanded=True):
                    st.markdown(f"**Original Text:**\n> {item['original_text']}")
                    st.markdown(f"**❌ What's Wrong:**\n{item['whats_wrong']}")
                    st.markdown(f"**✅ Corrected Version:**\n{item['corrected_text']}")

            # Display Rubric Breakdown
            st.subheader("📊 Criteria Breakdown")
            for item in data.get('breakdown', []):
                st.markdown(f"**{item['criterion']} ({item['score']}/{item['max']})**")
                st.write(item['feedback'])
                
            st.subheader("✅ Key Strengths")
            for s in data.get('strengths', []):
                st.write(f"- {s}")
                
            st.subheader("💡 Areas for Improvement")
            for i in data.get('improvements', []):
                st.write(f"- {i}")
                
            # Downloadable Report Button
            submission_name = uploaded_files[0].name.split('.')[0]
            report_str = generate_text_report(submission_name, syllabus, task_prompt, data)
            st.download_button(
                label="📥 Download Full Marking & Correction Sheet (.txt)",
                data=report_str,
                file_name=f"Corrected_{submission_name}.txt",
                mime="text/plain"
            )

        except Exception as e:
            st.error(f"Error evaluating essay: {e}")
