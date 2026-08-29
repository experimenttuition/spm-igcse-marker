import json
import io
import time
import streamlit as st
from google import genai
from google.genai import types
import pdfplumber
import docx
from PIL import Image

# Initialize Gemini Client using Streamlit Secret
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

def process_file(uploaded_file):
    """Extract text or convert image into Gemini bytes part."""
    filename = uploaded_file.name.lower()
    
    if filename.endswith(('.png', '.jpg', '.jpeg')):
        img = Image.open(uploaded_file)
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format=img.format if img.format else 'PNG')
        return "image", types.Part.from_bytes(
            data=img_byte_arr.getvalue(),
            mime_type=uploaded_file.type
        )
    elif filename.endswith('.pdf'):
        with pdfplumber.open(uploaded_file) as pdf:
            text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
            return "text", text
    elif filename.endswith('.docx'):
        doc = docx.Document(uploaded_file)
        text = "\n".join([p.text for p in doc.paragraphs])
        return "text", text
    else:
        return "text", str(uploaded_file.read(), "utf-8")

def generate_text_report(student_name, syllabus, prompt_text, data):
    report = f"WRITING EVALUATION & PARAGRAPH CORRECTION REPORT\n"
    report += f"="*50 + "\n"
    report += f"Student/File : {student_name}\n"
    report += f"Syllabus     : {syllabus}\n"
    report += f"Total Score  : {data.get('overall_score', 0)} / {data.get('max_score', 0)}\n"
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

def generate_with_retry(contents_payload, system_instruction, max_retries=3):
    """Attempt API call up to max_retries times to handle traffic spikes."""
    models_to_try = ["gemini-3.6-flash", "gemini-2.5-flash"]
    
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents_payload,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json"
                    )
                )
                return response
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                elif attempt == max_retries - 1 and model_name == models_to_try[-1]:
                    raise e

# Interface Setup
st.set_page_config(page_title="Multi-Syllabus Essay Marker", layout="wide")
st.title("📝 Automated Writing Marker & Paragraph Corrector")

# Expanded Syllabus List
syllabus_list = [
    "MPT4",
    "UASA Form 3",
    "SPM 1119",
    "IGCSE 3138 (Year 7)",
    "IGCSE 3139 (Year 8)",
    "IGCSE 3140 (Year 9)",
    "IGCSE 0816/01",
    "IGCSE 0816/02",
    "IGCSE 0500",
    "IGCSE 0510",
    "IGCSE O-Level 1123"
]

# Sidebar Controls
syllabus = st.sidebar.selectbox("Select Syllabus / Marking Scheme", syllabus_list)
task_prompt = st.sidebar.text_area("The Question (Optional)", help="Paste the essay topic or exam question here.")

# Multi-File Upload Interface
uploaded_files = st.file_uploader(
    "Upload Student Essay Pages (.png, .jpg, .jpeg, .pdf, .docx, .txt)", 
    type=["png", "jpg", "jpeg", "pdf", "docx", "txt"],
    accept_multiple_files=True
)

if uploaded_files and st.button("Mark & Correct Essay"):
    contents_payload = []
    
    if task_prompt:
        contents_payload.append(f"THE QUESTION / ASSIGNMENT PROMPT:\n{task_prompt}\n\n")
    
    image_files = [f for f in uploaded_files if f.name.lower().endswith(('.png', '.jpg', '.jpeg'))]
    if image_files:
        st.subheader("📷 Uploaded Essay Pages")
        cols = st.columns(min(len(image_files), 4))
        for idx, img_file in enumerate(image_files):
            with cols[idx % 4]:
                st.image(img_file, caption=f"Page {idx + 1}: {img_file.name}", width=250)

    for idx, file in enumerate(uploaded_files):
        file_type, content = process_file(file)
        if file_type == "image":
            contents_payload.append(f"STUDENT ESSAY IMAGE PAGE {idx + 1}:")
            contents_payload.append(content)
        else:
            contents_payload.append(f"STUDENT ESSAY TEXT PAGE {idx + 1}:\n{content}")

    system_instruction = f"""
    You are an official examiner for {syllabus}. 
    Evaluate the provided student essay strictly according to official assessment rubrics and criteria for {syllabus}.
    The essay may span across MULTIPLE uploaded images/pages. Read all pages in order as ONE single continuous essay.

    Perform a thorough paragraph-by-paragraph breakdown pointing out errors (grammar, vocabulary, tone, punctuation, coherence) and providing exact corrected rewrites for each paragraph.
    
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
    
    with st.spinner(f"Analyzing essay using {syllabus} rubric standards..."):
        try:
            response = generate_with_retry(contents_payload, system_instruction)
            data = json.loads(response.text)
            
            # Display Overall Score
            st.markdown("---")
            st.header(f"Total Score: {data['overall_score']} / {data['max_score']}")
            
            # Display Paragraph Breakdown
            st.subheader("✍️ Paragraph-by-Paragraph Corrections")
            for item in data.get('paragraph_analysis', []):
                with st.expander(f"📌 Paragraph {item['paragraph_number']} Analysis & Correction", expanded=True):
                    st.markdown(f"**Original Text:**\n> {item['original_text']}")
                    st.markdown(f"**❌ What's Wrong:**\n{item['whats_wrong']}")
                    st.markdown(f"**✅ Corrected Version:**\n{item['corrected_text']}")

            # Display Criteria
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
                
            # Downloadable Report
            report_name = uploaded_files[0].name.split('.')[0]
            report_str = generate_text_report(report_name, syllabus, task_prompt, data)
            st.download_button(
                label="📥 Download Full Marking & Correction Sheet (.txt)",
                data=report_str,
                file_name=f"Marked_{report_name}.txt",
                mime="text/plain"
            )

        except Exception as e:
            st.error(f"Error evaluating essay: {e}")
