import json
import os
import time
import random
import requests
import re
import gspread
import shutil
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google import genai

# --- ⚙️ CONFIGURATION ---
# 🚨 PASTE YOUR GEMINI API KEY HERE 🚨
GEMINI_API_KEY = "AIzaSyAq2hBj60PfNbSmirQinkRQxTGpw2zbGbE" 

# 🚨 PASTE YOUR FOLDER ID HERE 🚨
TARGET_FOLDER_ID = "1CdzlPliByhC4AsJ4hXbKQ23jeI1p_meR"

SHEET_NAME = "Job_Hunt_Auto"
HARD_DEALBREAKERS = [
    "citizen required", "citizenship required", "us citizen only", 
    "security clearance", "active secret", "top secret", "polygraph", 
    "no sponsorship", "cannot sponsor"
]

# --- 🔌 CLIENT ---
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

# --- 🧹 NOISE CLEANER (NEW!) ---
def clean_job_text(raw_text):
    """Aggressively removes LinkedIn UI noise to find the real JD."""
    lines = raw_text.split('\n')
    clean_lines = []
    
    # Common junk phrases in LinkedIn raw dumps
    junk_phrases = [
        "sign in", "join now", "forgot password", "email or phone", 
        "show more", "show less", "similar jobs", "people also viewed",
        "save job", "apply on company website", "easy apply", "skip to main"
    ]
    
    start_capture = False
    # Heuristics to detect the START of the real description
    start_markers = ["about the job", "about the team", "job description", "what you'll do", "minimum requirements", "qualifications"]
    
    for line in lines:
        s_line = line.strip().lower()
        
        # Skip empty or tiny lines
        if len(s_line) < 3: continue
        
        # Skip known junk lines
        if any(junk in s_line for junk in junk_phrases): continue
        
        # If we haven't found the start yet, look for a marker
        if not start_capture:
            if any(marker in s_line for marker in start_markers) or len(s_line) > 100:
                start_capture = True
        
        # Once started (or if we are lenient), add the line
        # We accept all lines if no marker found yet, just to be safe, 
        # but the junk filter above handles most of the trash.
        clean_lines.append(line.strip())

    # Rejoin. If filter removed everything, fallback to original.
    cleaned = "\n".join(clean_lines)
    return cleaned if len(cleaned) > 100 else raw_text

# --- 🧠 AI LOGIC ---
def call_gemini(prompt):
    """Robust AI caller with retry logic."""
    model_name = 'gemini-flash-latest'
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "429" in str(e):
                print(f"      ⚠️ Rate Limit (429). Waiting {60*(attempt+1)}s...")
                time.sleep(60 * (attempt + 1))
            else:
                print(f"      ❌ AI Error: {e}")
                return None
    return None

def clean_json(text):
    """Finds the first { and last } to extract valid JSON."""
    if not text: return "{}"
    # Regex to find the JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return "{}"

def analyze_job_deeply(master_json, job_desc):
    """Extracts qualifications and calculates a match score."""
    print("      ⚖️  Performing Deep Gap Analysis...")
    
    # Pre-clean the text to help the AI focus
    clean_desc = clean_job_text(job_desc)
    
    profile_summary = {
        "skills": master_json['skills'],
        "projects": [p['name'] + ": " + p['tech'] for p in master_json['projects']]
    }

    prompt = f"""
    You are a Hiring Manager. Analyze this Job Description (JD).
    
    CRITICAL INSTRUCTION: The JD text is messy and contains web-scraping noise. 
    Ignore lines like "Sign In", "Similar Jobs", etc. Focus ONLY on the Role Description and Requirements.
    
    JOB DESCRIPTION CONTENT:
    {clean_desc[:15000]} 
    
    CANDIDATE PROFILE:
    {json.dumps(profile_summary)}
    
    TASK:
    1. Extract 3 'Basic Qualifications' (Must Haves).
    2. Extract 3 'Preferred Qualifications' (Nice to Haves).
    3. Determine 'Match Score' (0-100). 
       - If you cannot find a job description in the text, return score 0.
    4. Write 'Match Analysis' (2 sentences on fit/gaps).
    
    OUTPUT JSON:
    {{
        "basic_quals": ["Req 1", "Req 2", "Req 3"],
        "preferred_quals": ["Pref 1", "Pref 2"],
        "match_score": 85,
        "match_analysis": "Candidate has strong Python..."
    }}
    """
    raw_text = call_gemini(prompt)
    try:
        return json.loads(clean_json(raw_text))
    except:
        print(f"      ⚠️ JSON Parse Error. Raw AI Response: {raw_text[:100]}...")
        return {"match_score": 0, "match_analysis": "Error parsing AI analysis", "basic_quals": [], "preferred_quals": []}

