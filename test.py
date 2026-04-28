import pandas as pd
import gspread
import html
from jobspy import scrape_jobs
from datetime import datetime
import time

# --- ⚙️ TEST CONFIGURATION ---
SHEET_NAME = "Job_Hunt_Auto"
# 30 Days lookback (Ensures we find SOMETHING)
HOURS_OLD = 720 
MAX_LEADS_TO_FIND = 5

# --- 🔍 BROAD SEARCH ---
# We use a very generic term just to test the pipeline
SEARCH_QUERIES = ["Python", "Data"]
LOCATIONS = ["Remote", "New York, NY"]

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

# --- 🕵️ THE FOOLPROOF SCOUT ---
def run_test_scout():
    print(f"🧪 TEST MODE: Finding {MAX_LEADS_TO_FIND} leads...")
    
    try:
        sheet = connect_to_sheet()
        existing_links = sheet.col_values(5)
    except Exception as e:
        print(f"❌ Error connecting to Sheets: {e}")
        return

    total_added = 0
    # Use Indeed + LinkedIn
    PLATFORMS = ["linkedin", "indeed"] 

    for city in LOCATIONS:
        if total_added >= MAX_LEADS_TO_FIND: break
        print(f"\n🌍 ARRIVING IN: {city.upper()}")
        
        for query in SEARCH_QUERIES:
            if total_added >= MAX_LEADS_TO_FIND: break
            print(f"   🔎 Searching: [{query}]...")
            
            for platform in PLATFORMS:
                if total_added >= MAX_LEADS_TO_FIND: break
                
                # Simple Logic for Test
                search_loc = city
                if "Remote" in city and platform == "linkedin":
                    search_loc = "United States"
                
                try:
                    jobs = scrape_jobs(
                        site_name=[platform], 
                        search_term=query,
                        location=search_loc,
                        results_wanted=5, 
                        hours_old=HOURS_OLD, 
                        country_indeed='USA'
                    )
                    
                    if jobs.empty: 
                        print(f"      [{platform.upper()}] Returned 0 results.")
                        continue
                        
                    print(f"      [{platform.upper()}] Found {len(jobs)} raw jobs...")

                    for index, row in jobs.iterrows():
                        if total_added >= MAX_LEADS_TO_FIND: break
                        
                        job_link = row.get('job_url')
                        title = str(row.get('title', ''))
                        company = str(row.get('company', ''))
                        desc = clean_description(str(row.get('description', '')))
                        
                        if job_link in existing_links: 
                            # print("      Skipping Duplicate")
                            continue

                        # Mark for fetching if description is short
                        if len(desc) < 100: desc = "FETCH_ME"

                        new_row = [
                            "New", datetime.now().strftime("%Y-%m-%d"),
                            title, company, job_link, city, 
                            desc[:40000], "", "", ""
                        ]
                        
                        try:
                            sheet.append_row(new_row)
                            existing_links.append(job_link)
                            total_added += 1
                            print(f"      ✅ ADDED: {title}")
                        except Exception as e:
                            print(f"      ⚠️ Sheet Error: {e}")

                    time.sleep(2)
                except Exception as e:
                    print(f"      ⚠️ {platform.upper()} Error: {e}")

    print(f"\n🎉 Test Complete. Added {total_added} leads.")

if __name__ == "__main__":
    run_test_scout()