"""
Background Job Scout for Vision Stack 2026 - Assertive Autonomous Agent Mode.
Standalone script that runs job scrapers continuously and logs high-match jobs.
This script can be executed independently via: python background_scout.py
It loads preferences.json in EVERY cycle to get potential_roles, added_skills, and industry_focus,
and writes all actions to scout_logs.json. Uses discovered_jobs.csv as the data source.

NEW: Universal Scraper Architecture - Can scrape from any URL (career pages, XML sitemaps).
NEW: Keyword-based Pre-filter - Scans for mandatory keywords before AI calls.
"""

import os
import sys
import time
import csv
import json
import random
import pandas as pd
import re
import requests
from datetime import datetime
from urllib.parse import urljoin, urlparse
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # Fallback if bs4 not installed
from utils import (
    load_profile, load_user_learnings, scrape_jobs_with_timeout,
    scrape_israeli_job_boards_with_timeout, filter_blacklisted_jobs,
    validate_job_source, validate_job_description, send_notification,
    load_preferences, get_db_manager
)
from core_engine import CoreEngine

# Configuration
SCRAPE_INTERVAL_MINUTES = 30  # Run every 30 minutes (configurable)
HIGH_MATCH_THRESHOLD = 70  # Log jobs with match score >= 70%
HARD_EXCLUSION_THRESHOLD = 40  # Jobs below this score are permanently hidden
DISCOVERED_JOBS_CSV = 'discovered_jobs.csv'
SCOUT_LOGS_JSON = 'scout_logs.json'  # Will be resolved via get_user_log_file
SCOUT_STATUS_LOG = 'scout_status.log'  # Will be resolved via get_user_log_file
HIDDEN_JOBS_JSON = 'hidden_jobs.json'  # Jobs permanently excluded (< 40% score)

# Temporary "crumbs" bypass: disable LinkedIn for now
JOBSPY_SITES = ["indeed", "glassdoor"]

# Universal Scraper Configuration
CAREER_PAGE_PATTERNS = [
    '/careers', '/jobs', '/career', '/openings', '/positions', '/hiring',
    '/join-us', '/work-with-us', '/opportunities'
]
XML_SITEMAP_PATTERNS = ['/sitemap.xml', '/sitemap_jobs.xml', '/job-sitemap.xml']

# Random user-agent placeholder (JobSpy may or may not accept this kwarg; we handle safely)
USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Proxies placeholder (wire your proxy URL here if needed)
PROXIES = None

def simplify_search_query(query: str, max_words: int = 2) -> str:
    """
    Query Simplification: If persona roles are too long, truncate them to max_words.
    Example: "VP Technology & Innovation" -> "VP Technology"
    """
    try:
        if not query:
            return ""
        # Normalize whitespace, keep first N tokens
        tokens = [t for t in str(query).strip().split() if t]
        return " ".join(tokens[:max_words]) if tokens else ""
    except Exception:
        return str(query)[:50] if query else ""

def _prefs_signature(preferences: dict) -> str:
    """
    Create a stable signature for the parts of preferences.json that should trigger a cycle restart.
    We watch:
    - user_identity.preferred_roles
    - user_identity.auto_query
    """
    try:
        ui = (preferences or {}).get("user_identity", {}) if isinstance(preferences, dict) else {}
        snap = {
            "preferred_roles": ui.get("preferred_roles", []),
            "auto_query": ui.get("auto_query", "")
        }
        return json.dumps(snap, sort_keys=True, ensure_ascii=False)
    except Exception:
        return ""

def log_scout_action(message, log_type='info', user_id=None):
    """
    Write every action to user-specific scout_logs.json (in data/{user_id}/logs/scout_logs.json).
    
    Args:
        message: Action message to log
        log_type: Type of log ('info', 'success', 'warning', 'error')
        user_id: Optional user_id. If not provided, uses get_user_id() from utils
    """
    try:
        from utils import get_user_log_file, get_user_id
        if user_id is None:
            user_id = get_user_id()
        log_file = get_user_log_file(SCOUT_LOGS_JSON, user_id)
    except Exception:
        # Fallback if utils not available
        log_file = SCOUT_LOGS_JSON
    
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'type': log_type,
        'message': message
    }
    
    # Load existing logs
    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
                # Keep only last 1000 entries to avoid file bloat
                if len(logs) > 1000:
                    logs = logs[-1000:]
        except Exception as e:
            print(f"⚠️ Error loading scout logs: {e}")
            logs = []
    
    # Append new log entry
    logs.append(log_entry)
    
    # Save logs
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Error saving scout logs: {e}")
    
    # Also print to console
    print(f"[{log_type.upper()}] {message}")

