import re
from pypdf import PdfReader
from io import BytesIO
from services.ai import get_embedding

KNOWN_SKILLS = {
    "Python", "FastAPI", "Django", "Flask", "Docker", "Kubernetes", 
    "AWS", "GCP", "Azure", "SQL", "PostgreSQL", "MySQL", "MongoDB",
    "React", "Vue", "Angular", "Node.js", "Java", "Go", "C++",
    "Machine Learning", "Deep Learning", "PyTorch", "TensorFlow",
    "LightGBM", "YOLO", "Computer Vision", "NLP", "Git", "Linux",
    "Scikit-learn", "Pandas", "NumPy"
}


def extract_text_from_pdf(file_content: bytes) -> str:
    """
    **PDF Text Extractor**
    
    Reads the raw bytes of a PDF file and converts it into a plain string.
    
    **Parameters:**
    - `file_content`: The binary content of the uploaded file.
    """
    try:
        # Open PDF from memory (no need to save to disk first)
        pdf_reader = PdfReader(BytesIO(file_content))

        # Extract text page by page
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        return text.strip()
    
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def clean_name(name: str) -> str:
    """
    **Name Cleaner**
    
    Fixes common PDF kerning issues where letters have spaces between them.
    Example: 'W ahyu' -> 'Wahyu'
    
    **Logic:**
    - Looks for a Capital Letter followed by a Space and a Lowercase Letter.
    - Removes that specific space.
    """
    if not name:
        return ""

    return re.sub(r"([A-Z])\s+(?=[a-z])", r"\1", name).strip()


def extract_details(text: str):
    """
    **Smart Detail Extractor**
    
    Attempts to parse specific metadata from the raw resume text.
    
    **Extraction Logic:**
    1. **Name:** Assumes the first non-empty line is the candidate's name. Applies cleaning.
    2. **Experience:** - Searches for sections like "Experience" or "Work History".
       - Only counts years found *after* that header to avoid counting graduation dates.
       - Calculates `Max Year - Min Year` to estimate total experience.
    
    **Returns:**
    - `full_name` (str)
    - `experience_years` (int)
    """
    # 1. Name Extraction (Heuristic: First line)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    raw_name = lines[0] if lines else None
    full_name = clean_name(raw_name) 
    
    # 2. Experience Calculation
    lower_text = text.lower()
    
    # Find where the "Experience" section starts
    experience_start_index = -1
    for keyword in ["experience", "work history", "employment"]:
        idx = lower_text.find(keyword)
        if idx != -1:
            experience_start_index = idx
            break

    # Crop text to start from "Experience" (or use full text if not found)
    target_text = text if experience_start_index == -1 else text[experience_start_index:]
    
    # Find all years (e.g., 2020, 2024) in the target text
    years = re.findall(r"\b(20\d{2})\b", target_text)
    
    experience_years = 0
    if years:
        # Convert strings to integers
        years_int = [int(y) for y in years]

        if years_int:
            # Simple math: End Year - Start Year
            experience_years = max(years_int) - min(years_int)
    
    return full_name, experience_years


def extract_skills(text: str) -> list[str]:
    """
    **Skill Matcher**
    
    Scans the resume for keywords defined in `KNOWN_SKILLS`.
    
    **Logic:**
    - Uses regex `\bword\b` (word boundaries) to ensure exact matches.
    - Example: 'Go' matches "I know Go", but not "Google".
    - Case-insensitive matching.
    """
    found_skills = set()
    text_lower = text.lower()

    for skill in KNOWN_SKILLS:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, text_lower):
            found_skills.add(skill)
    
    return list(found_skills)

# def estimate_experience(text: str) -> int:
#     years = re.findall(r"\b(20\d{2})\b", text)
#     if not years:
#         return 0

#     years = [int(y) for y in years]
#     min_years = min(years)
#     max_years = max(years)

#     diff = max_years - min_years
#     return max(0, diff)

def analyze_resume(file_content: bytes):
    """
    **Main Analysis Pipeline**
    
    Orchestrates the entire CV analysis process.
    
    **Steps:**
    1. **Extract Text:** Converts PDF binary to string.
    2. **Extract Metadata:** Gets Name, Experience Years.
    3. **Extract Skills:** Finds keywords.
    4. **Generate AI Brain:** Creates a vector embedding of the first 2000 chars.
    
    **Returns:**
    - A dictionary containing all extracted data, ready for the database.
    """
    raw_text = extract_text_from_pdf(file_content)
    
    if not raw_text:
        return None
    
    extracted_name, years = extract_details(raw_text)
    skills = extract_skills(raw_text)

    # Only embed the first 2000 characters to keep it focused on the summary/recent work
    embedding = get_embedding(raw_text[:2000])
    
    return {
        "text": raw_text,
        "embedding": embedding,
        "skills": skills,
        "experience_years": years,
        "extracted_name": extracted_name
    }