def tailor_resume_content(master_json, job_desc, analysis):
    """Rewrites the resume to target the specific job."""
    print("      🧠 Tailoring Resume Content...")
    
    clean_desc = clean_job_text(job_desc)
    
    prompt = f"""
    You are an Expert Resume Writer. Rewrite the candidate's resume JSON to target this job.
    
    TARGET QUALIFICATIONS: {analysis.get('basic_quals')}
    JOB CONTEXT: {clean_desc[:5000]}
    
    RULES:
    1. **Summary:** 2 lines max. Must mention Job Title and top 3 JD keywords.
    2. **Skills:** Reorder to put JD keywords first.
    3. **Bullets:** Rewrite to match the JD's phrasing. Use "Action Verb + Metric + Result" format.
    
    MASTER JSON:
    {json.dumps(master_json)}
    
    OUTPUT: Valid JSON matching the master structure.
    """
    raw_text = call_gemini(prompt)
    try:
        return json.loads(clean_json(raw_text))
    except:
        return master_json

def escape_latex(text):
    if not isinstance(text, str): return str(text)
    chars = {
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "\\": r"\textbackslash{}"
    }
    pattern = re.compile('|'.join(re.escape(key) for key in chars.keys()))
    return pattern.sub(lambda x: chars[x.group()], text)

def generate_pdf(resume_data, output_filename):
    print("      ⚙️  Compiling PDF...")
    try:
        if not os.path.exists("resume_template.tex"):
            print("   ❌ Error: 'resume_template.tex' file not found!")
            return None
            
        with open("resume_template.tex", "r") as f: 
            template = f.read()

        def safe_get(data, key, default=''): return escape_latex(data.get(key, default))

        # --- REPLACE VARIABLES ---
        tex = template.replace("VAR_NAME", safe_get(resume_data['personal_info'], 'name'))
        tex = tex.replace("VAR_PHONE", safe_get(resume_data['personal_info'], 'phone'))
        tex = tex.replace("VAR_EMAIL", safe_get(resume_data['personal_info'], 'email'))
        tex = tex.replace("VAR_LOCATION", safe_get(resume_data['personal_info'], 'location'))
        tex = tex.replace("VAR_SUMMARY_TEXT", safe_get(resume_data['personal_info'], 'summary'))

        # Skills
        tex = tex.replace("VAR_SKILLS_LANG", safe_get(resume_data['skills'], 'languages'))
        tex = tex.replace("VAR_SKILLS_ML", safe_get(resume_data['skills'], 'ml_ai'))
        tex = tex.replace("VAR_SKILLS_CLOUD", f"{safe_get(resume_data['skills'], 'cloud')}, {safe_get(resume_data['skills'], 'tools')}")
        tex = tex.replace("VAR_SKILLS_VIS", safe_get(resume_data['skills'], 'visualization'))

        # Certifications
        certs = resume_data.get('certifications', ["AWS Data Engineering"])
        cert_str = "".join([f"\\resumeItem{{{escape_latex(c)}}}\n" for c in certs])
        tex = tex.replace("VAR_CERTIFICATIONS_SECTION", cert_str)

        # Education
        edu_str = ""
        for edu in resume_data['education']:
            edu_str += f"\\resumeSubheading{{{escape_latex(edu['school'])}}}{{{escape_latex(edu.get('location',''))}}}{{{escape_latex(edu['degree'])}}}{{{escape_latex(edu['dates'])}}} \\resumeItemListStart \\resumeItem{{GPA: {escape_latex(edu.get('gpa',''))}}} \\resumeItem{{Coursework: {escape_latex(edu.get('coursework',''))}}} \\resumeItemListEnd"
        tex = tex.replace("VAR_EDUCATION_SECTION", edu_str)
        
        # Experience
        exp_str = ""
        for exp in resume_data['experience']:
            bullets = "".join([f"\\resumeItem{{{escape_latex(b)}}}\n" for b in exp['bullets']])
            exp_str += f"\\resumeSubheading{{{escape_latex(exp['company'])}}}{{{escape_latex(exp['location'])}}}{{{escape_latex(exp['role'])}}}{{{escape_latex(exp['dates'])}}} \\resumeItemListStart {bullets} \\resumeItemListEnd"
        tex = tex.replace("VAR_EXPERIENCE_SECTION", exp_str)
        
        # Projects
        proj_str = ""
        for proj in resume_data['projects']:
            bullets = "".join([f"\\resumeItem{{{escape_latex(b)}}}\n" for b in proj['bullets']])
            proj_str += f"\\resumeProjectHeading{{\\textbf{{{escape_latex(proj['name'])}}} $|$ \\emph{{{escape_latex(proj['tech'])}}}}}{{}} \\resumeItemListStart {bullets} \\resumeItemListEnd"
        tex = tex.replace("VAR_PROJECTS_SECTION", proj_str)
        
        with open("temp_resume.tex", "w") as f: f.write(tex)
        os.system(f"pdflatex -interaction=nonstopmode -jobname=\"{output_filename}\" temp_resume.tex")
        
        # Cleanup logs
        if not os.path.exists("logs"): os.makedirs("logs")
        for ext in ['.log', '.aux', '.out']:
            if os.path.exists("temp_resume" + ext):
                try: shutil.move("temp_resume" + ext, f"logs/{output_filename}{ext}")
                except: pass

        return f"{output_filename}.pdf" if os.path.exists(f"{output_filename}.pdf") else None
    except Exception as e:
        print(f"   ❌ Compiler Error: {e}")
        return None

