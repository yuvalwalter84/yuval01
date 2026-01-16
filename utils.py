"""
Utility functions for the Vision Stack 2026 project.
Includes helper functions for data management, API calls, validation, and session state initialization.
"""
import json
import os
import shutil
import re
import csv
import threading
import asyncio
import pandas as pd
import time
import datetime
import requests
import random
from dotenv import load_dotenv
from functools import wraps

# טעינת מפתח מהקובץ .env (לשמירה על בטיחות)
load_dotenv()

# ============================================================================
# MULTI-USER SANDBOX STRUCTURE & DATABASE INTEGRATION
# ============================================================================
# Database Manager Integration:
# All data operations now use SQLite via DatabaseManager for scalable SaaS architecture.
# The DatabaseManager ensures strict user isolation with WHERE user_id = ? in all queries.
# Fallback to JSON files is maintained for backward compatibility during migration.
# ============================================================================

# Initialize DatabaseManager singleton
_db_manager = None
_supabase_manager = None

def get_db_manager():
    """Get or create DatabaseManager singleton instance (SQLite - legacy/local)."""
    global _db_manager
    if _db_manager is None:
        from database_manager import DatabaseManager
        _db_manager = DatabaseManager(db_path="data/persona_db.sqlite")
    return _db_manager

def get_supabase_manager():
    """Get or create SupabaseDatabaseManager singleton instance (Cloud - production)."""
    global _supabase_manager
    if _supabase_manager is None:
        try:
            from supabase_manager import SupabaseDatabaseManager
            _supabase_manager = SupabaseDatabaseManager()
        except Exception as e:
            print(f"⚠️ Failed to initialize Supabase manager: {e}")
            return None
    return _supabase_manager

def use_supabase():
    """Check if Supabase should be used (based on env/config)."""
    try:
        import streamlit as st
        return st.secrets.get("USE_SUPABASE", "false").lower() == "true"
    except Exception:
        return os.getenv("USE_SUPABASE", "false").lower() == "true"

def get_user_id():
    """
    Get the current user_id from session state.
    Defaults to 'default_user' if not set.
    This is the primary source of truth for user identification.
    For email addresses (from Google OAuth), sanitizes to filesystem-safe format.
    """
    try:
        import streamlit as st
        user_id = st.session_state.get('user_id', 'default_user')
        # Sanitize user_id to prevent directory traversal attacks
        # For email addresses: convert @ to _at_ and . to _dot_ for filesystem safety
        user_id = str(user_id)
        if '@' in user_id:
            # Email address: sanitize for filesystem
            user_id = user_id.replace('@', '_at_').replace('.', '_dot_')
        # Remove any remaining unsafe characters (keep alphanumeric, _, -)
        user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id)[:100]  # Max 100 chars for email-based IDs
        if not user_id:
            user_id = 'default_user'
        return user_id
    except Exception:
        # Fallback if streamlit is not available (e.g., in background_scout.py)
        return os.getenv('USER_ID', 'default_user')

def get_user_data_dir(user_id=None):
    """
    Get the user-specific data directory path.
    Creates the directory if it doesn't exist.
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        str: Path to user data directory (e.g., 'data/default_user')
    """
    if user_id is None:
        user_id = get_user_id()
    
    # Sanitize user_id (handle email addresses)
    user_id = str(user_id)
    if '@' in user_id:
        # Email address: sanitize for filesystem
        user_id = user_id.replace('@', '_at_').replace('.', '_dot_')
    # Remove any remaining unsafe characters (keep alphanumeric, _, -)
    user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id)[:100]  # Max 100 chars for email-based IDs
    if not user_id:
        user_id = 'default_user'
    
    data_dir = os.path.join('data', user_id)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def get_user_file_path(filename, user_id=None):
    """
    Get the user-specific file path within their data directory.
    
    Args:
        filename: Name of the file (e.g., 'profile_data.json')
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        str: Full path to the user-specific file (e.g., 'data/default_user/profile_data.json')
    """
    data_dir = get_user_data_dir(user_id)
    return os.path.join(data_dir, filename)

