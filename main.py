import argparse
import asyncio
import pandas as pd
import json
import os
import re
import time
import litellm
from jobspy import scrape_jobs

# ייבוא מהקבצים המקומיים
try:
    from pdf_processor import PDFParser
    from job_agent import JobSearchAgent
except ImportError:
    print("❌ Error: Missing pdf_processor.py or job_agent.py in the directory.")

class JobSearchCLI:
    def __init__(self):
        print("🚀 Starting Professional Job Search (Israel Support)...")
        
        # איפוס והגדרה מחדש של המפתח
        raw_key = "AIzaSyCz8QuHJFJ02doY9pRmR3uk5qXzAO_0HtM"
        clean_key = raw_key.strip()
        
        # הגדרה בכל הרמות האפשריות
        os.environ["GEMINI_API_KEY"] = clean_key
        litellm.api_key = clean_key
        
        self.agent = JobSearchAgent()
        self.parser = PDFParser()

    def find_jobs_israel(self, title):
        """חיפוש משרות בישראל - LinkedIn ו-Indeed"""
        print(f"🔍 Searching for '{title}' jobs in Israel... (Please wait)")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed"], 
                search_term=title,
                location="Israel",
                results_wanted=15,
                hours_old=72,
                country_indeed='israel'
            )
            return jobs
        except Exception as e:
            print(f"❌ Search error: {e}")
            return pd.DataFrame()

    async def run(self, pdf_path):
        if not os.path.exists(pdf_path):
            print(f"❌ Error: File '{pdf_path}' not found.")
            return

        print("📄 Step 1: Reading CV...")
        resume_text = self.parser.extract_text(pdf_path)
        
        print("🧠 Step 2: AI Analyzing profile...")
        skills_raw = self.agent.extract_skills(resume_text)
        
        job_title = "Software Developer"
        try:
            clean_json = re.search(r'\{.*\}', skills_raw, re.DOTALL).group()
            skills_data = json.loads(clean_json)
            job_title = skills_data.get('top_job_titles', [job_title])[0]
        except:
            pass

        # Step 3: חיפוש משרות
        jobs_df = self.find_jobs_israel(job_title)

        if jobs_df is None or jobs_df.empty:
            print("⚠️ No jobs found. Trying broader search...")
            jobs_df = self.find_jobs_israel("Software Engineer")

        if jobs_df is None or jobs_df.empty:
            print("❌ No results found.")
            return

        print(f"✅ Found {len(jobs_df)} jobs! Step 4: AI Match Scoring...")
        
        final_results = []
        for _, row in jobs_df.iterrows():
            title = str(row.get('title', 'Unknown Title'))
            desc = str(row.get('description', 'No description available'))
            company = row.get('company', 'N/A')
            
            job_info = f"Title: {title}\nCompany: {company}\nDescription: {desc[:500]}"
            
            score = 0
            try:
                match_raw = self.agent.match_and_score(resume_text, job_info)
                match_json_str = re.search(r'\{.*\}', match_raw, re.DOTALL).group()
                match_data = json.loads(match_json_str)
                score = int(match_data.get('match_score', 0))
                time.sleep(1) 
            except:
                # ניסיון חילוץ מספר פשוט מהטקסט אם ה-JSON נכשל
                nums = re.findall(r'\d+', str(match_raw)) if 'match_raw' in locals() else []
                score = int(nums[0]) if nums and int(nums[0]) <= 100 else 0
            
            final_results.append({
                "Title": title,
                "Company": company,
                "Score": score,
                "Link": row.get('job_url', 'N/A')
            })

        output_df = pd.DataFrame(final_results).sort_values(by="Score", ascending=False)
        output_df.to_csv("jobs_tracker.csv", index=False, encoding='utf-8-sig')
        
        print("\n" + "="*80)
        print(f"🎯 TOP MATCHES FOR YOU IN ISRAEL:")
        print("="*80)
        print(output_df[["Title", "Company", "Score"]].head(15).to_string(index=False))
        print("="*80)
        print(f"\n✅ Done! Check 'jobs_tracker.csv' for links.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", type=str, required=True)
    args = parser.parse_args()
    asyncio.run(JobSearchCLI().run(args.resume))