def log_status(message: str, user_id=None):
    """
    Forced Visibility: append every status line to user-specific scout_status.log
    (in data/{user_id}/logs/scout_status.log) so you can inspect it even if the process
    is running detached from the terminal.
    
    Args:
        message: Status message to log
        user_id: Optional user_id. If not provided, uses get_user_id() from utils
    """
    try:
        from utils import get_user_log_file, get_user_id
        if user_id is None:
            user_id = get_user_id()
        log_file = get_user_log_file(SCOUT_STATUS_LOG, user_id)
    except Exception:
        # Fallback if utils not available
        log_file = SCOUT_STATUS_LOG
    
    try:
        ts = datetime.now().isoformat()
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{ts} {message}\n")
    except Exception:
        pass

def load_discovered_jobs():
    """
    Load existing discovered jobs from discovered_jobs.csv to avoid duplicates.
    This is the data source for tracking discovered jobs.
    """
    if not os.path.exists(DISCOVERED_JOBS_CSV):
        return set()
    
    discovered_urls = set()
    try:
        with open(DISCOVERED_JOBS_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('job_url'):
                    discovered_urls.add(row['job_url'])
    except Exception as e:
        log_scout_action(f"Error loading discovered jobs from {DISCOVERED_JOBS_CSV}: {e}", 'warning')
    
    return discovered_urls

def is_discovered_jobs_empty() -> bool:
    """
    Returns True if discovered_jobs.csv is missing OR has no data rows.
    """
    try:
        if not os.path.exists(DISCOVERED_JOBS_CSV):
            return True
        df = pd.read_csv(DISCOVERED_JOBS_CSV)
        return df.empty
    except Exception:
        # If we can't read it, treat as empty to trigger broad-search safety net
        return True

def log_discovered_job(job, match_score, role_analysis=None):
    """
    Log a high-match job to discovered_jobs.csv.
    This is the data source for storing discovered jobs.
    """
    fieldnames = ['timestamp', 'company', 'title', 'job_url', 'match_score', 'best_role', 'description_preview']
    
    # Ensure CSV exists with header
    file_exists = os.path.isfile(DISCOVERED_JOBS_CSV)
    
    job_data = {
        'timestamp': datetime.now().isoformat(),
        'company': job.get('company', 'Unknown'),
        'title': job.get('title', 'Unknown'),
        'job_url': job.get('job_url', ''),
        'match_score': match_score,
        'best_role': role_analysis.get('best_role', 'Unknown') if role_analysis else 'Unknown',
        'description_preview': job.get('description', '')[:500]  # First 500 chars
    }
    
    try:
        with open(DISCOVERED_JOBS_CSV, 'a', encoding='utf-8', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(job_data)
        
        log_scout_action(f"Logged high-match job to {DISCOVERED_JOBS_CSV}: {job_data['title']} @ {job_data['company']} (Score: {match_score}%)", 'success')
        
        # Send notification for high-match jobs
        try:
            send_notification({
                'company': job_data['company'],
                'title': job_data['title'],
                'job_url': job_data['job_url'],
                'match_score': match_score,
                'best_role': job_data['best_role']
            })
        except Exception as e:
            log_scout_action(f"Notification failed: {e}", 'warning')
        
        return True
    except Exception as e:
        log_scout_action(f"Error logging discovered job to {DISCOVERED_JOBS_CSV}: {e}", 'error')
        return False

def run_job_scout_cycle():
    """
    Run one complete job scout cycle: scrape, analyze, and log high-match jobs.
    CRITICAL: Re-loads preferences.json in EVERY cycle to get latest user updates (Focus, Skills, Roles).
    Uses discovered_jobs.csv as the data source for tracking discovered jobs.
    """
    log_scout_action(f"Starting job scout cycle at {datetime.now().isoformat()}", 'info')
    log_status("=== Starting scout cycle ===")
    
    # CRITICAL: Re-load preferences.json in EVERY cycle to see if user updated Focus or Skills through UI
    try:
        preferences = load_preferences()
        initial_pref_sig = _prefs_signature(preferences)
        potential_roles = preferences.get('user_identity', {}).get('preferred_roles', [])
        added_skills = preferences.get('user_identity', {}).get('added_skills', [])
        industry_focus = preferences.get('user_identity', {}).get('industry_focus', '')
        preferred_auto_query = preferences.get('user_identity', {}).get('auto_query', '')
        log_scout_action(f"Loaded preferences (re-loaded in every cycle): {len(potential_roles)} potential roles, {len(added_skills)} added skills, Industry Focus='{industry_focus}'", 'info')
        log_status(f"Loaded preferences: roles={len(potential_roles)} added_skills={len(added_skills)} industry_focus='{industry_focus}' auto_query_present={bool(preferred_auto_query)}")
    except Exception as e:
        log_scout_action(f"Error loading preferences.json in cycle: {e}", 'warning')
        initial_pref_sig = ""
        potential_roles = []
        added_skills = []
        industry_focus = ''
        preferred_auto_query = ''
    
    # Load profile and CV
    try:
        profile = load_profile()
        cv_text = profile.get('master_cv_text', '')
        if not cv_text:
            log_scout_action("No CV text in profile. Skipping scout cycle.", 'warning')
            return
    except Exception as e:
        log_scout_action(f"Error loading profile: {e}", 'error')
        return
    
    # Initialize engine
    try:
        engine = CoreEngine()
    except Exception as e:
        log_scout_action(f"Error initializing CoreEngine: {e}", 'error')
        return
    
    # Load user learnings for Digital Persona
    try:
        user_learnings = load_user_learnings()
    except Exception as e:
        log_scout_action(f"Error loading user learnings: {e}", 'warning')
        user_learnings = {}
    
    # Build Digital Persona (using latest preferences loaded above)
    try:
        digital_persona = engine.deep_profile_analysis(cv_text, skill_bucket=added_skills, rejection_learnings=user_learnings)
        # Update industry_focus if user set it manually
        if industry_focus:
            digital_persona['industry_focus'] = industry_focus
        log_scout_action(f"Built Digital Persona with Industry Focus='{digital_persona.get('industry_focus', '')}'", 'info')
    except Exception as e:
        log_scout_action(f"Error building Digital Persona: {e}", 'warning')
        digital_persona = None
    
    # Build Master Search Profile (using latest preferences loaded above)
    try:
        master_profile = engine.build_master_search_profile(cv_text, skill_bucket=added_skills, rejection_learnings=user_learnings)
    except Exception as e:
        log_scout_action(f"Error building Master Profile: {e}", 'warning')
        master_profile = None
    
    # Generate search strategy using potential_roles if available (from latest preferences)
    search_queries = []
    if potential_roles and len(potential_roles) > 0:
        # Use potential_roles as search queries (from preferences.json)
        search_queries = potential_roles[:5]  # Use top 5 roles
        log_scout_action(f"Using potential roles from preferences.json as search queries: {search_queries}", 'info')
        log_status(f"Top role queries (raw): {search_queries}")
    else:
        # Generate search strategy (using latest preferences)
        try:
            search_queries = engine.generate_search_strategy(
                digital_persona=digital_persona,
                skill_bucket=added_skills,
                cv_text=cv_text
            )
            log_scout_action(f"Generated search strategy: {search_queries}", 'info')
        except Exception as e:
            log_scout_action(f"Error generating search strategy: {e}", 'warning')
            search_queries = [profile.get('auto_query', 'CTO')]

    # Background Scout Sync:
    # If user updated preferred_roles or auto_query in preferences.json while this cycle is running,
    # restart the current cycle immediately (don't wait for the 30 minute sleep).
    try:
        latest_preferences = load_preferences()
        latest_sig = _prefs_signature(latest_preferences)
        if latest_sig and latest_sig != initial_pref_sig:
            log_scout_action("Detected preferences.json change (preferred_roles/auto_query). Restarting scout cycle to use new parameters.", 'info')
            return "restart"
    except Exception as e:
        log_scout_action(f"Preferences change check failed (non-blocking): {e}", 'warning')
    
    # Load previously discovered jobs from discovered_jobs.csv (the data source)
    discovered_urls = load_discovered_jobs()
    log_scout_action(f"Loaded {len(discovered_urls)} discovered jobs from {DISCOVERED_JOBS_CSV} to avoid duplicates", 'info')
    log_status(f"Discovered URLs already logged: {len(discovered_urls)}")
    
    # Scrape jobs from multiple sources
    all_jobs = []
    
    try:
        # 1. Scrape from JobSpy (LinkedIn, Indeed, Glassdoor) using top 5 role queries
        # Broaden Search Logic: Search for the top 5 roles per cycle (not just a single query)
        base_queries = []
        if search_queries:
            base_queries.extend(search_queries[:5])
        if preferred_auto_query:
            # Include auto_query as an additional base query (if present)
            base_queries.insert(0, preferred_auto_query)

        # Query Simplification: truncate role phrases to 2 words for better hit rates
        simplified_base = []
        seen = set()
        for q in base_queries:
            sq = simplify_search_query(q, max_words=2)
            if sq and sq not in seen:
                simplified_base.append(sq)
                seen.add(sq)

        # Add Remote/Hybrid variants by default
        jobspy_terms = []
        for sq in simplified_base:
            for term in [sq, f"{sq} remote", f"{sq} hybrid"]:
                if term not in seen:
                    seen.add(term)
                jobspy_terms.append(term)

        # Deduplicate while preserving order
        dedup_terms = []
        seen_terms = set()
        for t in jobspy_terms:
            if t not in seen_terms:
                seen_terms.add(t)
                dedup_terms.append(t)
        jobspy_terms = dedup_terms

        log_scout_action(f"Searching JobSpy for {len(jobspy_terms)} terms (top roles simplified): {jobspy_terms}", 'info')
        log_status(f"JobSpy sites: {JOBSPY_SITES}")
        for t in jobspy_terms:
            log_status(f"Trying query: {t}")
        try:
            jobspy_frames = []
            for term in jobspy_terms:
                try:
                    ua = random.choice(USER_AGENTS)
                    scrape_kwargs = {
                        "site_name": JOBSPY_SITES,
                        "search_term": term,
                        "location": "Israel",
                        "results_wanted": 100,  # Increase volume
                        "hours_old": 72,        # Last 3 days
                        "timeout": 30
                    }
                    # Optional placeholders (may not be supported by jobspy; we retry safely)
                    scrape_kwargs["user_agent"] = ua
                    scrape_kwargs["proxies"] = PROXIES

                    try:
                        jobspy_jobs = scrape_jobs_with_timeout(**scrape_kwargs)
                    except TypeError:
                        # JobSpy doesn't support user_agent/proxies in this environment; retry without
                        scrape_kwargs.pop("user_agent", None)
                        scrape_kwargs.pop("proxies", None)
                        jobspy_jobs = scrape_jobs_with_timeout(**scrape_kwargs)
                    # Verify API: print raw results count immediately after scraping (before filtering)
                    raw_count = 0
                    try:
                        raw_count = len(jobspy_jobs) if jobspy_jobs is not None else 0
                    except Exception:
                        raw_count = 0
                    print(f"DEBUG: Raw scraper found {raw_count} jobs for term='{term}'")
                    log_status(f"DEBUG: Raw scraper found {raw_count} jobs for term='{term}' (ua='{ua[:30]}...')")

                    if jobspy_jobs is not None and not jobspy_jobs.empty:
                        jobspy_frames.append(jobspy_jobs)
                        log_scout_action(f"Found {len(jobspy_jobs)} jobs from JobSpy for term='{term}'", 'success')
                except Exception as e:
                    log_scout_action(f"JobSpy scraping failed for term='{term}': {e}", 'warning')

            if jobspy_frames:
                merged_jobspy = pd.concat(jobspy_frames, ignore_index=True)
                if 'job_url' in merged_jobspy.columns:
                    merged_jobspy = merged_jobspy.drop_duplicates(subset=['job_url'], keep='first')
                # Cap total JobSpy jobs per cycle to control load (still much larger than before)
                merged_jobspy = merged_jobspy.head(200)
                all_jobs.append(merged_jobspy)
                log_scout_action(f"JobSpy merged results: {len(merged_jobspy)} jobs (capped at 200)", 'success')
                log_status(f"JobSpy merged jobs appended: {len(merged_jobspy)}")
        except Exception as e:
            log_scout_action(f"JobSpy scraping failed: {e}", 'warning')
            log_status(f"JobSpy scraping failed: {e}")

        # Re-check preferences between sources; restart if changed
        try:
            latest_preferences = load_preferences()
            latest_sig = _prefs_signature(latest_preferences)
            if latest_sig and latest_sig != initial_pref_sig:
                log_scout_action("Detected preferences.json change mid-cycle. Restarting scout cycle to use new parameters.", 'info')
                return "restart"
        except Exception as e:
            log_scout_action(f"Preferences change check failed (non-blocking): {e}", 'warning')
        
        # 2. Scrape from Israeli job boards using search queries
        log_scout_action(f"Scraping Israeli job boards with {len(search_queries[:3])} search terms...", 'info')
        try:
            israeli_search_terms = search_queries[:3]  # Limit to 3 terms
            israeli_jobs = scrape_israeli_job_boards_with_timeout(
                search_terms=israeli_search_terms,
                max_results_per_site=5,
                timeout=60  # Fix Scraping Abort: Increased timeout to 60 seconds for Israeli job boards
            )
            if israeli_jobs is not None and not israeli_jobs.empty:
                all_jobs.append(israeli_jobs)
                log_scout_action(f"Found {len(israeli_jobs)} jobs from Israeli boards", 'success')
                log_status(f"Israeli boards jobs appended: {len(israeli_jobs)}")
        except Exception as e:
            log_scout_action(f"Israeli boards scraping failed: {e}", 'warning')
            log_status(f"Israeli boards scraping failed: {e}")
    except Exception as e:
        log_scout_action(f"Error during job scraping: {e}", 'error')
        log_status(f"Error during job scraping: {e}")
        return

    # Query Refresh: if discovered_jobs.csv is still empty after this crawl attempt,
    # run a super-broad connectivity check.
    try:
        if is_discovered_jobs_empty():
            super_broad_terms = ["Software Israel", "High Tech Israel"]
            log_scout_action("discovered_jobs.csv is empty after crawl. Running Super Broad search to verify connectivity...", 'warning')
            log_status(f"Super Broad fallback triggered. Terms: {super_broad_terms}")
            for term in super_broad_terms:
                try:
                    ua = random.choice(USER_AGENTS)
                    scrape_kwargs = {
                        "site_name": JOBSPY_SITES,
                        "search_term": term,
                        "location": "Israel",
                        "results_wanted": 100,
                        "hours_old": 72,
                        "timeout": 30
                    }
                    scrape_kwargs["user_agent"] = ua
                    scrape_kwargs["proxies"] = PROXIES
                    try:
                        broad_jobs = scrape_jobs_with_timeout(**scrape_kwargs)
                    except TypeError:
                        scrape_kwargs.pop("user_agent", None)
                        scrape_kwargs.pop("proxies", None)
                        broad_jobs = scrape_jobs_with_timeout(**scrape_kwargs)

                    broad_count = 0
                    try:
                        broad_count = len(broad_jobs) if broad_jobs is not None else 0
                    except Exception:
                        broad_count = 0
                    print(f"DEBUG: Raw scraper found {broad_count} jobs for SUPER_BROAD term='{term}'")
                    log_status(f"DEBUG: Raw scraper found {broad_count} jobs for SUPER_BROAD term='{term}' (ua='{ua[:30]}...')")
                    if broad_jobs is not None and hasattr(broad_jobs, "empty") and not broad_jobs.empty:
                        all_jobs.append(broad_jobs)
                        log_scout_action(f"Super Broad search added {len(broad_jobs)} jobs for term='{term}'", 'success')
                except Exception as e:
                    log_scout_action(f"Super Broad search failed for term='{term}': {e}", 'warning')
                    log_status(f"Super Broad search failed for term='{term}': {e}")
    except Exception as e:
        log_status(f"Super Broad fallback check failed (non-blocking): {e}")
    
    # Merge and process jobs
    if not all_jobs:
        log_scout_action("No jobs found in this cycle", 'warning')
        return
    
    try:
        merged_jobs = pd.concat(all_jobs, ignore_index=True)
        
        # Remove duplicates
        if 'job_url' in merged_jobs.columns:
            merged_jobs = merged_jobs.drop_duplicates(subset=['job_url'], keep='first')
        
        # Filter blacklisted jobs
        merged_jobs = filter_blacklisted_jobs(merged_jobs)
        
        # Filter out already discovered jobs (from discovered_jobs.csv)
        if 'job_url' in merged_jobs.columns:
            merged_jobs = merged_jobs[~merged_jobs['job_url'].isin(discovered_urls)]
            log_scout_action(f"After filtering discovered jobs from {DISCOVERED_JOBS_CSV}, {len(merged_jobs)} new jobs to analyze", 'info')
        
        # Validate jobs (source verification, description length)
        valid_jobs = []
        for idx, job in merged_jobs.iterrows():
            is_valid_source, _ = validate_job_source(job)
            is_valid_desc, _ = validate_job_description(job)
            if is_valid_source and is_valid_desc:
                valid_jobs.append((idx, job))
        
        log_scout_action(f"Processing {len(valid_jobs)} valid jobs...", 'info')

        # Personal DNA Hard Constraints: pre-filter before any AI/token consumption
        try:
            jobs_dicts = []
            for _, j in valid_jobs:
                jd = j.to_dict() if hasattr(j, "to_dict") else dict(j)
                jobs_dicts.append({
                    "title": jd.get("title", ""),
                    "company": jd.get("company", ""),
                    "job_url": jd.get("job_url", ""),
                    "description": jd.get("description", "") or jd.get("description_preview", "")
                })
            kept, dropped = engine.pre_filter_jobs(jobs_dicts)
            kept_urls = {str(k.get("job_url", "") or "").strip() for k in kept if k.get("job_url")}
            if dropped:
                log_scout_action(f"Hard Constraints filtered out {len(dropped)} jobs before AI analysis.", 'info')
            # Rebuild valid_jobs in original structure, keeping only allowed job_urls
            if kept_urls:
                valid_jobs = [(idx, job) for (idx, job) in valid_jobs if str(job.get("job_url", "") or "").strip() in kept_urls]
        except Exception as e:
            log_scout_action(f"Hard Constraints pre-filter failed (non-blocking): {e}", 'warning')
        
        # Keyword Pre-filter: Before calling AI, scan for mandatory keywords
        # This saves tokens by skipping jobs that don't match basic requirements
        mandatory_keywords = []
        if digital_persona:
            tech_stack = digital_persona.get('tech_stack', [])
            role_level = digital_persona.get('role_level', '')
            if tech_stack:
                mandatory_keywords.extend(tech_stack[:3])
            if role_level:
                mandatory_keywords.append(role_level)
        if added_skills:
            mandatory_keywords.extend(added_skills[:3])
        
        # Pre-filter jobs by keywords before AI analysis
        prefiltered_jobs = []
        for idx, job in valid_jobs:
            # Check if job is already hidden
            if is_job_hidden(job.get('job_url', '')):
                continue  # Skip hidden jobs
            
            job_text = f"{job.get('title', '')} {job.get('description', '')}"
            if mandatory_keywords:
                passes, matched = keyword_pre_filter(job_text, mandatory_keywords)
                if not passes:
                    log_scout_action(f"Keyword pre-filter skipped job: {job.get('title', 'Unknown')} (no mandatory keywords found)", 'info')
                    continue  # Skip this job - no mandatory keywords
            prefiltered_jobs.append((idx, job))
        
        log_scout_action(f"Keyword pre-filter: {len(prefiltered_jobs)}/{len(valid_jobs)} jobs passed keyword check", 'info')
        
        # Analyze each job and log high-match ones to discovered_jobs.csv
        high_match_count = 0
        for idx, job in prefiltered_jobs:
            try:
                job_description = job.get('description', '')
                if not job_description:
                    continue
                
                # Cost Control: Summary-first approach - Use only first 1000 chars for initial scoring
                job_description_trimmed = job_description[:1000] if len(job_description) > 1000 else job_description
                
                # Perform multi-role analysis (using latest preferences)
                role_analysis = engine.analyze_multi_role_match(
                    job_description_trimmed,  # Use trimmed description for cost control
                    cv_text,
                    skill_bucket=added_skills,  # Uses latest preferences
                    master_profile=master_profile,
                    digital_persona=digital_persona,  # Uses latest preferences
                    job_url=job.get('job_url', ''),  # Strict caching key
                    job_title=job.get('title', '')
                )
                
                match_score = role_analysis.get('match_score', 0)
                
                # Deep Cleaning: Hard Exclusion Filter - Jobs below 40% are permanently hidden
                if match_score < HARD_EXCLUSION_THRESHOLD:
                    log_hidden_job(job, match_score, f"Score {match_score}% is below {HARD_EXCLUSION_THRESHOLD}% threshold")
                    discovered_urls.add(job.get('job_url', ''))  # Track to avoid duplicates
                    continue  # Skip this job - never show again
                
                # Log high-match jobs to discovered_jobs.csv (the data source)
                if match_score >= HIGH_MATCH_THRESHOLD:
                    log_discovered_job(job, match_score, role_analysis)
                    high_match_count += 1
                    discovered_urls.add(job.get('job_url', ''))  # Track to avoid duplicates in memory

                # Throttle the Scout: avoid hammering the free model endpoints
                time.sleep(10)
            except Exception as e:
                log_scout_action(f"Error analyzing job {idx}: {e}", 'warning')
                continue
        
        log_scout_action(f"Scout cycle complete. Found {high_match_count} high-match jobs (>= {HIGH_MATCH_THRESHOLD}%) and logged to {DISCOVERED_JOBS_CSV}", 'success')
    except Exception as e:
        log_scout_action(f"Error processing jobs: {e}", 'error')
        import traceback
        log_scout_action(traceback.format_exc(), 'error')

def run_background_scout():
    """
    Main function to run the background scout continuously as a persistent daemon.
    Runs job scraping and analysis every SCRAPE_INTERVAL_MINUTES (default 30 minutes).
    Each cycle re-loads preferences.json to get latest user updates (Focus, Skills, Roles).
    Uses discovered_jobs.csv as the data source for tracking discovered jobs.
    This function implements a while True loop with configurable delay.
    """
    log_scout_action(f"Background Job Scout started as persistent daemon. Running every {SCRAPE_INTERVAL_MINUTES} minutes.", 'info')
    log_scout_action(f"High-match jobs (>= {HIGH_MATCH_THRESHOLD}%) will be logged to {DISCOVERED_JOBS_CSV}", 'info')
    log_scout_action(f"Preferences.json is re-loaded in EVERY cycle to detect UI updates (Focus, Skills, Roles).", 'info')
    
    cycle_count = 0
    
    while True:
        try:
            cycle_count += 1
            log_scout_action(f"Cycle #{cycle_count} - {datetime.now().isoformat()}", 'info')
            
            # Run job scout cycle (re-loads preferences.json internally in EVERY cycle)
            cycle_result = run_job_scout_cycle()
            if cycle_result == "restart":
                log_scout_action("Restart requested. Restarting immediately with updated preferences...", 'info')
                time.sleep(2)
                continue
            
            # Wait for next cycle (SCRAPE_INTERVAL_MINUTES minutes)
            wait_seconds = SCRAPE_INTERVAL_MINUTES * 60
            log_scout_action(f"Waiting {SCRAPE_INTERVAL_MINUTES} minutes until next cycle...", 'info')
            time.sleep(wait_seconds)
        except KeyboardInterrupt:
            log_scout_action("Background scout stopped by user", 'info')
            break
        except Exception as e:
            log_scout_action(f"Unexpected error in background scout: {e}", 'error')
            import traceback
            log_scout_action(traceback.format_exc(), 'error')
            # Wait a bit before retrying
            log_scout_action("Waiting 5 minutes before retry...", 'info')
            time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    # Run background scout as standalone script (persistent daemon)
    run_background_scout()