# --- 🛠️ AUTH & UPLOAD ---
def get_g_services():
    print("   🔑 Authenticating as USER...")
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        print("❌ ERROR: Missing token.json. Run setup_login.py first.")
        return None, None
    if creds.expired and creds.refresh_token: creds.refresh(Request())
    return gspread.authorize(creds), build('drive', 'v3', credentials=creds)

def upload_to_drive(drive_service, file_path, folder_id):
    file_metadata = {'name': os.path.basename(file_path), 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return file.get('webViewLink')

def fetch_jd(url):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        return soup.get_text(separator="\n")
    except: return ""

# --- 🏃 RUNNER ---
def run_factory():
    print("🏭 Intelligent Career Agent Started...")
    if not os.path.exists("master_resume.json"): 
        print("❌ CRITICAL: master_resume.json not found!")
        return

    with open("master_resume.json", "r") as f: master_json = json.load(f)
    
    gc, drive_service = get_g_services()
    if not gc: return
    sheet = gc.open(SHEET_NAME).sheet1
    jobs = sheet.get_all_records()
    
    for i, job in enumerate(jobs):
        if str(job.get('Status', '')).strip() == "New":
            print(f"\n[Row {i+2}] Processing: {job.get('Job_Title')}...")
            
            # 1. Fetch
            desc = job.get('Description', '')
            if len(desc) < 200: desc = fetch_jd(job.get('Job_Link', ''))
            
            # 2. Hard Dealbreakers
            if any(db in desc.lower() for db in HARD_DEALBREAKERS):
                sheet.update_cell(i+2, 1, "Rejected: Dealbreaker")
                continue

            # 3. Deep Analysis with CLEANING
            analysis = analyze_job_deeply(master_json, desc)
            match_score = analysis.get("match_score", 0)
            
            # 4. UPDATE DESCRIPTION with Smart Notes
            smart_notes = f"""
🤖 AI MATCH SCORE: {match_score}%
----------------------------------
FIT ANALYSIS: {analysis.get("match_analysis")}

BASIC QUALS:
{chr(10).join(['- '+q for q in analysis.get('basic_quals', [])])}

PREFERRED QUALS:
{chr(10).join(['- '+q for q in analysis.get('preferred_quals', [])])}
----------------------------------
ORIGINAL JD:
{desc[:2000]}...
            """
            sheet.update_cell(i+2, 7, smart_notes)

            if match_score < 60:
                print(f"      ⛔ Low Match ({match_score}%). Skipping.")
                # We do NOT mark as rejected automatically in this version, 
                # just skipping generation to save tokens.
                # Uncomment next line if you want to auto-reject:
                # sheet.update_cell(i+2, 1, f"Rejected: Low Match ({match_score}%)")
                continue
            
            # 5. Tailor & Generate
            print(f"      ✅ High Match ({match_score}%). Tailoring...")
            opt_json = tailor_resume_content(master_json, desc, analysis)
            
            safe_title = re.sub(r'[^a-zA-Z0-9]', '_', job.get('Job_Title', 'Job'))[:20]
            pdf_name = f"Resume_{safe_title}_{int(time.time())}"
            pdf_path = generate_pdf(opt_json, pdf_name)
            
            # 6. Upload & Update Status
            if pdf_path:
                try:
                    link = upload_to_drive(drive_service, pdf_path, TARGET_FOLDER_ID)
                    sheet.update_cell(i+2, 1, "Ready for Referral")
                    sheet.update_cell(i+2, 8, link)
                    print(f"      🎉 Success! Resume saved.")
                    os.remove(pdf_path)
                except Exception as e:
                    print(f"      ❌ Upload Error: {e}")
                    sheet.update_cell(i+2, 1, "Error: Upload")
            else:
                sheet.update_cell(i+2, 1, "Error: PDF Gen")
            
            print("      💤 Cooldown (45s)...")
            time.sleep(45)

    print("\n🏁 Batch Complete.")

if __name__ == "__main__":
    run_factory()