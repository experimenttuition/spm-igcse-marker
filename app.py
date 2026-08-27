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

def extract_file_content(uploaded_file):
    """Extract text or prepare image bytes depending on the file type."""
    filename = uploaded_file.name.lower()
    
    if filename.endswith(('.png', '.jpg', '.jpeg')):
        # Open image and convert to bytes for Gemini
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
    report = f"WRITING EVALUATION REPORT\n"
    report += f"="*40 + "\n"
    report += f"Student/File : {student_name}\n"
    report += f"Syllabus     : {syllabus}\n"
    report += f"Total Score  : {data.get('overall_score', 0)} / {data.get('max_score', 0)}\n"
    report += f"="*40 + "\n\n"
    
    report += "CRITERIA BREAKDOWN:\n"
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
st.set_page_config(page_title="SPM & IGCSE Essay Marker", layout="wide")
st.title("📝 Automated Writing Marker")

# Sidebar Controls (Renamed to "The Question")
syllabus = st.sidebar.selectbox("Select Syllabus", ["SPM 1119", "IGCSE 0500"])
task_prompt = st.sidebar.text_area("The Question (Optional)", help="Paste the essay topic or exam question here.")

# File Upload Interface (Added JPG, JPEG, PNG support)
uploaded_file = st.file_uploader(
    "Upload Student Essay (.png, .jpg, .jpeg, .pdf, .docx, .txt)", 
    type=["png", "jpg", "jpeg", "pdf", "docx", "txt"]
)

if uploaded_file and st.button("Mark Essay"):
    file_type, content = extract_file_content(uploaded_file)
    
    # Display preview if an image was uploaded
    if file_type == "image":
        st.image(uploaded_file, caption="Uploaded Essay Image", width=400)
    
    system_instruction = f"""
    You are an official examiner for {syllabus}. 
    Evaluate the provided student essay against official rubric standards. 
    If the essay is an image of handwriting, read the text carefully first, then evaluate it.
    
    Return JSON ONLY matching this structure:
    {{
      "overall_score": 0,
      "max_score": 0,
      "breakdown": [
        {{"criterion": "Criterion Name", "score": 0, "max": 0, "feedback": "Detailed notes referencing text."}}
      ],
      "strengths": ["Strength 1"],
      "improvements": ["Improvement 1"]
    }}
    """
    
    with st.spinner("Analyzing essay and evaluating criteria..."):
        try:
            # Prepare contents payload for Gemini
            contents_payload = []
            if task_prompt:
                contents_payload.append(f"THE QUESTION / ASSIGNMENT PROMPT:\n{task_prompt}\n\n")
            
            if file_type == "image":
                contents_payload.append("STUDENT ESSAY IMAGE:")
                contents_payload.append(content)  # Binary image part
            else:
                contents_payload.append(f"STUDENT ESSAY TEXT:\n{content}")

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents_payload,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            
            data = json.loads(response.text)
            
            # Display Results
            st.markdown("---")
            st.header(f"Total Score: {data['overall_score']} / {data['max_score']}")
            
            st.subheader("📊 Criteria Breakdown")
            for item in data['breakdown']:
                st.markdown(f"**{item['criterion']} ({item['score']}/{item['max']})**")
                st.write(item['feedback'])
                
            st.subheader("✅ Key Strengths")
            for s in data['strengths']:
                st.write(f"- {s}")
                
            st.subheader("💡 Areas for Improvement")
            for i in data['improvements']:
                st.write(f"- {i}")
                
            report_str = generate_text_report(uploaded_file.name.split('.')[0], syllabus, task_prompt, data)
            
            st.download_button(
                label="📥 Download Full Marking Sheet (.txt)",
                data=report_str,
                file_name=f"Marked_{uploaded_file.name.split('.')[0]}.txt",
                mime="text/plain"
            )

        except Exception as e:
            st.error(f"Error evaluating essay: {e}")
