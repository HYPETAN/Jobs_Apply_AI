import pandas as pd
import gspread
import requests
from jobspy import scrape_jobs
from datetime import datetime
import time
import random
import re
import html

# --- ⚙️ CONFIGURATION ---
SHEET_NAME = "Job_Hunt_Auto"
HOURS_OLD = 168 # 7 Days

# --- 🔍 SEARCH QUERIES ---
SEARCH_QUERIES = [
    # --- CORE ROLES ---
    '"Machine Learning Engineer" python',
    '"Data Engineer" aws python',
    '"AI Engineer" tensorflow',
    '"Backend Engineer" python',
    '"Python Developer"',

    # --- NEW SPECIALIZED ROLES ---
    '"MLOps Engineer" python',
    '"Data Scientist" python machine learning',
    '"Software Engineer" machine learning',
    '"NLP Engineer" python',
    '"Computer Vision Engineer" python'
]

LOCATIONS = [
    "Remote", "Seattle, WA", "New York, NY", "Austin, TX", "San Francisco, CA",
    "San Jose, CA", "Boston, MA", "Washington, DC", "Dallas, TX", "Chicago, IL"
]

# --- 🚫 TITLE KILL LIST ---
BAD_TITLE_KEYWORDS = [
    "senior", "sr.", "staff", "principal", "lead", "manager", "director", "vp", "head of", "chief",
    "citizen", "citizenship", "clearance", "secret", "top secret", "ts/sci", "polygraph", "fsp", "public trust"
]

# --- 🛠️ SETUP ---
def connect_to_sheet():
    gc = gspread.service_account(filename="credentials.json")
    sheet = gc.open(SHEET_NAME).sheet1
    return sheet

def clean_description(text):
    if not text: return ""
    text = html.unescape(text)
    text = text.replace(r"\+", "+").replace(r"\-", "-").replace("\n", " ")
    return text

def is_title_clean(title):
    title_lower = title.lower()
    for bad_word in BAD_TITLE_KEYWORDS:
        if bad_word in title_lower:
            return False
    return True

# --- 🌐 CUSTOM SCRAPER: REMOTE OK ---
def scrape_remote_ok():
    print(f"\n🌍 CHECKING REMOTE OK (API)...")
    try:
        # RemoteOK has a public API! No scraping needed.
        url = "https://remoteok.com/api"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        jobs = response.json()
        
        found_jobs = []
        for job in jobs:
            # Skip the legal disclaimer (first item usually)
            if "legal" in job: continue
            
            # Check Date (simple filter, API returns recent jobs)
            date_str = job.get('date', '')
            
            title = job.get('position', '')
            company = job.get('company', '')
            link = job.get('url', '')
            description = job.get('description', '')
            tags = job.get('tags', [])
            
            # 1. Keywords Check
            desc_lower = description.lower() + " " + " ".join(tags).lower()
            if "python" not in desc_lower and "machine learning" not in desc_lower:
                continue
                
            # 2. Title Filter
            if not is_title_clean(title): continue
            
            # 3. Create Row
            found_jobs.append({
                'title': title,
                'company': company,
                'job_url': link,
                'location': "Remote",
                'description': description
            })
            
        print(f"      ✅ Found {len(found_jobs)} matches on RemoteOK.")
        return found_jobs
        
    except Exception as e:
        print(f"      ⚠️ RemoteOK Error: {e}")
        return []

# --- 🕵️ THE SCOUT ---
def run_scout():
    print(f"🕵️  Lead Generator Active.")
    print(f"    Targets: Google, LinkedIn, Indeed, Zip, RemoteOK.")
    
    try:
        sheet = connect_to_sheet()
        existing_links = sheet.col_values(5)
    except Exception as e:
        print(f"❌ Error connecting to Sheets: {e}")
        return

    total_added = 0
    
    # 1. RUN CUSTOM SCRAPER (RemoteOK)
    remote_jobs = scrape_remote_ok()
    for job in remote_jobs:
        if job['job_url'] in existing_links: continue
        new_row = ["New", datetime.now().strftime("%Y-%m-%d"), job['title'], job['company'], job['job_url'], job['location'], "FETCH_ME", "", "", ""]
        try:
            sheet.append_row(new_row)
            existing_links.append(job['job_url'])
            total_added += 1
            print(f"      ✅ LEAD CAPTURED [REMOTEOK]: {job['title']}")
        except: pass

    # 2. RUN STANDARD SCRAPERS
    # Removed Glassdoor (Broken). Kept Google, Zip, LinkedIn, Indeed.
    PLATFORMS = ["linkedin", "indeed", "zip_recruiter", "google"]
    random.shuffle(LOCATIONS)

    for city in LOCATIONS:
        print(f"\n🌍 ARRIVING IN: {city.upper()}")
        
        for query in SEARCH_QUERIES:
            print(f"   🔎 Searching: [{query}]...")
            
            for platform in PLATFORMS:
                # Query Logic
                active_query = query
                if platform in ["linkedin", "indeed"]:
                    active_query += " -Senior -Sr -Staff -Principal -Lead -Manager"
                else:
                    active_query = query.replace('"', '') 

                # Location Logic
                search_loc = city
                if "Remote" in city and platform in ["linkedin", "google"]:
                    search_loc = "United States"
                
                # Batch Size
                batch_size = 20 if platform in ["linkedin", "google"] else 5
                
                try:
                    # FIX FOR GOOGLE JOBS: Explicitly map query to google_search_term
                    google_term = active_query if platform == "google" else None
                    
                    jobs = scrape_jobs(
                        site_name=[platform], 
                        search_term=active_query,
                        google_search_term=google_term, # <--- THE FIX
                        location=search_loc,
                        results_wanted=batch_size,
                        hours_old=HOURS_OLD, 
                        country_indeed='USA'
                    )
                    
                    if jobs.empty: continue
                    print(f"      [{platform.upper()}] Found {len(jobs)} raw jobs...")

                    for index, row in jobs.iterrows():
                        job_link = row.get('job_url')
                        title = str(row.get('title', ''))
                        company = str(row.get('company', ''))
                        raw_desc = str(row.get('description', ''))
                        description = clean_description(raw_desc)
                        
                        if job_link in existing_links: continue

                        if not is_title_clean(title): continue

                        if len(description) < 100:
                            description = "FETCH_ME"

                        new_row = [
                            "New", datetime.now().strftime("%Y-%m-%d"),
                            title, company, job_link, city, 
                            description[:40000], "", "", ""
                        ]
                        
                        try:
                            sheet.append_row(new_row)
                            existing_links.append(job_link)
                            total_added += 1
                            print(f"      ✅ LEAD CAPTURED [{platform.upper()}]: {title}")
                            time.sleep(1.0)
                        except: pass

                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    # print(f"      ⚠️ {platform.upper()} Error: {e}")
                    pass

        print(f"   💤 Taking a break...")
        time.sleep(random.uniform(5, 10))

    print(f"\n🎉 Run Complete. Added {total_added} leads.")

if __name__ == "__main__":
    run_scout()