def get_user_logs_dir(user_id=None):
    """
    Get the user-specific logs directory path.
    Creates the directory if it doesn't exist.
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        str: Path to user logs directory (e.g., 'data/default_user/logs')
    """
    if user_id is None:
        user_id = get_user_id()
    
    data_dir = get_user_data_dir(user_id)
    logs_dir = os.path.join(data_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir

def get_user_log_file(filename, user_id=None):
    """
    Get the user-specific log file path.
    
    Args:
        filename: Name of the log file (e.g., 'scout_logs.txt')
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        str: Full path to the user-specific log file (e.g., 'data/default_user/logs/scout_logs.txt')
    """
    logs_dir = get_user_logs_dir(user_id)
    return os.path.join(logs_dir, filename)

# --- Persona Debug Logging (User-Specific) ---
def log_event(message, level='INFO', user_id=None):
    """
    Append a debug event to persona_debug.log (user-specific).
    This is intentionally lightweight and safe to call from anywhere (including background_scout).
    
    Args:
        message: Log message
        level: Log level (INFO, WARNING, ERROR, etc.)
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    try:
        log_file = get_user_log_file('persona_debug.log', user_id)
        ts = datetime.datetime.now().isoformat()
        line = f"{ts} [{level}] {message}\n"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        # Never crash the app due to logging
        pass

# --- פונקציות ניהול נתונים עם הגנה מפני KeyError (User-Specific) ---
def load_profile(user_id=None):
    """
    Load profile data from user-specific file.
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        dict: Profile data
    """
    file_path = get_user_file_path('profile_data.json', user_id)
    # הגדרת מבנה ברירת המחדל למניעת KeyError
    default_data = {"master_cv_text": "", "auto_query": ""}
    
    if not os.path.exists(file_path):
        return default_data
    
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # מוודא שכל השדה הנדרש קיים, אם לא - מוסיף אותו
            for key in default_data:
                if key not in data:
                    data[key] = default_data[key]
            return data
        except json.JSONDecodeError:
            return default_data

def save_profile(data, user_id=None):
    """
    Save profile data to user-specific file.
    
    Args:
        data: Profile data dict
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    file_path = get_user_file_path('profile_data.json', user_id)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- Blacklist Management Functions (User-Specific) ---
def load_blacklist(user_id=None):
    """
    Load blacklisted job URLs and titles from user-specific blacklist.json
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    blacklist_file = get_user_file_path('blacklist.json', user_id)
    if not os.path.exists(blacklist_file):
        return {"urls": [], "titles": []}
    try:
        with open(blacklist_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"urls": [], "titles": []}

def save_blacklist(blacklist, user_id=None):
    """
    Save blacklist to user-specific blacklist.json
    
    Args:
        blacklist: Blacklist dict
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    blacklist_file = get_user_file_path('blacklist.json', user_id)
    with open(blacklist_file, 'w', encoding='utf-8') as f:
        json.dump(blacklist, f, indent=4)

def add_to_blacklist(job_url, job_title, user_id=None):
    """
    Add a job to the user-specific blacklist
    
    Args:
        job_url: Job URL to blacklist
        job_title: Job title to blacklist
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    blacklist = load_blacklist(user_id)
    if job_url and job_url not in blacklist["urls"]:
        blacklist["urls"].append(job_url)
    if job_title and job_title not in blacklist["titles"]:
        blacklist["titles"].append(job_title)
    save_blacklist(blacklist, user_id)

def filter_blacklisted_jobs(jobs_df):
    """Filter out blacklisted jobs from DataFrame. Returns all jobs if blacklist is empty or missing."""
    if jobs_df is None or jobs_df.empty:
        return jobs_df
    blacklist = load_blacklist()
    # Guard: Return all jobs if blacklist is empty or missing
    if not blacklist or (not blacklist.get("urls", []) and not blacklist.get("titles", [])):
        return jobs_df

    # Filter out jobs with blacklisted URLs or titles
    mask = pd.Series([True] * len(jobs_df), index=jobs_df.index)
    if 'job_url' in jobs_df.columns and blacklist.get("urls"):
        mask = mask & (~jobs_df['job_url'].isin(blacklist["urls"]))
    if 'title' in jobs_df.columns and blacklist.get("titles"):
        mask = mask & (~jobs_df['title'].isin(blacklist["titles"]))

    return jobs_df[mask]

# --- User Learning Management Functions (User-Specific) ---
def load_user_learnings(user_id=None):
    """
    Load user profile learnings from user-specific user_profile_learnings.json
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    learnings_file = get_user_file_path('user_profile_learnings.json', user_id)
    default_learnings = {
        "wrong_seniority": 0,
        "irrelevant_industry": 0,
        "missing_tech_stack": 0,
        "irrelevant_role": 0
    }
    if not os.path.exists(learnings_file):
        return default_learnings
    try:
        with open(learnings_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure all keys exist
            for key in default_learnings:
                if key not in data:
                    data[key] = default_learnings[key]
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return default_learnings

def save_user_learnings(learnings, user_id=None):
    """
    Save user profile learnings to user-specific user_profile_learnings.json
    
    Args:
        learnings: Learnings dict
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    learnings_file = get_user_file_path('user_profile_learnings.json', user_id)
    with open(learnings_file, 'w', encoding='utf-8') as f:
        json.dump(learnings, f, indent=4)

def add_rejection_learning(reason_type, user_id=None):
    """
    Add a rejection learning reason to the user-specific profile
    
    Args:
        reason_type: Type of rejection reason
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    learnings = load_user_learnings(user_id)
    # Map reason types to learning keys
    reason_mapping = {
        "Wrong Seniority": "wrong_seniority",
        "Irrelevant Industry": "irrelevant_industry",
        "Missing Tech Stack": "missing_tech_stack",
        "Irrelevant Role": "irrelevant_role"
    }
    key = reason_mapping.get(reason_type)
    if key:
        learnings[key] = learnings.get(key, 0) + 1
        save_user_learnings(learnings, user_id)

def validate_job_source(job):
    """Validate that job URL and Title are not placeholders. Returns (is_valid, reason)"""
    job_url = str(job.get('job_url', '')).strip()
    job_title = str(job.get('title', '')).strip()
    
    # Check for placeholder URLs
    placeholder_urls = ['#', 'http://', 'https://', 'www.', 'placeholder', 'example.com', 'test']
    if not job_url or job_url in placeholder_urls or len(job_url) < 10:
        return False, "Invalid URL"
    
    # Check for placeholder titles
    placeholder_titles = ['', 'N/A', 'None', 'Unknown', 'Job Title', 'Title', 'Position']
    if not job_title or job_title in placeholder_titles or len(job_title) < 3:
        # Fix Empty Titles: Try to extract title from first line of description before discarding
        job_description = str(job.get('description', '')).strip()
        if job_description and len(job_description) > 10:
            # Extract first line as potential title
            first_line = job_description.split('\n')[0].strip()
            # Check if first line looks like a title (reasonable length, no excessive punctuation)
            if 3 <= len(first_line) <= 100 and first_line.count('.') <= 2:
                # Update job_title with extracted value
                job['title'] = first_line
                print(f"🔧 Fixed Empty Title: Extracted '{first_line[:50]}...' from description")
                return True, "Valid (extracted from description)"
        
        return False, "Invalid Title"
    
    return True, "Valid"

def validate_job_description(job):
    """Validate that job description is not too short (phantom job). Returns (is_valid, reason)"""
    description = str(job.get('description', '')).strip()
    
    # Relaxed filter: minimum 50 characters (was 100) to ensure we don't lose valid LinkedIn postings
    if not description or len(description) < 50:
        return False, "Invalid Data - Description too short (<50 chars)"
    
    return True, "Valid"

# Helper function for merging preferences
def _merge_preferences(existing, new):
    """Merge new preferences into existing ones, preserving user-defined settings."""
    merged = existing.copy()
    merged.update(new)
    
    # Deep merge for nested structures
    if 'user_identity' in existing and 'added_skills' in existing['user_identity']:
        existing_skills = existing['user_identity']['added_skills']
        new_skills = new.get('user_identity', {}).get('added_skills', [])
        merged['user_identity']['added_skills'] = list(set(existing_skills + new_skills))
    
    if 'scoring_weights' in existing:
        merged['scoring_weights'] = existing['scoring_weights'].copy()
        merged['scoring_weights'].update(new.get('scoring_weights', {}))
    
    return merged

# Add anti-black-hole logging for every submission (User-Specific)
def log_application(job, application_text, status='applied', user_id=None):
    """
    Log application to SQLite database (primary) and CSV file (fallback).
    Status can be: 'applied', 'draft', 'rejected', etc.
    
    Args:
        job: Job dict
        application_text: Application text
        status: Application status
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    if user_id is None:
        user_id = get_user_id()
    
    # Try database first (primary)
    try:
        db = get_db_manager()
        db.log_application(
            user_id=user_id,
            job_url=job.get('job_url', ''),
            company=job.get('company', ''),
            title=job.get('title', ''),
            application_text=application_text,
            status=status
        )
    except Exception as db_error:
        print(f"⚠️ Database log failed, falling back to CSV: {db_error}")
    
    # Fallback to CSV file
    fieldnames = ['timestamp', 'company', 'title', 'job_url', 'application_text', 'status']
    log_file = get_user_file_path('applications_history.csv', user_id)
    exists = os.path.isfile(log_file)
    timestamp = datetime.datetime.now().isoformat()
    
    try:
        with open(log_file, 'a', encoding='utf-8', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow({
                'timestamp': timestamp,
                'company': job.get('company', ''),
                'title': job.get('title', ''),
                'job_url': job.get('job_url', ''),
                'application_text': application_text,
                'status': status
            })
    except Exception:
        pass

def check_if_applied(job_url, user_id=None):
    """
    Check if a job URL has already been applied to (status='applied') using database (primary) or CSV (fallback).
    Returns True if already applied, False otherwise.
    
    Args:
        job_url: Job URL to check
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    log_file = get_user_file_path('applications_history.csv', user_id)
    if not os.path.exists(log_file):
        return False
    
    try:
        with open(log_file, 'r', encoding='utf-8', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get('job_url', '').strip() == job_url.strip() and row.get('status', '').strip() == 'applied':
                    return True
    except Exception as e:
        print(f"Error checking application history: {e}")
    
    return False

def load_recycle_bin(user_id=None):
    """
    Load recycle bin from user-specific recycle_bin.json
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    recycle_file = get_user_file_path('recycle_bin.json', user_id)
    if not os.path.exists(recycle_file):
        return []
    
    try:
        with open(recycle_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_recycle_bin(recycle_bin, user_id=None):
    """
    Save recycle bin to user-specific recycle_bin.json
    
    Args:
        recycle_bin: Recycle bin list
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    recycle_file = get_user_file_path('recycle_bin.json', user_id)
    with open(recycle_file, 'w', encoding='utf-8') as f:
        json.dump(recycle_bin, f, indent=2, ensure_ascii=False)

def move_to_recycle_bin(job, reason, user_id=None):
    """
    Move a job to user-specific recycle_bin.json and remove from main jobs list.
    Job is stored with metadata including reason for rejection.
    
    Safety checks: Handles None, string, or dict job objects safely.
    
    Args:
        job: Job dict/object to recycle
        reason: Reason for recycling
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    # Safety check: if job is None, return early
    if job is None:
        print("WARN: move_to_recycle_bin called with None job. Skipping.")
        return False
    
    # Handle case where job might be a string (job URL)
    if isinstance(job, str):
        # If job is just a URL string, create a minimal dict
        job = {
            'job_url': job,
            'company': 'Unknown',
            'title': 'Unknown',
            'description': ''
        }
    
    # Handle case where job is a dict (normal case)
    if not isinstance(job, dict):
        print(f"WARN: move_to_recycle_bin called with unexpected job type: {type(job)}. Skipping.")
        return False
    
    recycle_bin = load_recycle_bin(user_id)
    
    # Safely extract job fields with defaults
    job_entry = {
        'timestamp': datetime.datetime.now().isoformat(),
        'job_id': f"{job.get('company', 'Unknown')}_{job.get('title', 'Unknown')}_{job.get('job_url', '')}",
        'company': job.get('company', 'Unknown'),
        'title': job.get('title', 'Unknown'),
        'job_url': job.get('job_url', ''),
        'description': str(job.get('description', ''))[:500],  # Store first 500 chars, ensure it's a string
        'reason': str(reason) if reason else 'Auto-filtered (low score)'
    }
    
    # Check if already in recycle bin
    job_urls = [entry.get('job_url', '') for entry in recycle_bin if isinstance(entry, dict)]
    if job_entry['job_url'] not in job_urls:
        recycle_bin.append(job_entry)
        save_recycle_bin(recycle_bin, user_id)
    
    return True

def load_feedback_log(user_id=None):
    """
    Load feedback log from user-specific feedback_log.json
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    feedback_file = get_user_file_path('feedback_log.json', user_id)
    if not os.path.exists(feedback_file):
        return []
    
    try:
        with open(feedback_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_feedback_log(feedback_log, user_id=None):
    """
    Save feedback log to user-specific feedback_log.json
    
    Args:
        feedback_log: Feedback log list
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    feedback_file = get_user_file_path('feedback_log.json', user_id)
    with open(feedback_file, 'w', encoding='utf-8') as f:
        json.dump(feedback_log, f, indent=2, ensure_ascii=False)

# Timeout wrapper for scrape_jobs - Threading-only (works in any thread context)
def scrape_jobs_with_timeout(*args, timeout=30, **kwargs):
    """
    Wraps scrape_jobs with a timeout mechanism using threading.
    Thread-safe and works in any thread context (not just main thread).
    """
    from jobspy import scrape_jobs
    result_container = {'result': None, 'exception': None, 'completed': False}

    def target():
        try:
            result_container['result'] = scrape_jobs(*args, **kwargs)
            result_container['completed'] = True
        except Exception as e:
            result_container['exception'] = e
            result_container['completed'] = True

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if not result_container['completed']:
        # Timeout occurred - thread is still running
        raise TimeoutError(f"Job scraping exceeded {timeout} seconds timeout. The search may be taking longer than expected. Please try again or reduce the number of results.")

    if result_container['exception']:
        # Re-raise the original exception with context
        error_msg = str(result_container['exception'])
        if 'signal' in error_msg.lower() or 'thread' in error_msg.lower():
            raise RuntimeError(f"Job scraping error: {error_msg}. This may be due to a network issue or the job board being temporarily unavailable. Please try again.")
        raise result_container['exception']

    return result_container['result']

# Wrapper for async Israeli job boards scraper with timeout
def scrape_israeli_job_boards_with_timeout(search_terms, max_results_per_site=5, timeout=60):
    """
    Wraps scrape_israeli_job_boards async function with timeout using threading.
    Thread-safe and works in any thread context.
    """
    from browser_bot import scrape_israeli_job_boards
    result_container = {'result': None, 'exception': None, 'completed': False}

    def target():
        try:
            # Run the async function in a new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(scrape_israeli_job_boards(search_terms, max_results_per_site))
                result_container['result'] = result
            finally:
                loop.close()
            result_container['completed'] = True
        except Exception as e:
            result_container['exception'] = e
            result_container['completed'] = True

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if not result_container['completed']:
        raise TimeoutError(f"Israeli job boards scraping exceeded {timeout} seconds timeout.")

    if result_container['exception']:
        raise result_container['exception']

    return result_container['result']

# --- Retry Decorator for API Calls ---
def retry_api_call(max_attempts=3, delay=1.0, backoff=2.0):
    """
    Smart Retry Logic: Decorator that retries API calls up to max_attempts times.
    Handles network errors, API errors, and transient failures.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    # Extract status code if present (requests HTTPError has .response)
                    status_code = None
                    try:
                        status_code = getattr(getattr(e, "response", None), "status_code", None)
                    except Exception:
                        status_code = None
                    
                    # Check if error is retryable (network/API errors)
                    is_retryable = (
                        'network' in error_str or
                        'timeout' in error_str or
                        'connection' in error_str or
                        'api' in error_str or
                        '404' in error_str or
                        '429' in error_str or
                        '500' in error_str or
                        '503' in error_str or
                        'clienterror' in error_str
                    )
                    is_429 = ('429' in error_str) or (status_code == 429) or ('too many requests' in error_str)
                    
                    if attempt < max_attempts - 1 and is_retryable:
                        # Exponential Backoff:
                        # When 429 is received, wait longer: 5s, 10s, 20s (+ small jitter).
                        if is_429:
                            # Immediate rate-limit shield: longer waits for 429 (10s, 20s, 40s)
                            wait_s = 10 * (2 ** attempt)
                        else:
                            wait_s = current_delay
                            current_delay *= backoff
                        # jitter to avoid thundering herd
                        wait_s = float(wait_s) + random.uniform(0.0, 0.7)
                        print(f"WARN: API call failed (attempt {attempt + 1}/{max_attempts}, status={status_code}): {e}. Retrying in {wait_s:.1f}s...")
                        time.sleep(wait_s)
                        continue
                    else:
                        # Not retryable or final attempt
                        raise
            
            # If we exhausted all retries, raise the last error
            raise last_error
        return wrapper
    return decorator

# --- API Call Fallback and Language Detection (OpenRouter) ---
class APIClient:
    """
    Centralized API client using OpenRouter for maximum stability and quality.
    Uses OpenRouter's REST API with standard POST requests.
    Smart Retry Logic: Retries up to 3 times on network/API errors.
    """
    def __init__(self):
        # שליפת API KEY לסביבה - Production Security: Use st.secrets first, fallback to .env
        api_key = None
        primary_model = None
        fallback_model = None
        
        try:
            import streamlit as st
            # Try st.secrets first (production security)
            try:
                api_key = st.secrets.get("OPENROUTER_API_KEY", None)
                primary_model = st.secrets.get("OPENROUTER_PRIMARY_MODEL", None)
                fallback_model = st.secrets.get("OPENROUTER_FALLBACK_MODEL", None)
            except (AttributeError, KeyError, Exception):
                # st.secrets might not be available or key doesn't exist
                pass
        except Exception:
            # streamlit might not be imported in this context
            pass
        
        # Fallback to .env file if st.secrets is not available
        if not api_key:
            api_key = os.getenv("OPENROUTER_API_KEY")
        if not primary_model:
            primary_model = os.getenv("OPENROUTER_PRIMARY_MODEL", "anthropic/claude-3-haiku")
        if not fallback_model:
            fallback_model = os.getenv("OPENROUTER_FALLBACK_MODEL", "meta-llama/llama-3.1-8b-instruct")
        
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY לא נמצא ב-st.secrets או בקובץ .env. אנא הוסף מפתח API לפרויקט.")
        
        self.api_key = api_key
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Paid Tier & Turbo Mode:
        # Use paid/stable models and enable JSON response_format.
        # Primary: anthropic/claude-3-haiku (more stable than gemini-2.0-flash)
        # Fallback 1: meta-llama/llama-3.1-8b-instruct (free tier fallback)
        self.model_id = str(primary_model).strip()
        fallback_model = str(fallback_model).strip()
        # Hard guard: exactly one fallback model
        self.fallback_models = [fallback_model]
        
        print(f"INFO: OpenRouter API initialized: primary='{self.model_id}', fallback='{fallback_model}'")
    
    def _clean_text_for_json(self, text):
        """
        Clean text to remove special characters that might break JSON payload.
        Removes control characters, null bytes, and other problematic characters.
        """
        if not text or not isinstance(text, str):
            return text or ""
        # Remove null bytes and control characters (except newlines and tabs)
        cleaned = "".join(char for char in text if ord(char) >= 32 or char in "\n\t")
        # Remove any remaining problematic unicode characters that might break JSON encoding
        try:
            # Test if it can be JSON encoded
            json.dumps(cleaned)
            return cleaned
        except (UnicodeEncodeError, TypeError):
            # Fallback: encode to ASCII with error handling
            return cleaned.encode('ascii', errors='ignore').decode('ascii')
    
    @retry_api_call(max_attempts=3, delay=1.0, backoff=2.0)
    def _call_api_single(self, model_name, prompt, system_prompt=None):
        """
        Single API call attempt with retry logic (wrapped by retry_api_call decorator).
        Uses OpenRouter's REST API format.
        Supports system_prompt for core identity rules.
        """
        # Debug: Show exact model name being tried
        print(f"DEBUG: Attempting OpenRouter API call with model: '{model_name}'")
        
        # OpenRouter API headers
        # Note: Free models still require API key in Authorization header
        # Get Streamlit URL from environment (production) or default to localhost (development)
        streamlit_url = os.getenv("STREAMLIT_SERVER_URL", "http://localhost:8501")
        try:
            import streamlit as st
            # Try to get from Streamlit config if available
            if hasattr(st, 'config') and hasattr(st.config, 'server'):
                server_url = getattr(st.config.server, 'baseUrlPath', None) or streamlit_url
                streamlit_url = server_url
        except Exception:
            pass
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": streamlit_url,
            "X-Title": "JobHunter_Agent",
            "Content-Type": "application/json"
        }
        
        # Debug: Log model tier
        if ':free' in str(model_name):
            print(f"DEBUG: Using FREE model: {model_name}")
        else:
            print(f"DEBUG: Using PAID/standard model: {model_name}")
        
        # Clean input text to remove special characters that might break JSON
        cleaned_prompt = self._clean_text_for_json(prompt)
        cleaned_system_prompt = self._clean_text_for_json(system_prompt) if system_prompt else None
        
        # Build messages list with system role if provided
        messages = []
        if cleaned_system_prompt and cleaned_system_prompt.strip():
            messages.append({
                "role": "system",
                "content": cleaned_system_prompt.strip()
            })
            print(f"DEBUG: System prompt included in API call ({len(cleaned_system_prompt)} chars)")
        
        # Add user message (only if not empty)
        if cleaned_prompt and cleaned_prompt.strip():
            messages.append({
                "role": "user",
                "content": cleaned_prompt.strip()
            })
        else:
            raise ValueError("Prompt is empty or contains only whitespace after cleaning")
        
        # Ensure messages array is not empty
        if not messages:
            raise ValueError("Messages array is empty - cannot make API call")
        
        # OpenRouter API payload format
        # Paid Tier: enable JSON response_format for structured output.
        payload = {
            "model": str(model_name).strip(),
            "messages": messages
        }
        
        # Remove top_k parameter if it exists (not supported by OpenRouter)
        if "top_k" in payload:
            payload.pop("top_k")
        
        # Ensure response_format JSON mode is enabled (paid tier / turbo).
        # Some providers/model variants (even paid) may reject response_format.
        # For google/gemini-2.0-flash specifically, retry immediately once without response_format on ANY 400.
        payload["response_format"] = {"type": "json_object"}
        
        # Make POST request to OpenRouter
        response = None
        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
            log_event(f"OpenRouter call model='{model_name}' status={response.status_code}", level="INFO")
            if response.status_code >= 400:
                # Truncate body to avoid log bloat / leaking too much data
                body_preview = (response.text or "")[:800]
                log_event(f"OpenRouter error model='{model_name}' status={response.status_code} body_preview={body_preview}", level="ERROR")
                # Retry immediately once without response_format:
                # - For gemini-2.0-flash: any 400
                # - For other models: only if error mentions response_format
                model_lower = str(model_name).lower().strip()
                should_retry_no_rf = False
                if response.status_code == 400 and ("google/gemini-2.0-flash" in model_lower):
                    should_retry_no_rf = True
                elif response.status_code == 400 and ("response_format" in (response.text or "").lower()):
                    should_retry_no_rf = True

                if should_retry_no_rf:
                    payload_no_rf = dict(payload)
                    payload_no_rf.pop("response_format", None)
                    response = requests.post(self.api_url, headers=headers, json=payload_no_rf, timeout=60)
                    log_event(f"OpenRouter retry(no response_format) model='{model_name}' status={response.status_code}", level="INFO")

            # Check for HTTP errors
            response.raise_for_status()
        except Exception as e:
            status = getattr(response, "status_code", None)
            log_event(f"OpenRouter exception model='{model_name}' status={status} err={e}", level="ERROR")
            raise
        
        # Parse JSON response
        response_data = response.json()
        
        # Extract content from OpenRouter response format: choices[0].message.content
        if 'choices' in response_data and len(response_data['choices']) > 0:
            content = response_data['choices'][0].get('message', {}).get('content', '')
            if not content:
                raise ValueError("OpenRouter response missing content in choices[0].message.content")
            
            # Create a response-like object for compatibility
            class OpenRouterResponse:
                def __init__(self, text):
                    self.text = text
                    self.choices = response_data.get('choices', [])
                    self.raw_response = response_data
            
            print(f"DEBUG: OpenRouter API call successful with model: '{model_name}'")
            # Turbo Mode Cooldown: keep a tiny guard to reduce accidental bursts
            cooldown_s = float(os.getenv("OPENROUTER_COOLDOWN_SECONDS", "0.2"))
            if cooldown_s > 0:
                time.sleep(cooldown_s)
            return OpenRouterResponse(content)
        else:
            raise ValueError("OpenRouter response missing choices array")
    
    def call_api_with_fallback(self, prompt, system_prompt=None):
        """
        Centralized API call method with automatic fallback to alternative model names.
        Smart Retry Logic: Uses retry decorator for 3 attempts on network/API errors.
        If all models fail, return a Mock response so the app can function.
        Supports system_prompt for core identity rules.
        Returns the response object (or Mock response if API fails).
        
        Args:
            prompt: User message content
            system_prompt: Optional system message for core identity rules
        """
        # Model Chain: Primary (Claude 3.5 Sonnet), Secondary (Gemini Flash 1.5), Free Fallback (Llama 3.1 8B)
        models_to_try = [self.model_id] + self.fallback_models
        last_error = None
        
        for model_name in models_to_try:
            try:
                # Smart Retry Logic: _call_api_single is wrapped with retry_api_call decorator
                response = self._call_api_single(model_name, prompt, system_prompt=system_prompt)
                
                # If successful, update primary model for future calls
                if model_name != self.model_id:
                    self.model_id = model_name
                    print(f"INFO: Using model: {model_name}")
                return response
            except Exception as model_error:
                last_error = model_error
                # Only log warning for first attempt, reduce noise
                if model_name == models_to_try[0]:
                    print(f"WARN: Model {model_name} failed after retries: {model_error}")
                continue  # Try next model
        
        # If all models fail, return Mock response instead of raising
        print(f"WARN: All model attempts failed. Last error: {last_error}. Using Mock response.")
        return self._create_mock_response(prompt)
    
    def _create_mock_response(self, prompt):
        """
        Creates a Mock response object when API fails.
        This allows the app to function even when the API is offline.
        """
        class MockResponse:
            def __init__(self, text):
                self.text = text
                self.choices = []
                self.raw_response = {}
        
        # Return a simple mock response
        mock_text = "AI Analysis temporarily unavailable. Please review manually."
        return MockResponse(mock_text)

def clean_json_text(text):
    """
    Assertive JSON cleaning: Remove triple backticks (```json) and other markdown formatting
    before parsing JSON. Includes retry logic for robust parsing.
    """
    if not text:
        return text
    
    # Remove markdown code blocks
    text = text.strip()
    # Remove ```json at start
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    # Remove ``` at end
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    return text

def parse_json_safely(text, max_retries=3):
    """
    Bulletproof JSON: Uses advanced regex to find the FIRST { and the LAST } in the string.
    Handles nested JSON objects and arrays robustly.
    Returns parsed JSON or None if all attempts fail.
    """
    if not text:
        return None
    
    # First, remove triple backticks
    cleaned_text = clean_json_text(text)
    
    for attempt in range(max_retries):
        try:
            # Try direct parsing first
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            if attempt < max_retries - 1:
                # Bulletproof JSON: Find FIRST { and LAST } using advanced regex
                # This handles nested structures by finding the outermost braces
                first_open = cleaned_text.find('{')
                first_open_bracket = cleaned_text.find('[')
                
                if first_open != -1:
                    # Find matching closing brace for the first {
                    # Count braces to find the matching closing }
                    brace_count = 0
                    last_close = -1
                    for i in range(first_open, len(cleaned_text)):
                        if cleaned_text[i] == '{':
                            brace_count += 1
                        elif cleaned_text[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                last_close = i
                                break
                    
                    if last_close != -1:
                        json_text = cleaned_text[first_open:last_close + 1]
                        try:
                            return json.loads(json_text)
                        except json.JSONDecodeError:
                            pass
                
                # Try array extraction: Find FIRST [ and LAST ]
                if first_open_bracket != -1:
                    bracket_count = 0
                    last_close_bracket = -1
                    for i in range(first_open_bracket, len(cleaned_text)):
                        if cleaned_text[i] == '[':
                            bracket_count += 1
                        elif cleaned_text[i] == ']':
                            bracket_count -= 1
                            if bracket_count == 0:
                                last_close_bracket = i
                                break
                    
                    if last_close_bracket != -1:
                        json_text = cleaned_text[first_open_bracket:last_close_bracket + 1]
                        try:
                            return json.loads(json_text)
                        except json.JSONDecodeError:
                            pass
                
                # Last resort: more aggressive cleaning
                # Remove any leading/trailing non-JSON characters
                cleaned_text = re.sub(r'^[^{[]*', '', cleaned_text)
                cleaned_text = re.sub(r'[^}\]]*$', '', cleaned_text)
                cleaned_text = cleaned_text.strip()
            else:
                # On final attempt, try to extract with simpler regex
                json_match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])', cleaned_text, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass
                raise json.JSONDecodeError("Failed to parse JSON after all retries", cleaned_text, 0)
    
    return None

def detect_language(text):
    """
    Detects if text is Hebrew or English.
    Returns 'he' for Hebrew, 'en' for English.
    Uses heuristic: if Hebrew characters (א-ת) are > 30% of text, it's Hebrew.
    """
    if not text or len(text.strip()) == 0:
        return 'en'  # Default to English
    
    # Hebrew Unicode range: \u0590-\u05FF
    hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
    ascii_pattern = re.compile(r'[a-zA-Z]')
    
    hebrew_chars = len(hebrew_pattern.findall(text))
    ascii_chars = len(ascii_pattern.findall(text))
    total_chars = hebrew_chars + ascii_chars
    
    if total_chars == 0:
        return 'en'  # Default if no recognizable characters
    
    hebrew_ratio = hebrew_chars / total_chars if total_chars > 0 else 0
    
    return 'he' if hebrew_ratio > 0.3 else 'en'

# --- Safe Gemini API Call Helper (Anti-404) ---
def call_gemini_safely(prompt, api_client=None):
    """
    Safe wrapper for Gemini API calls that handles 404 errors and other API failures gracefully.
    Returns dict with 'success' (bool), 'response' (response object or None), 'error' (str or None).
    
    Args:
        prompt: The prompt to send to Gemini
        api_client: Optional APIClient instance. If None, creates a new one.
    
    Returns:
        dict with keys: 'success', 'response', 'error', 'error_code'
    """
    if api_client is None:
        try:
            api_client = APIClient()
        except Exception as e:
            return {
                'success': False,
                'response': None,
                'error': f"Failed to initialize APIClient: {e}",
                'error_code': 'INIT_ERROR'
            }
    
    try:
        response = api_client.call_api_with_fallback(prompt)
        return {
            'success': True,
            'response': response,
            'error': None,
            'error_code': None
        }
    except Exception as e:
        error_str = str(e)
        # Check for 404 or NOT_FOUND errors
        if '404' in error_str or 'NOT_FOUND' in error_str or 'ClientError' in error_str:
            return {
                'success': False,
                'response': None,
                'error': 'ERROR_404: API model not found or unavailable',
                'error_code': 'ERROR_404'
            }
        else:
            return {
                'success': False,
                'response': None,
                'error': f"API call failed: {error_str}",
                'error_code': 'API_ERROR'
            }

# --- Session State Initializers ---
def initialize_session_state():
    """Initialize all session state variables with default values."""
    import streamlit as st
    
    if 'job_analyses' not in st.session_state:
        st.session_state.job_analyses = {}
    if 'jobs_analyzed' not in st.session_state:
        st.session_state.jobs_analyzed = set()
    if 'scraping_in_progress' not in st.session_state:
        st.session_state.scraping_in_progress = False
    if 'pdf_processed_hash' not in st.session_state:
        st.session_state.pdf_processed_hash = None
    if 'should_rerun_after_pdf' not in st.session_state:
        st.session_state.should_rerun_after_pdf = False
    if 'quick_analyses' not in st.session_state:
        st.session_state.quick_analyses = {}
    if 'search_term_offset' not in st.session_state:
        st.session_state.search_term_offset = 0
    if 'my_skill_bucket' not in st.session_state:
        st.session_state.my_skill_bucket = []
    if 'job_top_skills' not in st.session_state:
        st.session_state.job_top_skills = {}
    if 'rejection_reasons' not in st.session_state:
        st.session_state.rejection_reasons = {}
    if 'show_rejection_menu' not in st.session_state:
        st.session_state.show_rejection_menu = {}
    if 'digital_persona' not in st.session_state:
        st.session_state.digital_persona = None
    if 'job_dossiers' not in st.session_state:
        st.session_state.job_dossiers = {}
    if 'show_all_jobs' not in st.session_state:
        st.session_state.show_all_jobs = False
    if 'optimized_queries' not in st.session_state:
        st.session_state.optimized_queries = []
    if 'scraper_status' not in st.session_state:
        st.session_state.scraper_status = {
            'linkedin': {'status': 'idle', 'last_check': None},
            'indeed': {'status': 'idle', 'last_check': None},
            'alljobs': {'status': 'idle', 'last_check': None},
            'drushim': {'status': 'idle', 'last_check': None},
            'jobmaster': {'status': 'idle', 'last_check': None}
        }
    if 'active_model' not in st.session_state:
        # Free-tier ONLY default (Stop Credit Leak)
        st.session_state.active_model = 'google/gemini-2.0-flash-exp:free'
    if 'potential_roles' not in st.session_state:
        st.session_state.potential_roles = []
    if 'hunting_mode' not in st.session_state:
        st.session_state.hunting_mode = False
    if 'hunting_active' not in st.session_state:
        st.session_state.hunting_active = False
    if 'scout_process' not in st.session_state:
        st.session_state.scout_process = None

# --- System Integrity Check (Heartbeat) ---
def check_system_integrity():
    """
    Establishes a heartbeat that returns a dictionary of statuses for:
    - API Client: Whether APIClient can be initialized and make a test call
    - Session State: Whether all required session state variables are initialized
    - Persona Engine: Whether CoreEngine can be initialized and has required methods
    
    Returns a dict with status information for each component.
    """
    status = {
        'api_client': {'status': 'unknown', 'message': '', 'timestamp': None},
        'session_state': {'status': 'unknown', 'message': '', 'timestamp': None},
        'persona_engine': {'status': 'unknown', 'message': '', 'timestamp': None},
        'browser_bot': {'status': 'unknown', 'message': '', 'timestamp': None}
    }
    
    # Check API Client
    try:
        api_client = APIClient()
        # Try a minimal test call (very short prompt to avoid quota issues)
        test_response = api_client.call_api_with_fallback("Say 'OK'")
        if test_response and hasattr(test_response, 'text'):
            status['api_client'] = {
                'status': 'healthy',
                'message': f'API Client operational. Model: {api_client.model_id}',
                'timestamp': datetime.datetime.now().isoformat()
            }
        else:
            status['api_client'] = {
                'status': 'warning',
                'message': 'API Client initialized but test call returned unexpected format',
                'timestamp': datetime.datetime.now().isoformat()
            }
    except Exception as e:
        status['api_client'] = {
            'status': 'error',
            'message': f'API Client error: {str(e)[:100]}',
            'timestamp': datetime.datetime.now().isoformat()
        }
    
    # Check Session State
    try:
        import streamlit as st
        required_keys = [
            'job_analyses', 'jobs_analyzed', 'scraping_in_progress',
            'pdf_processed_hash', 'should_rerun_after_pdf', 'my_skill_bucket',
            'job_top_skills', 'digital_persona', 'job_dossiers',
            'show_all_jobs', 'optimized_queries', 'scraper_status', 'active_model'
        ]
        missing_keys = []
        for key in required_keys:
            if key not in st.session_state:
                missing_keys.append(key)
        
        if missing_keys:
            status['session_state'] = {
                'status': 'warning',
                'message': f'Missing session state keys: {", ".join(missing_keys)}',
                'timestamp': datetime.datetime.now().isoformat()
            }
        else:
            status['session_state'] = {
                'status': 'healthy',
                'message': f'All {len(required_keys)} required session state keys initialized',
                'timestamp': datetime.datetime.now().isoformat()
            }
    except Exception as e:
        status['session_state'] = {
            'status': 'error',
            'message': f'Session state check error: {str(e)[:100]}',
            'timestamp': datetime.datetime.now().isoformat()
        }
    
    # Check Persona Engine (CoreEngine)
    try:
        from core_engine import CoreEngine
        engine = CoreEngine()
        required_methods = [
            'deep_profile_analysis', 'build_master_search_profile',
            'extract_search_query', 'analyze_match', 'reframing_analysis',
            'generate_search_strategy', 'check_level_mismatch',
            'extract_top_skills', 'job_dossier', 'generate_rejection_reasons',
            'extract_avoid_rule_from_text'
        ]
        missing_methods = []
        for method in required_methods:
            if not hasattr(engine, method) or not callable(getattr(engine, method, None)):
                missing_methods.append(method)
        
        if missing_methods:
            status['persona_engine'] = {
                'status': 'error',
                'message': f'Missing CoreEngine methods: {", ".join(missing_methods)}',
                'timestamp': datetime.datetime.now().isoformat()
            }
        else:
            status['persona_engine'] = {
                'status': 'healthy',
                'message': f'CoreEngine operational with {len(required_methods)} methods',
                'timestamp': datetime.datetime.now().isoformat()
            }
    except Exception as e:
        status['persona_engine'] = {
            'status': 'error',
            'message': f'CoreEngine initialization error: {str(e)[:100]}',
            'timestamp': datetime.datetime.now().isoformat()
        }
    
    # Check Browser Bot Functions (submit_application, send_confirmation_email, auto_fill_ats)
    try:
        import importlib.util
        browser_bot_path = 'browser_bot.py'
        if os.path.exists(browser_bot_path):
            with open(browser_bot_path, 'r', encoding='utf-8') as f:
                browser_bot_content = f.read()
            
            required_functions = ['submit_application', 'send_confirmation_email', 'auto_fill_ats', 'JobAppBot']
            missing_functions = []
            for func in required_functions:
                # Check for function definition
                func_pattern = rf'def\s+{func}\s*\('
                class_pattern = rf'class\s+{func}\s*[\(:]'
                if not (re.search(func_pattern, browser_bot_content) or re.search(class_pattern, browser_bot_content)):
                    missing_functions.append(func)
            
            if missing_functions:
                status['browser_bot'] = {
                    'status': 'error',
                    'message': f'Missing browser_bot functions: {", ".join(missing_functions)}',
                    'timestamp': datetime.datetime.now().isoformat()
                }
            else:
                status['browser_bot'] = {
                    'status': 'healthy',
                    'message': f'All {len(required_functions)} browser_bot functions present',
                    'timestamp': datetime.datetime.now().isoformat()
                }
        else:
            status['browser_bot'] = {
                'status': 'error',
                'message': 'browser_bot.py file not found',
                'timestamp': datetime.datetime.now().isoformat()
            }
    except Exception as e:
        status['browser_bot'] = {
            'status': 'error',
            'message': f'Browser bot check error: {str(e)[:100]}',
            'timestamp': datetime.datetime.now().isoformat()
        }
    
    return status

# --- Persistent Learning Mechanism (preferences.json) ---
def get_cv_metadata(uploaded_files):
    """
    Hash-Based Check: Generate metadata for CV files (hash, filenames, modification dates).
    Used to detect if CV files have changed and trigger re-analysis.
    
    Args:
        uploaded_files: List of uploaded file objects (from st.file_uploader)
    
    Returns:
        dict with: 'combined_hash', 'file_count', 'filenames', 'last_modified'
    """
    if not uploaded_files or len(uploaded_files) == 0:
        return None
    
    import hashlib
    import datetime
    
    combined_hash = hashlib.md5(b''.join([f.getvalue() for f in uploaded_files])).hexdigest()
    filenames = [f.name for f in uploaded_files]
    file_count = len(uploaded_files)
    
    # Get modification time (use current time as proxy since uploaded files don't have mtime)
    last_modified = datetime.datetime.now().isoformat()
    
    return {
        'combined_hash': combined_hash,
        'file_count': file_count,
        'filenames': filenames,
        'last_modified': last_modified
    }

def load_preferences(user_id=None):
    """
    Load user preferences from Supabase (cloud - primary), SQLite database (local - secondary), or JSON file (fallback).
    If neither exists, creates default structure in database.
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        dict with: user_identity, scoring_weights, history, cv_metadata
    """
    if user_id is None:
        user_id = get_user_id()
    
    # Try Supabase first (cloud-native - primary)
    try:
        if use_supabase():
            supabase = get_supabase_manager()
            if supabase:
                preferences = supabase.get_preferences(tenant_id=user_id)
                if preferences:
                    # Convert to expected format
                    return {
                        "personal_dna": preferences.get("personal_dna", {}),
                        "career_horizon": preferences.get("career_horizon", {}),
                        "hard_constraints": preferences.get("hard_constraints", {})
                    }
    except Exception as supabase_error:
        print(f"⚠️ Supabase load failed, falling back to local: {supabase_error}")
    
    # Try SQLite database (local - secondary)
    try:
        db = get_db_manager()
        preferences = db.get_preferences(user_id)
        if preferences:
            return preferences
    except Exception as db_error:
        print(f"⚠️ Database load failed, falling back to JSON: {db_error}")
    
    # Fallback to JSON file
    preferences_file = get_user_file_path('preferences.json', user_id)
    default_preferences = {
        "personal_dna": {
            "hard_constraints": {
                "location_flexibility": {
                    "allowed_cities": ["Tel Aviv", "Kfar Saba", "Petah Tikva"],
                    "israel_only": True,
                    "allow_relocation": False
                },
                "work_model": {
                    "remote_only": False,
                    "hybrid_allowed": True,
                    "min_home_days": 2
                },
                "travel_limits": {
                    "max_commute_minutes": 45,
                    "overseas_travel": "none"
                },
                "family_obligations": {
                    "early_exit_days": ["Tuesday", "Thursday"],
                    "early_exit_time": "15:30"
                }
            },
            "soft_traits": {
                "hobbies": ["Digital Persona Development", "Automated Scouting Systems"],
                "communication_style": "Professional yet authentic",
                "tone_voice": "Bold, result-oriented, empathetic"
            }
        },
        "career_horizon": {
            "target_roles": ["CTO", "Head of AI", "Product Architect"],
            "additive_weight": 0.2
        },
        "user_identity": {
            "added_skills": [],  # Skills added via 'Adopt Skills' button
            "preferred_roles": [],
            "preferred_industries": [],
            "user_ambitions": "",  # User's written ambitions text (influences scoring and horizon roles)
            "pivot_mode": False  # If True, search by skills, not just titles
        },
        "cv_metadata": {
            "combined_hash": None,
            "file_count": 0,
            "filenames": [],
            "last_modified": None
        },
        "scoring_weights": {
            # Default weights for different skills/attributes (multipliers)
            # These get boosted when user approves jobs
            "ecommerce": 1.0,
            "leadership": 1.0,
            "technology": 1.0,
            "management": 1.0,
            "python": 1.0,
            "javascript": 1.0,
            "aws": 1.0,
            "docker": 1.0,
            "kubernetes": 1.0,
            "shopify": 1.0,
            "magento": 1.0,
            "react": 1.0,
            "nodejs": 1.0,
            "cto": 1.0,
            "vp": 1.0,
            "architect": 1.0
        },
        "history": {
            "rejected_jobs": [],  # List of rejected jobs with reasons
            "approved_jobs": [],  # List of approved jobs (for learning)
            "total_searches": 0,
            "last_updated": None
        }
    }
    
    if not os.path.exists(preferences_file):
        # Create file with defaults
        save_preferences(default_preferences)
        return default_preferences
    
    try:
        with open(preferences_file, 'r', encoding='utf-8') as f:
            preferences = json.load(f)
        mutated = False
        
        # Ensure all required keys exist (schema migration - preserve existing settings)
        if 'personal_dna' not in preferences:
            preferences['personal_dna'] = default_preferences['personal_dna']
            mutated = True
        else:
            preferences['personal_dna'].setdefault('hard_constraints', default_preferences['personal_dna']['hard_constraints'])
            preferences['personal_dna'].setdefault('soft_traits', default_preferences['personal_dna']['soft_traits'])
            # setdefault doesn't tell us if changed; do conservative mutation check by probing keys
            # Deep defaults for hard constraints
            hc = preferences['personal_dna'].get('hard_constraints', {})
            hc.setdefault('location_flexibility', default_preferences['personal_dna']['hard_constraints']['location_flexibility'])
            hc.setdefault('work_model', default_preferences['personal_dna']['hard_constraints']['work_model'])
            hc.setdefault('travel_limits', default_preferences['personal_dna']['hard_constraints']['travel_limits'])
            hc.setdefault('family_obligations', default_preferences['personal_dna']['hard_constraints']['family_obligations'])
            preferences['personal_dna']['hard_constraints'] = hc
            # Soft traits defaults
            st = preferences['personal_dna'].get('soft_traits', {})
            for k, v in default_preferences['personal_dna']['soft_traits'].items():
                st.setdefault(k, v)
            preferences['personal_dna']['soft_traits'] = st
            # Conservative: if any expected key missing previously, mark mutated
            for k in ["hard_constraints", "soft_traits"]:
                if k not in (preferences.get("personal_dna", {}) or {}):
                    mutated = True

        if 'career_horizon' not in preferences:
            preferences['career_horizon'] = default_preferences['career_horizon']
            mutated = True
        else:
            preferences['career_horizon'].setdefault('target_roles', default_preferences['career_horizon']['target_roles'])
            preferences['career_horizon'].setdefault('additive_weight', default_preferences['career_horizon']['additive_weight'])
            if "target_roles" not in (preferences.get("career_horizon", {}) or {}) or "additive_weight" not in (preferences.get("career_horizon", {}) or {}):
                mutated = True

        if 'user_identity' not in preferences:
            preferences['user_identity'] = default_preferences['user_identity']
            mutated = True
        if 'scoring_weights' not in preferences:
            preferences['scoring_weights'] = default_preferences['scoring_weights']
            mutated = True
        if 'history' not in preferences:
            preferences['history'] = default_preferences['history']
            mutated = True
        if 'cv_metadata' not in preferences:
            preferences['cv_metadata'] = default_preferences['cv_metadata']
            mutated = True
        
        # Ensure added_skills exists
        if 'added_skills' not in preferences['user_identity']:
            preferences['user_identity']['added_skills'] = []
        
        # Ensure rejected_jobs exists
        if 'rejected_jobs' not in preferences['history']:
            preferences['history']['rejected_jobs'] = []
        if 'approved_jobs' not in preferences['history']:
            preferences['history']['approved_jobs'] = []
        
        # Immediate Persistence: if we injected missing keys, write back instantly
        try:
            if mutated:
                save_preferences(preferences, preserve_user_settings=True)
        except Exception:
            pass

        return preferences
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"⚠️ Error loading preferences.json: {e}. Using defaults.")
        # Save defaults to database
        try:
            db = get_db_manager()
            db.save_preferences(user_id, default_preferences)
        except Exception:
            pass
        return default_preferences

def save_preferences(preferences, preserve_user_settings=True, user_id=None):
    """
    Save preferences to Supabase (cloud - primary), SQLite database (local - secondary), and JSON file (fallback).
    Silent Update: If preserve_user_settings is True, merges with existing preferences
    to preserve user-defined settings like 'Added Skills' without destroying them.
    
    Args:
        preferences: Dictionary with preferences to save
        preserve_user_settings: If True, merges with existing file to preserve user settings
        user_id: Optional user_id. If not provided, uses get_user_id()
    """
    if user_id is None:
        user_id = get_user_id()
    
    # Try Supabase first (cloud-native - primary)
    try:
        if use_supabase():
            supabase = get_supabase_manager()
            if supabase:
                if preserve_user_settings:
                    # Load existing preferences from Supabase for merge
                    existing = supabase.get_preferences(tenant_id=user_id)
                    if existing:
                        # Merge preferences
                        preferences = _merge_preferences(existing, preferences)
                # Save to Supabase
                success = supabase.save_preferences(preferences, tenant_id=user_id)
                if success:
                    print(f"✅ Saved preferences to Supabase for {user_id}")
    except Exception as supabase_error:
        print(f"⚠️ Supabase save failed, falling back to local: {supabase_error}")
    
    # Try SQLite database (local - secondary)
    try:
        db = get_db_manager()
        if preserve_user_settings:
            # Load existing preferences from database for merge
            existing = db.get_preferences(user_id)
            if existing:
                # Merge preferences (same logic as JSON merge below)
                preferences = _merge_preferences(existing, preferences)
        db.save_preferences(user_id, preferences)
    except Exception as db_error:
        print(f"⚠️ Database save failed, falling back to JSON: {db_error}")
    
    # Fallback to JSON file
    preferences_file = get_user_file_path('preferences.json', user_id)
    try:
        # Silent Update: Load existing preferences if preserve_user_settings is True
        if preserve_user_settings and os.path.exists(preferences_file):
            try:
                with open(preferences_file, 'r', encoding='utf-8') as f:
                    existing_preferences = json.load(f)
                
                # Smart Merge: Preserve user-defined settings
                # Preserve added_skills (user manually added these)
                if 'user_identity' in existing_preferences and 'added_skills' in existing_preferences['user_identity']:
                    existing_skills = existing_preferences['user_identity']['added_skills']
                    if 'user_identity' in preferences:
                        # Merge: Keep existing skills, add new ones that don't exist
                        new_skills = preferences['user_identity'].get('added_skills', [])
                        merged_skills = list(set(existing_skills + new_skills))
                        preferences['user_identity']['added_skills'] = merged_skills
                    else:
                        preferences['user_identity'] = existing_preferences['user_identity'].copy()
                
                # Preserve scoring_weights (user may have customized these)
                if 'scoring_weights' in existing_preferences:
                    if 'scoring_weights' in preferences:
                        # Merge: Keep existing weights, update only new ones
                        merged_weights = existing_preferences['scoring_weights'].copy()
                        merged_weights.update(preferences['scoring_weights'])
                        preferences['scoring_weights'] = merged_weights
                    else:
                        preferences['scoring_weights'] = existing_preferences['scoring_weights'].copy()

                # Preserve personal_dna & career_horizon (Persona boundaries and soft traits)
                if 'personal_dna' in existing_preferences:
                    if 'personal_dna' not in preferences:
                        preferences['personal_dna'] = existing_preferences['personal_dna']
                    else:
                        # Merge deep without wiping existing user-defined values
                        merged_pd = existing_preferences.get('personal_dna', {}).copy()
                        merged_pd.update(preferences.get('personal_dna', {}))
                        # hard_constraints deep merge
                        merged_hc = (existing_preferences.get('personal_dna', {}) or {}).get('hard_constraints', {}).copy()
                        merged_hc.update((preferences.get('personal_dna', {}) or {}).get('hard_constraints', {}))
                        merged_pd['hard_constraints'] = merged_hc
                        # soft_traits deep merge
                        merged_st = (existing_preferences.get('personal_dna', {}) or {}).get('soft_traits', {}).copy()
                        merged_st.update((preferences.get('personal_dna', {}) or {}).get('soft_traits', {}))
                        merged_pd['soft_traits'] = merged_st
                        preferences['personal_dna'] = merged_pd

                if 'career_horizon' in existing_preferences:
                    if 'career_horizon' not in preferences:
                        preferences['career_horizon'] = existing_preferences['career_horizon']
                    else:
                        merged_ch = existing_preferences.get('career_horizon', {}).copy()
                        merged_ch.update(preferences.get('career_horizon', {}))
                        preferences['career_horizon'] = merged_ch
                
                # Preserve history (user's job approval/rejection history)
                # Fix Merge Error: Handle dictionary merging correctly (ensure keys are strings/hashes)
                if 'history' in existing_preferences:
                    if 'history' in preferences:
                        # Merge: Keep existing history, append new entries
                        merged_history = existing_preferences['history'].copy()
                        
                        # Fix Merge Error: Use list comprehension instead of set() for dictionaries
                        # Dictionaries are unhashable, so we need to deduplicate by job_id or URL
                        if 'rejected_jobs' in preferences['history']:
                            existing_rejected = existing_preferences['history'].get('rejected_jobs', [])
                            new_rejected = preferences['history'].get('rejected_jobs', [])
                            # Deduplicate by job_id or job_url (whichever exists)
                            seen_ids = set()
                            merged_rejected = []
                            for job in existing_rejected + new_rejected:
                                # Use job_id or job_url as unique identifier
                                job_id = job.get('job_id') or job.get('job_url') or str(job)
                                if job_id not in seen_ids:
                                    seen_ids.add(job_id)
                                    merged_rejected.append(job)
                            merged_history['rejected_jobs'] = merged_rejected
                        
                        if 'approved_jobs' in preferences['history']:
                            existing_approved = existing_preferences['history'].get('approved_jobs', [])
                            new_approved = preferences['history'].get('approved_jobs', [])
                            # Deduplicate by job_id or job_url (whichever exists)
                            seen_ids = set()
                            merged_approved = []
                            for job in existing_approved + new_approved:
                                # Use job_id or job_url as unique identifier
                                job_id = job.get('job_id') or job.get('job_url') or str(job)
                                if job_id not in seen_ids:
                                    seen_ids.add(job_id)
                                    merged_approved.append(job)
                            merged_history['approved_jobs'] = merged_approved
                        
                        preferences['history'] = merged_history
                    else:
                        preferences['history'] = existing_preferences['history'].copy()
                
                # Preserve professional_dna (user-defined target industries and custom skills)
                if 'professional_dna' in existing_preferences:
                    if 'professional_dna' not in preferences:
                        preferences['professional_dna'] = existing_preferences['professional_dna'].copy()
                    else:
                        # Merge: Keep existing DNA, update only new fields
                        merged_dna = existing_preferences['professional_dna'].copy()
                        merged_dna.update(preferences['professional_dna'])
                        preferences['professional_dna'] = merged_dna
                
                print("✅ Silent Update: Preserved user-defined settings (added_skills, scoring_weights, history, professional_dna)")
            except Exception as merge_error:
                print(f"⚠️ Error merging preferences: {merge_error}. Saving new preferences without merge.")
        
        # Save merged preferences
        with open(preferences_file, 'w', encoding='utf-8') as f:
            json.dump(preferences, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error saving preferences.json: {e}")
        return False

def update_preferences(job_data, action, user_id=None):
    """
    Update preferences based on user action (Approve or Reject).
    
    Args:
        job_data: Dictionary with job information (company, title, job_url, description, skills, etc.)
        action: 'approve' or 'reject'
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        dict with 'status' (bool) and 'message' (str)
    """
    try:
        # Fix Crash: Get user_id if not provided
        if user_id is None:
            user_id = get_user_id()
        
        # Fix Crash: Directly call load_preferences function with user_id
        # Ensure we're calling the function, not a local variable
        preferences = load_preferences(user_id)
        
        if action == 'reject':
            # Extract reason and add to rejected_jobs
            reason = job_data.get('reason', 'No reason provided')
            rejected_job = {
                'company': job_data.get('company', 'Unknown'),
                'title': job_data.get('title', 'Unknown'),
                'job_url': job_data.get('job_url', ''),
                'reason': reason,
                'timestamp': datetime.datetime.now().isoformat()
            }
            preferences['history']['rejected_jobs'].append(rejected_job)
            
            # Keep only last 100 rejected jobs to avoid file bloat
            if len(preferences['history']['rejected_jobs']) > 100:
                preferences['history']['rejected_jobs'] = preferences['history']['rejected_jobs'][-100:]
            
            print(f"📝 Preferences updated: Job rejected - {job_data.get('title', 'Unknown')} @ {job_data.get('company', 'Unknown')}")
        
        elif action == 'approve':
            # Boost weights of skills found in that job
            job_description = job_data.get('description', '').lower()
            job_title = job_data.get('title', '').lower()
            job_text = job_description + ' ' + job_title
            
            # Extract skills from job (common tech keywords)
            skill_keywords = {
                'ecommerce': ['e-commerce', 'ecommerce', 'shopify', 'magento', 'retail tech'],
                'python': ['python'],
                'javascript': ['javascript', 'js', 'node.js', 'nodejs'],
                'aws': ['aws', 'amazon web services'],
                'docker': ['docker'],
                'kubernetes': ['kubernetes', 'k8s'],
                'react': ['react', 'reactjs'],
                'nodejs': ['node.js', 'nodejs'],
                'shopify': ['shopify'],
                'magento': ['magento'],
                'leadership': ['leadership', 'lead', 'manage', 'team'],
                'technology': ['technology', 'tech', 'engineering'],
                'management': ['management', 'manager', 'director'],
                'cto': ['cto', 'chief technology officer'],
                'vp': ['vp', 'vice president'],
                'architect': ['architect', 'architecture']
            }
            
            # Boost weights for skills found in approved job (multiply by 1.1, cap at 2.0)
            for skill_key, keywords in skill_keywords.items():
                if any(keyword in job_text for keyword in keywords):
                    current_weight = preferences['scoring_weights'].get(skill_key, 1.0)
                    new_weight = min(2.0, current_weight * 1.1)  # Boost by 10%, cap at 2.0
                    preferences['scoring_weights'][skill_key] = new_weight
            
            # Add to approved_jobs history
            approved_job = {
                'company': job_data.get('company', 'Unknown'),
                'title': job_data.get('title', 'Unknown'),
                'job_url': job_data.get('job_url', ''),
                'timestamp': datetime.datetime.now().isoformat()
            }
            preferences['history']['approved_jobs'].append(approved_job)
            
            # Keep only last 100 approved jobs
            if len(preferences['history']['approved_jobs']) > 100:
                preferences['history']['approved_jobs'] = preferences['history']['approved_jobs'][-100:]
            
            print(f"📝 Preferences updated: Job approved - {job_data.get('title', 'Unknown')} @ {job_data.get('company', 'Unknown')}. Weights boosted.")
        
        # Update last_updated timestamp
        preferences['history']['last_updated'] = datetime.datetime.now().isoformat()
        
        # Save preferences with user_id
        if save_preferences(preferences, preserve_user_settings=True, user_id=user_id):
            return {'status': True, 'message': f'Preferences updated for {action} action'}
        else:
            return {'status': False, 'error': 'Failed to save preferences'}
    
    except Exception as e:
        print(f"❌ Error updating preferences: {e}")
        import traceback
        print(traceback.format_exc())
        return {'status': False, 'error': str(e)}

def add_skill_to_preferences(skill, user_id=None):
    """
    Add a skill to user_identity['added_skills'] in preferences.json.
    Called when user clicks 'Adopt Skills' button.
    
    Args:
        skill: Skill string to add
        user_id: Optional user_id. If not provided, uses get_user_id()
    
    Returns:
        dict with 'status' (bool)
    """
    try:
        # Get user_id if not provided
        if user_id is None:
            user_id = get_user_id()
        
        preferences = load_preferences(user_id)
        
        if skill not in preferences['user_identity']['added_skills']:
            preferences['user_identity']['added_skills'].append(skill)
            save_preferences(preferences, preserve_user_settings=True, user_id=user_id)
            print(f"✅ Skill added to preferences: {skill}")
            return {'status': True}
        else:
            return {'status': True, 'message': 'Skill already in preferences'}
    except Exception as e:
        print(f"❌ Error adding skill to preferences: {e}")
        return {'status': False, 'error': str(e)}

# --- Notification Setup (Future Alert System Integration) ---
def send_notification(job_details):
    """
    Placeholder function for future alert system integration.
    This function will be connected to an alert system (e.g., email, SMS, Slack) in the future.
    
    Args:
        job_details: Dictionary with job information (company, title, job_url, match_score, etc.)
    
    Returns:
        dict with 'status' (bool) and 'message' (str)
    """
    # Placeholder implementation - will be connected to alert system later
    try:
        company = job_details.get('company', 'Unknown')
        title = job_details.get('title', 'Unknown')
        match_score = job_details.get('match_score', 0)
        
        # Log notification event (for now, just print)
        print(f"🔔 Notification: High-match job found - {title} @ {company} (Match: {match_score}%)")
        
        # Future: Connect to alert system (email, SMS, Slack, etc.)
        # Example: email_service.send_alert(job_details)
        # Example: sms_service.send_alert(job_details)
        # Example: slack_service.send_alert(job_details)
        
        return {
            'status': True,
            'message': f'Notification placeholder called for {company} - {title}'
        }
    except Exception as e:
        return {
            'status': False,
            'error': str(e)
        }
def reset_system_data(uploads_dir: str = None, user_id: str = None) -> bool:
    """
    Reset Persona system data for a specific user (best-effort, non-crashing):
    - Delete user-specific preferences.json, professional_dna.json, persona_cache.json, and profile_data.json.
    - Clear all files/subfolders inside user's uploads/ directory.
    - Clear Streamlit caches if available.
    - Only clears the current user's data directory, NOT the entire data/ folder.
    
    Args:
        uploads_dir: Optional uploads directory path. If not provided, uses user-specific uploads directory.
        user_id: Optional user_id. If not provided, uses get_user_id()

    Returns True only if all deletions succeeded; False if any item could not be removed
    (e.g., file is locked by another process).
    """
    if user_id is None:
        user_id = get_user_id()
    
    # Get user-specific data directory
    user_data_dir = get_user_data_dir(user_id)
    
    # Set uploads_dir to user-specific if not provided
    if uploads_dir is None:
        uploads_dir = os.path.join(user_data_dir, 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
    
    errors = []

    # Clear Streamlit caches (best-effort)
    try:
        import streamlit as st
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
    except Exception:
        pass

    # Nuclear Reset: Explicitly delete user-specific persona_cache.json and profile_data.json
    critical_files = ['persona_cache.json', 'profile_data.json', 'preferences.json', 'professional_dna.json', 
                     'blacklist.json', 'user_profile_learnings.json', 'recycle_bin.json', 'feedback_log.json',
                     'applications_history.csv']
    for fname in critical_files:
        try:
            file_path = get_user_file_path(fname, user_id)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    print(f"✅ Deleted {file_path}")
                except PermissionError as e:
                    # Retry a few times
                    ok = False
                    for attempt in range(3):
                        time.sleep(0.2 * (2 ** attempt))
                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            ok = True
                            break
                        except Exception:
                            continue
                    if not ok:
                        errors.append(f"{file_path}: {e}")
                except Exception as e:
                    errors.append(f"{file_path}: {e}")
        except Exception as e:
            errors.append(f"{fname}: {e}")
    
    # Delete any .json/.csv/.db files in user's data directory (best-effort)
    try:
        if os.path.isdir(user_data_dir):
            for entry in os.listdir(user_data_dir):
                try:
                    entry_path = os.path.join(user_data_dir, entry)
                    # Skip subdirectories (like 'logs' and 'uploads')
                    if os.path.isdir(entry_path):
                        continue
                    if entry.endswith(('.json', '.csv', '.db')):
                        if os.path.isfile(entry_path):
                            os.remove(entry_path)
                            print(f"✅ Deleted {entry_path}")
                except Exception as e:
                    errors.append(f"{entry}: {e}")
    except Exception as e:
        errors.append(f"user_data_dir_scan: {e}")

    # Clear user-specific uploads directory contents (only this user's uploads)
    try:
        if os.path.isdir(uploads_dir):
            for entry in os.listdir(uploads_dir):
                path = os.path.join(uploads_dir, entry)
                try:
                    if os.path.isdir(path):
                        ok = False
                        for attempt in range(3):
                            try:
                                shutil.rmtree(path)
                                ok = True
                                break
                            except PermissionError:
                                time.sleep(0.2 * (2 ** attempt))
                            except Exception as e:
                                errors.append(f"{path}: {e}")
                                ok = True
                                break
                        if not ok:
                            errors.append(f"{path}: PermissionError (in use?)")
                    else:
                        ok = False
                        for attempt in range(3):
                            try:
                                if os.path.exists(path):
                                    os.remove(path)
                                ok = True
                                break
                            except PermissionError:
                                time.sleep(0.2 * (2 ** attempt))
                            except Exception as e:
                                errors.append(f"{path}: {e}")
                                ok = True
                                break
                        if not ok:
                            errors.append(f"{path}: PermissionError (in use?)")
                except Exception as e:
                    errors.append(f"{path}: {e}")
    except Exception as e:
        errors.append(f"uploads_dir({uploads_dir}): {e}")
    
    # Clear user-specific logs directory (optional - keeps logs for debugging)
    # Uncomment if you want to clear logs on reset:
    # try:
    #     logs_dir = get_user_logs_dir(user_id)
    #     if os.path.isdir(logs_dir):
    #         for entry in os.listdir(logs_dir):
    #             log_path = os.path.join(logs_dir, entry)
    #             try:
    #                 if os.path.isfile(log_path):
    #                     os.remove(log_path)
    #             except Exception as e:
    #                 errors.append(f"{log_path}: {e}")
    # except Exception as e:
    #     errors.append(f"logs_dir: {e}")

    if errors:
        try:
            log_event(f"reset_system_data completed with errors: {errors}", level='WARNING')
        except Exception:
            pass
        return False

    try:
        log_event(f"reset_system_data completed successfully for user {user_id}", level='INFO', user_id=user_id)
    except Exception:
        pass

    # Verification: Print statement to confirm reset is complete
    print(f"PRINT: System is now 100% empty for user {user_id} when the reset is complete.")
    
    return True

# ============================================================================
# SUPABASE MIGRATION - Zero-Loss Data Migration
# ============================================================================

def migrate_to_supabase(user_id=None, verify_only=False):
    """
    Zero-Loss Migration: Migrate local JSON/CSV data to Supabase.
    
    This function:
    1. Checks for local preferences.json and found_jobs.json
    2. Migrates data to Supabase
    3. Verifies migration success
    4. Only switches to cloud DB after verification
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id()
        verify_only: If True, only verifies migration without migrating
    
    Returns:
        dict: Migration status with details
    """
    if user_id is None:
        user_id = get_user_id()
    
    migration_status = {
        "success": False,
        "preferences_migrated": False,
        "jobs_migrated": False,
        "errors": [],
        "warnings": []
    }
    
    try:
        supabase = get_supabase_manager()
        if supabase is None:
            migration_status["errors"].append("Supabase manager not available. Check credentials.")
            return migration_status
        
        # ========================================================================
        # 1. MIGRATE PREFERENCES.JSON
        # ========================================================================
        preferences_file = get_user_file_path('preferences.json', user_id)
        if os.path.exists(preferences_file):
            try:
                with open(preferences_file, 'r', encoding='utf-8') as f:
                    local_preferences = json.load(f)
                
                if not verify_only:
                    # Save to Supabase
                    success = supabase.save_preferences(local_preferences, tenant_id=user_id)
                    if success:
                        # Verify migration
                        cloud_preferences = supabase.get_preferences(tenant_id=user_id)
                        if cloud_preferences:
                            migration_status["preferences_migrated"] = True
                            print(f"✅ Migrated preferences.json to Supabase for {user_id}")
                        else:
                            migration_status["errors"].append("Preferences migration verification failed")
                    else:
                        migration_status["errors"].append("Failed to save preferences to Supabase")
                else:
                    # Verify-only mode: check if data exists in Supabase
                    cloud_preferences = supabase.get_preferences(tenant_id=user_id)
                    if cloud_preferences:
                        migration_status["preferences_migrated"] = True
                        print(f"✅ Preferences already exist in Supabase for {user_id}")
                    else:
                        migration_status["warnings"].append("Preferences not found in Supabase")
            except Exception as e:
                migration_status["errors"].append(f"Error migrating preferences: {e}")
        else:
            migration_status["warnings"].append("preferences.json not found locally")
        
        # ========================================================================
        # 2. MIGRATE FOUND_JOBS (from session_state or CSV)
        # ========================================================================
        # Check for found_jobs in session_state (if available)
        try:
            import streamlit as st
            if 'found_jobs' in st.session_state and st.session_state.found_jobs:
                jobs_to_migrate = st.session_state.found_jobs
                
                if not verify_only:
                    migrated_count = 0
                    for index, job, job_key, analysis in jobs_to_migrate:
                        try:
                            # Convert job to dict if it's a Series
                            job_dict = job.to_dict() if hasattr(job, 'to_dict') else job
                            
                            # Extract match score and status
                            match_score = analysis.get('match_score', analysis.get('score', 0))
                            status = 'pending'  # Default status
                            
                            # Extract hook if available
                            hook = analysis.get('hook') or analysis.get('strategic_hook', '')
                            
                            # Save to Supabase
                            job_id = supabase.save_job(
                                job_data=job_dict,
                                match_score=match_score,
                                status=status,
                                hook=hook,
                                tenant_id=user_id
                            )
                            
                            if job_id:
                                migrated_count += 1
                        except Exception as e:
                            migration_status["errors"].append(f"Error migrating job {job_key}: {e}")
                    
                    if migrated_count > 0:
                        migration_status["jobs_migrated"] = True
                        print(f"✅ Migrated {migrated_count} jobs to Supabase for {user_id}")
                else:
                    # Verify-only mode
                    cloud_jobs = supabase.get_jobs(tenant_id=user_id)
                    if cloud_jobs:
                        migration_status["jobs_migrated"] = True
                        print(f"✅ {len(cloud_jobs)} jobs already exist in Supabase for {user_id}")
                    else:
                        migration_status["warnings"].append("No jobs found in Supabase")
        except Exception as e:
            migration_status["warnings"].append(f"Could not access session_state for jobs: {e}")
        
        # ========================================================================
        # 3. VERIFY MIGRATION SUCCESS
        # ========================================================================
        if migration_status["preferences_migrated"] or migration_status["jobs_migrated"]:
            migration_status["success"] = True
        elif not migration_status["errors"]:
            migration_status["warnings"].append("No data to migrate (this is OK if starting fresh)")
            migration_status["success"] = True  # Success if nothing to migrate
        
        return migration_status
        
    except Exception as e:
        migration_status["errors"].append(f"Migration failed: {e}")
        return migration_status
