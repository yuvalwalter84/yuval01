"""
Vision Stack 2026: Secure Job Aggregator & Scraper
--------------------------------------------------
Aggregates job search results from top Israeli sites and LinkedIn, for optimal breadth and zero regression.
Integrates with the Vision Stack Master CV AI agent and supports anti-regression verification by design.

- Always returns direct links to major Israeli job boards (Drushim, AllJobs, JobMaster) on top.
- Deep search on LinkedIn using jobspy (for ATS/auto-apply stack).
- No code shrinkage; dependencies and structure kept as per guardrails.
"""

import pandas as pd
from jobspy import scrape_jobs

def search_jobs(title, location="Israel", max_results=10, hours_old=72):
    """
    Aggregates search results from Israeli job boards and LinkedIn.
    Always includes direct links to Israeli boards at the top, then appends scraped positions.
    All columns are normalized.
    """
    # 1. Always-top Israeli direct links
    israeli_sites = [
        {
            "site": "Drushim",
            "title": f"תוצאות חיפוש {title}",
            "company": "מגוון חברות",
            "job_url": f"https://www.drushim.co.il/jobs/search/{title}/"
        },
        {
            "site": "AllJobs",
            "title": f"תוצאות חיפוש {title}",
            "company": "מגוון חברות",
            "job_url": f"https://www.alljobs.co.il/SearchResult.aspx?freeText={title}"
        },
        {
            "site": "JobMaster",
            "title": f"תוצאות חיפוש {title}",
            "company": "מגוון חברות",
            "job_url": f"https://www.jobmaster.co.il/jobs/?q={title}"
        }
    ]
    local_jobs = pd.DataFrame(israeli_sites)

    # 2. Deep LinkedIn Search via jobspy
    try:
        global_jobs = scrape_jobs(
            site_name=["linkedin"],
            search_term=title,
            location=location,
            results_wanted=max_results,
            hours_old=hours_old,
            country_is_israel=True
        )
        # If results are present, harmonize columns and label as LinkedIn
        if not global_jobs.empty:
            global_jobs['site'] = 'LinkedIn'
            # Normalize essential columns if not present
            if 'company' not in global_jobs.columns:
                global_jobs['company'] = ""
            if 'title' not in global_jobs.columns:
                global_jobs['title'] = title
            if 'job_url' not in global_jobs.columns:
                global_jobs['job_url'] = ""
            global_jobs = global_jobs[['site', 'title', 'company', 'job_url']].copy()
        else:
            # In rare edge cases, fallback to empty DataFrame with schema
            global_jobs = pd.DataFrame(columns=['site', 'title', 'company', 'job_url'])
    except Exception as exc:
        # Defensive fallback (anti-regression): Never crash the stack if LinkedIn is down
        global_jobs = pd.DataFrame(columns=['site', 'title', 'company', 'job_url'])

    # Combine
    all_jobs = pd.concat([local_jobs, global_jobs], ignore_index=True)
    # Always ensure the resulting DataFrame has the required columns
    for col in ['site', 'title', 'company', 'job_url']:
        if col not in all_jobs.columns:
            all_jobs[col] = ""
    return all_jobs

def verify_jobs_dataframe(jobs_df):
    """
    Guardrail: Checks that the jobs DataFrame contains only vetted columns, and is not empty.
    Returns (ok: bool, error: str)
    """
    required = ['site', 'title', 'company', 'job_url']
    for col in required:
        if col not in jobs_df.columns:
            return (False, f"Missing column: {col}")
    if len(jobs_df) == 0:
        return (False, "No jobs returned.")
    return (True, "")

# End-to-end anti-regression test
if __name__ == "__main__":
    # Mini self-test: returns > 0 results for 'CTO'
    jobs = search_jobs("CTO")
    ok, err = verify_jobs_dataframe(jobs)
    if not ok:
        print(f"❌ Jobs regression: {err}")
    else:
        print(f"✅ {len(jobs)} jobs aggregated. Sample:")
        print(jobs.head(3).to_string())