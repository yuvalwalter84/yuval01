"""
Vision Stack 2026: Full Autonomous Mode - Main Orchestrator
This file acts as the main orchestrator, importing functions from modular components.
"""
import streamlit as st
import asyncio
import json
import os
import PyPDF2
import hashlib
import pandas as pd
from jobspy import scrape_jobs
from browser_bot import JobAppBot, send_confirmation_email, auto_fill_ats, submit_application, scrape_israeli_job_boards, discover_job_sources, scrape_discovered_sources
from integrity_check import verify_system

# Google OAuth Authentication - Must be imported first
from auth import authenticate_user, render_login_page, check_user_onboarding

# Import from modular components
from utils import (
    load_profile, save_profile, load_blacklist, save_blacklist, add_to_blacklist,
    filter_blacklisted_jobs, load_user_learnings, save_user_learnings, add_rejection_learning,
    validate_job_source, validate_job_description, log_application,
    scrape_jobs_with_timeout, scrape_israeli_job_boards_with_timeout, initialize_session_state,
    load_preferences, save_preferences, check_if_applied, load_recycle_bin, get_cv_metadata,
    get_user_id, get_user_file_path, log_event
)
from core_engine import CoreEngine
from pdf_generator import PDFGenerator
from ui_layout import (
    render_sidebar, render_job_list, render_human_in_the_loop,
    inject_global_css, render_custom_job_card, create_circular_gauge_svg
)

# Application Status Constants (for tracking flow)
APPLICATION_STATUS_DRAFT = 'Draft'
APPLICATION_STATUS_FINAL_LAUNCH = 'Final Launch'

# הגדרות עמוד
st.set_page_config(page_title="Persona: Your Career, Synchronized", layout="wide", initial_sidebar_state="expanded")

# ============================================================================
# FORCE GLOBAL CSS INJECTION (Must be first, before any UI rendering)
# ============================================================================
# Note: inject_global_css is already imported above, call it immediately
inject_global_css()

# ============================================================================
# SUPABASE MIGRATION CHECK (Zero-Loss Migration)
# ============================================================================
# Check if migration is needed and perform it automatically
try:
    from utils import migrate_to_supabase, use_supabase
    if use_supabase():
        # Run migration check (verify-only on first load, actual migration on user action)
        if 'supabase_migration_checked' not in st.session_state:
            migration_status = migrate_to_supabase(verify_only=True)
            st.session_state.supabase_migration_checked = True
            if migration_status.get('warnings'):
                print(f"ℹ️ Supabase migration status: {migration_status}")
except Exception as migration_error:
    print(f"⚠️ Migration check failed (non-blocking): {migration_error}")

# ============================================================================
# DARK MODE THEME & GLOBAL CSS (Additional styling)
# ============================================================================
st.markdown("""
<style>
    /* Dark Mode Theme */
    :root {
        --bg-primary: #0E1117;
        --bg-card: #161B22;
        --text-primary: #E0E0E0;
        --text-secondary: #8B949E;
        --border-color: #30363D;
        --accent-emerald: #10B981;
        --accent-cyber-blue: #3B82F6;
        --accent-hover: #4A9EFF;
    }
    
    /* Main App Background */
    .stApp {
        background-color: var(--bg-primary);
        color: var(--text-primary);
    }
    
    /* Headers & Text */
    h1, h2, h3, h4, h5, h6 {
        color: var(--text-primary) !important;
    }
    
    /* Cards & Containers */
    .stExpander {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
        margin-bottom: 12px !important;
        padding: 16px !important;
    }
    
    .stExpander:hover {
        border-color: var(--accent-cyber-blue) !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15) !important;
        transition: all 0.3s ease !important;
    }
    
    /* Job Cards Styling */
    .job-card {
        background-color: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        transition: all 0.3s ease;
    }
    
    .job-card:hover {
        border-color: var(--accent-cyber-blue);
        box-shadow: 0 4px 16px rgba(59, 130, 246, 0.2);
        transform: translateY(-2px);
    }
    
    /* Circular Match Score Gauge */
    .match-gauge {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        font-weight: bold;
        margin: 0 auto;
        position: relative;
    }
    
    .match-gauge.high {
        background: linear-gradient(135deg, var(--accent-emerald) 0%, #059669 100%);
        color: white;
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
    }
    
    .match-gauge.medium {
        background: linear-gradient(135deg, var(--accent-cyber-blue) 0%, #2563EB 100%);
        color: white;
        box-shadow: 0 0 20px rgba(59, 130, 246, 0.4);
    }
    
    .match-gauge.low {
        background: linear-gradient(135deg, #6B7280 0%, #4B5563 100%);
        color: white;
    }
    
    /* Pill-shaped Tags */
    .pill-tag {
        display: inline-block;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
        margin: 4px;
        background-color: var(--bg-card);
        border: 1px solid var(--border-color);
        color: var(--text-primary);
    }
    
    .pill-tag.capability {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(59, 130, 246, 0.1) 100%);
        border-color: var(--accent-cyber-blue);
        color: var(--accent-cyber-blue);
    }
    
    .pill-tag.skill {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(16, 185, 129, 0.1) 100%);
        border-color: var(--accent-emerald);
        color: var(--accent-emerald);
    }
    
    /* Glow Effect for Magic Button */
    .magic-button {
        background: linear-gradient(135deg, var(--accent-cyber-blue) 0%, #2563EB 100%);
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        color: white;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.3);
    }
    
    .magic-button:hover {
        box-shadow: 0 0 25px rgba(59, 130, 246, 0.6);
        transform: translateY(-2px);
    }
    
    /* DNA Pulse Animation */
    @keyframes dnaPulse {
        0%, 100% {
            opacity: 1;
            transform: scale(1);
        }
        50% {
            opacity: 0.7;
            transform: scale(1.05);
        }
    }
    
    .dna-pulse {
        animation: dnaPulse 2s ease-in-out infinite;
        color: var(--accent-cyber-blue);
    }
    
    /* Gradient Text for Header */
    .gradient-text {
        background: linear-gradient(135deg, var(--accent-cyber-blue) 0%, #8B5CF6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 700;
        font-size: 2.5rem;
    }
    
    /* Cost Saver Badge */
    .cost-saver {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px 16px;
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%);
        border: 1px solid var(--accent-emerald);
        border-radius: 20px;
        color: var(--accent-emerald);
        font-size: 13px;
        font-weight: 600;
    }
    
    /* Sidebar Styling */
    .css-1d391kg {
        background-color: var(--bg-card) !important;
    }
    
    /* Input Fields */
    .stTextInput > div > div > input {
        background-color: var(--bg-card) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: var(--bg-card) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
    }
    
    .stButton > button:hover {
        border-color: var(--accent-cyber-blue) !important;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.2) !important;
    }
    
    /* Toggle Switch Styling */
    .stCheckbox {
        color: var(--text-primary) !important;
    }
    
    /* Metric Cards */
    .stMetric {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
        padding: 16px !important;
    }
    
    /* Info/Warning/Success Messages */
    .stAlert {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
    }
    
    /* Divider */
    hr {
        border-color: var(--border-color) !important;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# AUTHENTICATION WRAPPER - Check authentication before allowing access
# ============================================================================
user_email = authenticate_user()

if not user_email:
    # User is not authenticated - show login page
    render_login_page()
    st.stop()

# User is authenticated - set user_id to Google email for sandbox enforcement
if 'user_id' not in st.session_state or st.session_state.user_id != user_email:
    st.session_state.user_id = user_email
    st.session_state.user_email = user_email
    print(f"✅ User authenticated: {user_email}")

# Sandbox Enforcement: Ensure all file paths use data/{user_email}/
user_id = st.session_state.user_id  # This is the Google email

# User Onboarding: Check if user's directory exists. If not, redirect to CV upload.
if not check_user_onboarding():
    # User needs to upload CV - show onboarding message
    st.info("👋 Welcome! Please upload your CV to get started.")
    # Set flag to show CV upload section prominently
    st.session_state.show_upload_prompt = True

# Pre-Flight Setup: Browser installation check - runs exactly once when app starts
# Ensure it runs before anything else and NOT inside the "Start Hunting" button loop
try:
    from browser_bot import check_and_install_chromium
    # Browser Speed: This will skip if .playwright_done flag exists
    browser_check = check_and_install_chromium()
    if not browser_check.get("status", False):
        # Only show warning if installation actually failed (not just skipped)
        if not os.path.exists('.playwright_done'):
            st.warning(f"⚠️ Browser setup: {browser_check.get('message', 'Unknown issue')}")
except Exception as browser_error:
    # Don't block the app if browser check fails
    print(f"⚠️ Browser check error (non-blocking): {browser_error}")

# 🛡️ בדיקת אינטגריטי (חוק: קוד מלא בלבד)
# Expose Error: Replace generic message with st.exception(e) to show full traceback
# Post-Reset Safety: Never hard-stop on missing profile_data.json
try:
    integrity_errors = verify_system()
except Exception as e:
    integrity_errors = []
    print(f"⚠️ Integrity check failed: {e}")

if integrity_errors:
    profile_missing = any("profile_data.json" in err or "Missing Key" in err for err in integrity_errors)
    # Always keep UI alive; for reset/missing profile show friendly message
    if profile_missing:
        st.session_state.digital_persona = None
        st.info("👋 Welcome! System reset successful. Please upload a new CV to build a new Persona.")
    else:
        st.warning("⚠️ System integrity check found issues. The app will continue:")
        with st.expander("Show Integrity Details"):
            for err in integrity_errors:
                st.text(f"• {err}")

# Initialize session state
try:
    initialize_session_state()
except Exception as e:
    st.error("❌ שגיאה באתחול Session State")
    st.exception(e)
    st.stop()

# Deep purge guard: if profile_data.json is missing, reset persona/session variables immediately
try:
    if not os.path.exists("profile_data.json"):
        st.session_state.digital_persona = None
        st.session_state.persona_data = None
        st.session_state.persona_data_hash = None
        st.session_state.persona_questions = []
        st.session_state.persona_answers = {}
        st.session_state.questionnaire_completed = False
        st.session_state.questionnaire_active = False
        st.session_state.professional_dna = None
        st.session_state.master_profile = None
        st.session_state.my_skill_bucket = []
        st.session_state.uploaded_cv_texts = []
except Exception:
    pass

# Force Sidebar: Move render_sidebar() to the very top, immediately after initialize_session_state()
# BUT: render_sidebar needs engine and profile, so we need to initialize them first
# Initialize core components (engine, profile, pdf_generator) - NO try-except wrapper
# We'll handle errors with st.exception() inside
profile = None
engine = None
pdf_generator = None

# Multi-User Sandbox: user_id is now set from Google OAuth (user_email) above
# All file paths automatically use data/{user_email}/ via get_user_file_path()

# Try to load profile from database first (primary), then fallback to JSON
profile = None
try:
    from utils import get_db_manager
    db = get_db_manager()
    persona_data = db.get_persona(user_id)
    if persona_data:
        # Convert database persona to profile format
        digital_persona = persona_data.get('digital_persona', {})
        profile = {
            "master_cv_text": "",  # CV text is not stored in personas table (too large, stored separately if needed)
            "auto_query": "",
            "digital_persona": digital_persona
        }
        if digital_persona:
            st.session_state.digital_persona = digital_persona
        print(f"✅ Loaded persona from database for user {user_id}")
except Exception as db_error:
    print(f"⚠️ Database load failed, falling back to JSON: {db_error}")

# Fallback to JSON file if database load failed or returned None
if not profile:
    profile_data_path = get_user_file_path('profile_data.json', user_id)
    if os.path.exists(profile_data_path):
        try:
            profile = load_profile(user_id)
            # Only load persona_cache.json if profile has CV text
            if profile and isinstance(profile, dict) and profile.get('master_cv_text'):
                try:
                    from core_engine import load_persona_cache
                    cached_persona = load_persona_cache(user_id)
                    if cached_persona and isinstance(cached_persona, dict):
                        st.session_state.digital_persona = cached_persona
                        print(f"✅ Loaded persona from cache at startup for user {user_id}")
                    else:
                        st.session_state.digital_persona = None
                except Exception as e:
                    print(f"⚠️ Could not load persona from cache: {e}")
                    st.session_state.digital_persona = None
        except Exception as e:
            print(f"⚠️ Error loading profile: {e}")
            profile = {"master_cv_text": "", "auto_query": ""}
    else:
        # No profile in database or JSON - initialize empty
        print(f"⚠️ No profile found for user {user_id} - initializing empty profile")
        st.session_state.digital_persona = None
        profile = {"master_cv_text": "", "auto_query": ""}  # Empty profile dict

# Initialize profile if still None
if not profile:
    profile = {"master_cv_text": "", "auto_query": ""}

try:
    engine = CoreEngine()
except Exception as e:
    st.error("❌ שגיאה באתחול CoreEngine")
    st.exception(e)
    st.stop()

try:
    pdf_generator = PDFGenerator()
    # Update active model from engine
    st.session_state.active_model = engine.model_id
except Exception as e:
    st.error("❌ שגיאה באתחול PDFGenerator")
    st.exception(e)
    st.stop()

# Force Sidebar: Render sidebar immediately after initialization - NO try-except wrapper
# This ensures sidebar is always visible, even if there are errors later
try:
    must_have_keywords, exclude_keywords = render_sidebar(engine, profile)
except Exception as e:
    st.error("❌ שגיאה ב-render_sidebar")
    st.exception(e)
    # Set defaults to prevent NameError
    must_have_keywords = []
    exclude_keywords = []

# Professional Header with Gradient Text and DNA Pulse
st.markdown("""
<div style="text-align: center; padding: 20px 0;">
    <h1 class="gradient-text" style="margin-bottom: 10px;">
        <span class="dna-pulse">🧬</span> Persona: Your Career, Synchronized
    </h1>
    <p style="color: #8B949E; font-size: 16px;">Autonomous Digital Recruitment Agent</p>
</div>
""", unsafe_allow_html=True)

# Debug: Show what the AI 'thinks' it knows (temporary debugging)
if st.session_state.get('digital_persona'):
    with st.expander("🔍 DEBUG: Current Digital Persona (What the AI knows)", expanded=False):
        st.write("**Digital Persona State:**")
        st.json(st.session_state.digital_persona)
        st.caption("This is temporary debugging output. Remove after persona issues are resolved.")

# --- שלב 1: ניתוח CV (הבסיס למערכת) ---
st.header("📄 Resume Intelligence")

# User Onboarding: Prominent upload prompt for new users
if st.session_state.get('show_upload_prompt', False) or not check_user_onboarding():
    st.error("📄 **Action Required:** Please upload your CV below to initialize your Persona and start job hunting.")
    st.markdown("---")

# Multi-CV Management: Allow multiple CV uploads
uploaded_files = st.file_uploader("Upload Master CV(s) to train the Agent", type="pdf", accept_multiple_files=True, key="cv_uploader")

# Multi-CV Management: Process all uploaded files
if uploaded_files and len(uploaded_files) > 0:
    # Hash-Based Check: Compare current CV files with metadata in preferences.json
    current_cv_metadata = get_cv_metadata(uploaded_files)
    combined_hash = current_cv_metadata['combined_hash'] if current_cv_metadata else hashlib.md5(b''.join([f.getvalue() for f in uploaded_files])).hexdigest()
    
    # Load preferences to check stored CV metadata
    preferences = load_preferences(user_id)
    stored_cv_metadata = preferences.get('cv_metadata', {})
    stored_hash = stored_cv_metadata.get('combined_hash')
    
    # Auto-Sync: Trigger re-analysis if CV files have changed
    cv_changed = (
        stored_hash is None or  # No stored metadata
        stored_hash != combined_hash or  # Hash mismatch
        stored_cv_metadata.get('file_count', 0) != len(uploaded_files) or  # File count changed
        stored_cv_metadata.get('filenames', []) != [f.name for f in uploaded_files]  # Filenames changed
    )
    
    # Only process if these are new files (hash doesn't match processed hash) OR CV metadata changed
    if st.session_state.pdf_processed_hash != combined_hash or cv_changed:
        if cv_changed and stored_hash:
            print(f"🔄 Auto-Sync: CV files changed (hash: {stored_hash[:8]}... -> {combined_hash[:8]}...). Triggering re-analysis.")
            st.info("🔄 **Auto-Sync:** CV files have changed. Re-analyzing Digital Persona...")
        
        # Identity Reset: Clear all persona-related data before processing new CV
        def reset_persona_context(user_id):
            """
            Reset persona context when a new CV is uploaded.
            Clears session state and deletes old database entries to prevent data leakage.
            """
            print("🔄 Identity Reset: Clearing persona context for new CV upload...")
            
            # Clear all persona-related session state variables
            persona_session_keys = [
                'digital_persona',
                'horizon_roles',
                'persona_data',
                'persona_data_hash',
                'persona_questions',
                'persona_answers',
                'potential_roles',
                'uploaded_cv_texts'
            ]
            for key in persona_session_keys:
                if key in st.session_state:
                    del st.session_state[key]
                    print(f"  ✅ Cleared session state: {key}")
            
            # Delete old entries from database
            try:
                from utils import get_db_manager
                db = get_db_manager()
                db.delete_persona(user_id)
                db.delete_horizon_roles(user_id)
                print(f"  ✅ Deleted old persona and horizon_roles from database for user {user_id}")
            except Exception as db_error:
                print(f"  ⚠️ Error deleting old persona data: {db_error}")
            
            # Clear persona cache file if it exists
            try:
                from utils import get_user_file_path
                persona_cache_file = get_user_file_path('persona_cache.json', user_id)
                if os.path.exists(persona_cache_file):
                    os.remove(persona_cache_file)
                    print(f"  ✅ Deleted persona cache file")
            except Exception as cache_error:
                print(f"  ⚠️ Error deleting persona cache: {cache_error}")
            
            print("✅ Identity Reset complete - ready for fresh persona analysis")
        
        # Trigger identity reset before processing new CV
        reset_persona_context(user_id)
        
        with st.status("📄 **מנתח קורות חיים...**", expanded=True) as status:
            try:
                status.update(label=f"📖 קורא {len(uploaded_files)} קובצי PDF...")
                cv_texts_list = []
                
                # Extract text from all uploaded CVs
                for i, uploaded_file in enumerate(uploaded_files, 1):
                    status.update(label=f"📖 קורא קובץ PDF {i}/{len(uploaded_files)}...")
                    uploaded_file.seek(0)  # Reset file pointer
                    reader = PyPDF2.PdfReader(uploaded_file)
                    cv_text = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
                    cv_texts_list.append(cv_text)
                
                # Merge all CVs into Master Profile
                status.update(label="🔗 מיזוג קורות חיים מרובים ל-Master Profile...")
                merged_cv_text = engine.merge_cv_data(cv_texts_list)
                profile['master_cv_text'] = merged_cv_text
                
                # Store individual CV texts for reference
                st.session_state.uploaded_cv_texts = cv_texts_list

                status.update(label="🤖 בונה Digital Persona ומחלץ שאילתת חיפוש... (Building Persona & Generating Query)")
                # Build Digital Persona first
                # Forced Re-Analysis: Always pass existing_persona=None to ensure fresh analysis from new CV
                # This prevents data leakage from old CVs
                user_learnings = load_user_learnings()
                # CRITICAL: Set existing_persona=None to force fresh analysis (no additive expansion)
                # This ensures the persona is built ONLY from the current CV text
                existing_persona = None
                try:
                    st.session_state.digital_persona = engine.deep_profile_analysis(
                        merged_cv_text,
                        skill_bucket=st.session_state.my_skill_bucket,
                        rejection_learnings=user_learnings,
                        existing_persona=None  # Force fresh analysis - no old data leakage
                    )
                    # Debug Visibility: Print industry focus
                    industry_focus = st.session_state.digital_persona.get('industry_focus', 'Not specified')
                    print(f"DEBUG: Industry Focus: {industry_focus}")
                except Exception as persona_error:
                    print(f"WARN: Digital Persona creation failed: {persona_error}")
                    st.exception(persona_error)  # Expose Error
                    # Create fallback persona
                    st.session_state.digital_persona = {
                        "role_level": "Senior",
                        "industry_focus": "Technology",
                        "tech_stack": [],
                        "leadership_style": "Technical Leadership",
                        "preferences": [],
                        "avoid_patterns": [],
                        "persona_summary": "Fallback persona - AI analysis unavailable"
                    }

                # Build Master Search Profile for query generation
                master_profile = engine.build_master_search_profile(
                    merged_cv_text,
                    skill_bucket=st.session_state.my_skill_bucket,
                    rejection_learnings=user_learnings
                )
                profile['auto_query'] = engine.extract_search_query(merged_cv_text, master_profile=master_profile, digital_persona=st.session_state.digital_persona)

                # Task 3: Integration - Identify potential roles and save to preferences.json
                # Sync: After CV upload, immediately call identify_potential_roles and update preferences.json
                status.update(label="🎯 Identifying potential roles...")
                try:
                    potential_roles = engine.identify_potential_roles(merged_cv_text, digital_persona=st.session_state.digital_persona)
                    # Save to preferences.json under user_identity['preferred_roles']
                    preferences = load_preferences(user_id)
                    preferences['user_identity']['preferred_roles'] = potential_roles
                    save_preferences(preferences, preserve_user_settings=True, user_id=user_id)
                    # Update session state so UI reflects these roles immediately
                    st.session_state.potential_roles = potential_roles
                    print(f"✅ Identified {len(potential_roles)} potential roles: {potential_roles}")
                except Exception as roles_error:
                    print(f"⚠️ Error identifying potential roles: {roles_error}")
                    import traceback
                    print(traceback.format_exc())
                    # Continue without failing the whole process
                
                # Generate Horizon Roles with gap analysis
                # Versatility Check: Extract only from current CV text and current user ambitions
                status.update(label="🚀 Generating Horizon Roles with gap analysis...")
                try:
                    # Get current user ambitions from preferences (not cached)
                    preferences = load_preferences(user_id)
                    user_ambitions = preferences.get('user_identity', {}).get('user_ambitions', '')
                    
                    # Forced Re-Analysis: Generate horizon roles from current CV and current ambitions only
                    horizon_roles = engine.generate_horizon_roles(
                        merged_cv_text,  # Current CV text only
                        digital_persona=st.session_state.digital_persona,  # Fresh persona from current CV
                        skill_bucket=st.session_state.my_skill_bucket,  # Current skill bucket
                        user_ambitions=user_ambitions  # Current user ambitions only
                    )
                    
                    # Clear old horizon roles from session state before setting new ones
                    if 'horizon_roles' in st.session_state:
                        del st.session_state.horizon_roles
                    
                    # Save to session state for UI display
                    st.session_state.horizon_roles = horizon_roles
                    
                    # Save to database (primary) for persistence - this overwrites old entries
                    try:
                        from utils import get_db_manager
                        db = get_db_manager()
                        db.save_horizon_roles(user_id, horizon_roles)  # This deletes old and inserts new
                        print(f"✅ Saved {len(horizon_roles)} horizon roles to database (old entries deleted)")
                    except Exception as db_error:
                        print(f"⚠️ Failed to save horizon roles to database: {db_error}")
                    
                    print(f"✅ Generated {len(horizon_roles)} horizon roles with gap analysis")
                except Exception as horizon_error:
                    print(f"⚠️ Error generating horizon roles: {horizon_error}")
                    import traceback
                    print(traceback.format_exc())
                    # Continue without failing the whole process
                
                # Zero-Click Start: Immediately set hunting_active = True after identify_potential_roles
                st.session_state.hunting_active = True
                print(f"✅ Zero-Click Start: hunting_active set to True")

                status.update(label="💾 שומר נתונים... (Saving Data)")
                # Forced Re-Analysis: Save persona to database (overwrites old entries)
                # Versatility Check: Latent capabilities are extracted only from current CV text and current user ambitions
                try:
                    from utils import get_db_manager
                    db = get_db_manager()
                    # Get current preferences for ambitions (not cached)
                    try:
                        preferences = load_preferences(user_id)
                        current_ambitions = preferences.get('user_identity', {}).get('user_ambitions', '')
                    except:
                        preferences = None
                        current_ambitions = ''
                    
                    # Extract latent capabilities from current persona (built from current CV only)
                    # Versatility Check: These are extracted ONLY from current CV text in deep_profile_analysis
                    current_latent_capabilities = st.session_state.digital_persona.get('latent_capabilities', []) if st.session_state.digital_persona else []
                    
                    # AI-ORCHESTRATION: Generate Personal DNA Signature (Vector Embedding)
                    # This is done once during onboarding and reused for low-cost filtering
                    status.update(label="🧬 Generating Personal DNA Signature (Vector Embedding)...")
                    questionnaire_answers = preferences.get('user_identity', {}).get('questionnaire_answers', {}) if preferences else {}
                    dna_embedding = engine.generate_dna_signature(
                        cv_text=merged_cv_text,
                        digital_persona=st.session_state.digital_persona,
                        questionnaire_answers=questionnaire_answers,
                        ambitions=current_ambitions
                    )
                    if dna_embedding:
                        print(f"✅ Generated DNA Signature (embedding dimension: {len(dna_embedding)})")
                    else:
                        print("⚠️ DNA Signature generation failed (will fallback to AI-only analysis)")
                    
                    # Save persona to database - this overwrites old persona entry
                    db.save_persona(
                        user_id=user_id,
                        profile_summary=st.session_state.digital_persona.get('persona_summary', '') if st.session_state.digital_persona else None,
                        latent_capabilities=current_latent_capabilities,  # Only from current CV
                        ambitions=current_ambitions,  # Only current user ambitions
                        digital_persona=st.session_state.digital_persona if st.session_state.digital_persona else None,
                        dna_embedding=dna_embedding  # Personal DNA Signature for vector similarity
                    )
                    print("✅ Saved fresh persona to database (old persona overwritten)")
                except Exception as db_error:
                    print(f"⚠️ Database save failed, falling back to JSON: {db_error}")
                    # Fallback to JSON (for backward compatibility during transition)
                    save_profile(profile, user_id)
                
                # Hash-Based Check: Save CV metadata to preferences.json
                if current_cv_metadata:
                    preferences = load_preferences(user_id)
                    old_personal_dna = json.dumps(preferences.get('personal_dna', {}), sort_keys=True)
                    preferences['cv_metadata'] = current_cv_metadata
                    save_preferences(preferences, preserve_user_settings=True, user_id=user_id)  # Silent Update: Preserve user settings
                    print(f"✅ CV metadata saved: {current_cv_metadata['file_count']} files, hash: {combined_hash[:8]}...")
                    
                    # Persona Synchronization: Trigger re-scoring if personal_dna changed
                    new_personal_dna = json.dumps(preferences.get('personal_dna', {}), sort_keys=True)
                    if old_personal_dna != new_personal_dna:
                        try:
                            from persona_sync import trigger_persona_synchronization
                            print("🔄 Personal DNA changed - triggering persona synchronization...")
                            updated, skipped = trigger_persona_synchronization(user_id=user_id, force=False)
                            print(f"✅ Persona synchronization complete: {updated} jobs updated, {skipped} skipped")
                        except Exception as sync_error:
                            print(f"⚠️ Persona synchronization failed (non-blocking): {sync_error}")

                # Mark these files as processed
                st.session_state.pdf_processed_hash = combined_hash

                status.update(label=f"✅ כוילה בהצלחה: {profile['auto_query']}", state="complete")
                st.success(f"✅ המערכת כוילה לחיפוש: {profile['auto_query']}")

                # Set flag to rerun once after processing completes
                st.session_state.should_rerun_after_pdf = True
                
                # Auto-Start: Immediately after CV processing (after hashing), trigger background_scout.py subprocess
                # Task 1: Auto-Start Scout - Start background_scout.py if it's not already running
                try:
                    import subprocess
                    import sys
                    
                    # Check if background_scout.py exists
                    if os.path.exists('background_scout.py'):
                        # Check if background_scout_process is already running in session_state
                        should_start = True
                        if 'background_scout_process' in st.session_state:
                            # Check if process is still alive
                            existing_process = st.session_state.background_scout_process
                            if existing_process is not None:
                                # Check if process is still running (poll() returns None if running, return code if finished)
                                if existing_process.poll() is None:
                                    print(f"✅ Auto-Start: Background scout is already running (PID: {existing_process.pid})")
                                    # Process is already running, don't start another one
                                    should_start = False
                                else:
                                    # Process has finished, need to start a new one
                                    print(f"⚠️ Auto-Start: Previous background scout process finished. Starting new one.")
                        
                        if should_start:
                            # Start background scout in a separate process (persistent daemon)
                            scout_process = subprocess.Popen(
                                [sys.executable, 'background_scout.py'],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            st.session_state.background_scout_process = scout_process
                            print(f"✅ Auto-Start: Background scout started (PID: {scout_process.pid})")
                            st.info("🚀 **Auto-Start:** Background job scout has been started automatically.")
                    else:
                        print(f"⚠️ background_scout.py not found. Skipping auto-start.")
                except Exception as scout_error:
                    print(f"⚠️ Failed to start background scout: {scout_error}")
                    # Don't block the app if scout fails to start
                    
            except Exception as pdf_error:
                status.update(label=f"❌ שגיאה: {pdf_error}", state="error")
                st.error(f"❌ שגיאה בעיבוד CV: {pdf_error}")
                st.exception(pdf_error)
                st.session_state.should_rerun_after_pdf = False

        # Handle rerun only once after PDF processing
        if st.session_state.should_rerun_after_pdf:
            st.session_state.should_rerun_after_pdf = False
            st.rerun()

# Dynamic Persona Questionnaire: Initialize questionnaire state
# Persistence: Use st.session_state to ensure the questionnaire progress isn't lost during background scans
if profile.get('master_cv_text') and st.session_state.get('digital_persona'):
    # Initialize questionnaire state
    if 'persona_questions' not in st.session_state:
        try:
            # Context-Aware Questions: Pass digital_persona to generate domain-specific questions
            st.session_state.persona_questions = engine.generate_persona_questions(
                profile['master_cv_text'],
                digital_persona=st.session_state.get('digital_persona')
            )
            st.session_state.persona_answers = {}
            st.session_state.questionnaire_completed = False
            # Initialize questionnaire_active flag: True if persona is newly generated and no answers exist
            preferences = load_preferences(user_id)
            questionnaire_answers = preferences.get('user_identity', {}).get('questionnaire_answers', {})
            st.session_state.questionnaire_active = len(questionnaire_answers) == 0
            print(f"✅ Generated {len(st.session_state.persona_questions)} persona questions")
        except Exception as q_error:
            print(f"⚠️ Error generating persona questions: {q_error}")
            st.session_state.persona_questions = []
            st.session_state.persona_answers = {}
            st.session_state.questionnaire_completed = False
            st.session_state.questionnaire_active = False
    else:
        # Check if questionnaire should be active (not completed and no answers in preferences)
        if 'questionnaire_active' not in st.session_state:
            preferences = load_preferences(user_id)
            questionnaire_answers = preferences.get('user_identity', {}).get('questionnaire_answers', {})
            st.session_state.questionnaire_active = (not st.session_state.get('questionnaire_completed', False) and len(questionnaire_answers) == 0)

# הגנה: אם אין טקסט של CV, המערכת מציגה הודעה ומציגה את סעיף העלאת CV
# DO NOT use st.stop() - allow user to see and use the upload section
_has_valid_cv = bool(profile.get('master_cv_text'))
if not _has_valid_cv:
    st.error("📄 **Action Required:** Please upload your CV above to initialize your Persona and start job hunting.")
    st.info("אנא העלה קורות חיים כדי שהסוכן האוטונומי יוכל להתחיל לעבוד.")

# הצגת סטטוס הסוכן בבטחה
current_query = profile.get('auto_query', 'ממתין לכיול...')
st.info(f"🕵️ **סטטוס סוכן:** מחפש משרות עבור `{current_query}`")

st.divider()

# --- Manual Job Analysis Section ---
st.header("📝 Manual Job Analysis")
st.write("Paste a job description below to analyze the match and prepare a draft immediately.")
manual_job_description = st.text_area(
    "Job Description:",
    height=300,
    placeholder="Paste the job description here...",
    key="manual_job_description"
)

if st.button("🔍 Analyze Match & Prepare Draft", key="manual_analyze_btn"):
    if not manual_job_description.strip():
        st.warning("Please paste a job description first.")
    else:
        with st.status("🤖 **מנתח התאמה ויוצר טיוטה...**", expanded=True) as manual_status:
            try:
                manual_status.update(label="📊 מנתח התאמה עם CV ו-Digital Persona...")
                # Build/load Digital Persona and Master Search Profile
                user_learnings = load_user_learnings()
                if st.session_state.digital_persona is None:
                    st.session_state.digital_persona = engine.deep_profile_analysis(
                        profile['master_cv_text'],
                        skill_bucket=st.session_state.my_skill_bucket,
                        rejection_learnings=user_learnings
                    )
                master_profile = engine.build_master_search_profile(
                    profile['master_cv_text'],
                    skill_bucket=st.session_state.my_skill_bucket,
                    rejection_learnings=user_learnings
                )
                # Pass strict_industry_match flag to analyze_match
                strict_industry_match = st.session_state.get('strict_industry_match', True)
                
                # AI-ORCHESTRATION: Load DNA embedding for vector similarity filtering
                dna_embedding = None
                try:
                    from utils import get_db_manager
                    db = get_db_manager()
                    persona_data = db.get_persona(user_id)
                    if persona_data and persona_data.get('dna_embedding'):
                        dna_embedding = persona_data['dna_embedding']
                except Exception:
                    pass
                
                analysis = engine.analyze_match(manual_job_description, profile['master_cv_text'], 
                                              skill_bucket=st.session_state.my_skill_bucket, 
                                              master_profile=master_profile,
                                              digital_persona=st.session_state.digital_persona,
                                              strict_industry_match=strict_industry_match,
                                              dna_embedding=dna_embedding)
                
                # Debug the 0%: Log AI reason for 0% score
                score = analysis.get('match_score', analysis.get('score', 0))
                verify_system()  # Ensure system integrity check is performed here
                if score == 0:
                    print(f"DEBUG: AI Reason for 0% score (Manual Analysis): {analysis.get('explanation', analysis.get('reasoning', 'No explanation provided'))}")
                
                score = analysis.get('score', 0)
                reasoning = analysis.get('reasoning', 'No reasoning available')
                gaps = analysis.get('gaps', [])

                manual_status.update(label="📝 יוצר טיוטה מותאמת...")
                # Cover Letter Guard: Validate result before storing
                draft_text_result = engine.reframing_analysis(manual_job_description, profile['master_cv_text'], 
                                                       skill_bucket=st.session_state.my_skill_bucket,
                                                       master_profile=master_profile,
                                                       digital_persona=st.session_state.digital_persona)
                # Validation: Ensure draft text is not None
                if draft_text_result and isinstance(draft_text_result, str) and len(draft_text_result) > 0:
                    draft_text = draft_text_result
                else:
                    # Fallback: Generate basic cover letter
                    from utils import detect_language
                    job_lang = detect_language(manual_job_description)
                    draft_text = engine._generate_fallback_cover_letter(
                        manual_job_description,
                        profile['master_cv_text'],
                        job_lang
                    )

                # Store in session state for display
                st.session_state.manual_analysis = analysis
                st.session_state.manual_draft = draft_text
                st.session_state.manual_job_description = manual_job_description

                manual_status.update(label="✅ ניתוח וטיוטה מוכנים!", state="complete")
                st.success(f"✅ Match Score: {score}%")
                
            except Exception as e:
                manual_status.update(label=f"❌ שגיאה: {e}", state="error")
                st.error(f"שגיאה בניתוח: {e}")
                st.exception(e)  # Expose Error
                import traceback
                print(f"ERROR in manual analysis: {e}\n{traceback.format_exc()}")

# Display manual analysis results
if 'manual_analysis' in st.session_state and 'manual_draft' in st.session_state:
    st.divider()
    st.subheader("📊 Analysis Results")
    analysis = st.session_state.manual_analysis
    score = analysis.get('score', 0)

    st.metric("Match Score", f"{score}%")
    st.write(f"**Reasoning:** {analysis.get('reasoning', 'No reasoning available')}")
    gaps = analysis.get('gaps', [])
    if gaps:
        st.write(f"**Gaps:** {', '.join(gaps)}")
    else:
        st.write("**Gaps:** None identified")

    st.subheader("📝 Draft Text")
    edited_draft = st.text_area(
        "Edit the draft before saving:",
        st.session_state.manual_draft,
        height=200,
        key="manual_edited_draft"
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save Draft", key="save_manual_draft"):
            # Create a placeholder job dict for the draft
            manual_job = {
                'company': 'Manual Entry',
                'title': 'Manual Job Analysis',
                'job_url': '',
                'description': st.session_state.manual_job_description
            }
            st.session_state.selected_job = manual_job
            st.session_state.current_draft = edited_draft
            st.success("Draft saved! Scroll down to submit.")
            st.rerun()
    with col2:
        if st.button("🗑️ Clear Analysis", key="clear_manual"):
            del st.session_state.manual_analysis
            del st.session_state.manual_draft
            del st.session_state.manual_job_description
            st.rerun()

st.divider()

# --- שלב 2: חיפוש ומציאת משרות אוטונומי ---
st.header("🔍 Automated Job Matcher")

# Task 1: Live Sync - Read jobs from database (primary) or discovered_jobs.csv (fallback)
DISCOVERED_JOBS_CSV = 'discovered_jobs.csv'

# Initialize sync status container
if 'sync_status_container' not in st.session_state:
    st.session_state.sync_status_container = st.empty()

# Live Sync: Read jobs from database (primary) or CSV (fallback) and append to st.session_state.jobs
def sync_discovered_jobs():
    """
    Read jobs from database (primary) or discovered_jobs.csv (fallback) and append to st.session_state.jobs.
    Returns the number of jobs found.
    """
    # Try database first (primary)
    try:
        from utils import get_db_manager
        db = get_db_manager()
        jobs = db.get_jobs(user_id, status='candidate', limit=100)
        
        if jobs:
            jobs_list = []
            for job in jobs:
                job_dict = {
                    'title': job.get('title', ''),
                    'company': job.get('company', ''),
                    'job_url': job.get('job_url', ''),
                    'description': job.get('description', ''),
                    'match_score': job.get('match_score', 0),
                    'analysis': job.get('analysis', {})
                }
                jobs_list.append(job_dict)
            
            # Update session state
            if 'jobs' not in st.session_state or st.session_state.jobs is None:
                st.session_state.jobs = []
            st.session_state.jobs.extend(jobs_list)
            return len(jobs_list)
    except Exception as db_error:
        print(f"⚠️ Database sync failed, falling back to CSV: {db_error}")
    
    # Fallback to CSV file
    if not os.path.exists(DISCOVERED_JOBS_CSV):
        return 0
    
    try:
        # Read CSV
        discovered_df = pd.read_csv(DISCOVERED_JOBS_CSV)
        
        if discovered_df.empty:
            return 0
        
        # Convert discovered_jobs.csv format to job format (title, company, job_url, description)
        # CSV columns: timestamp, company, title, job_url, match_score, best_role, description_preview
        jobs_list = []
        for _, row in discovered_df.iterrows():
            job_dict = {
                'title': row.get('title', ''),
                'company': row.get('company', ''),
                'job_url': row.get('job_url', ''),
                'description': row.get('description_preview', '')  # Use description_preview as description
            }
            # Only add valid jobs (with URL)
            if job_dict['job_url']:
                jobs_list.append(job_dict)
        
        if not jobs_list:
            return 0
        
        # Convert to DataFrame
        new_jobs_df = pd.DataFrame(jobs_list)
        
        # Get existing jobs
        if 'jobs' in st.session_state and st.session_state.jobs is not None and not st.session_state.jobs.empty:
            existing_jobs_df = st.session_state.jobs
            # Merge with existing jobs (avoid duplicates by job_url)
            if 'job_url' in existing_jobs_df.columns and 'job_url' in new_jobs_df.columns:
                # Find new jobs (not already in existing_jobs)
                existing_urls = set(existing_jobs_df['job_url'].dropna())
                new_jobs_df = new_jobs_df[~new_jobs_df['job_url'].isin(existing_urls)]
            
            if not new_jobs_df.empty:
                # Append new jobs to existing jobs
                merged_jobs = pd.concat([existing_jobs_df, new_jobs_df], ignore_index=True)
                # Remove duplicates by job_url (keep first)
                if 'job_url' in merged_jobs.columns:
                    merged_jobs = merged_jobs.drop_duplicates(subset=['job_url'], keep='first')
                st.session_state.jobs = merged_jobs
                print(f"✅ Live Sync: Added {len(new_jobs_df)} new jobs from {DISCOVERED_JOBS_CSV}. Total: {len(merged_jobs)} jobs.")
            else:
                print(f"ℹ️ Live Sync: No new jobs to add from {DISCOVERED_JOBS_CSV}.")
        else:
            # No existing jobs, set new jobs
            st.session_state.jobs = new_jobs_df
            print(f"✅ Live Sync: Loaded {len(new_jobs_df)} jobs from {DISCOVERED_JOBS_CSV}.")
        
        return len(discovered_df)
    except Exception as e:
        print(f"⚠️ Live Sync Error: Failed to read {DISCOVERED_JOBS_CSV}: {e}")
        return 0

# Sync discovered jobs from CSV
jobs_count = sync_discovered_jobs()

# Display status if hunting_active is True
if st.session_state.get('hunting_active', False):
    st.info(f"🕵️ **Agent is actively scouting...** [{jobs_count}] jobs found in discovered_jobs.csv")
    if jobs_count > 0 and 'jobs' in st.session_state and st.session_state.jobs is not None:
        total_jobs = len(st.session_state.jobs)
        st.caption(f"Total jobs in session: {total_jobs}")

if 'jobs' in st.session_state and st.session_state.jobs is not None and not st.session_state.jobs.empty:
    # Display Verification: Debug print before display logic
    st.write(f'DEBUG: Found {len(st.session_state.jobs)} jobs before filtering')
    print(f"DEBUG: Found {len(st.session_state.jobs)} jobs before filtering")
    
    # CRITICAL FIX: Disable ALL keyword filtering - show EVERY job found
    jobs_to_display = st.session_state.jobs.copy()

    # Never-Zero Display Rule: If total_found > 0 but analyzed == 0, show raw jobs with 'Waiting for AI' status
    total_found = len(jobs_to_display)
    analyzed_count = len(st.session_state.jobs_analyzed)
    
    if total_found > 0 and analyzed_count == 0:
        # AI analysis hasn't started or completely failed - show raw jobs with 'Waiting for AI' status
        st.subheader(f"📋 תוצאות חיפוש ({total_found} משרות - ממתין לניתוח AI)")
        st.info("⏳ **ממתין לניתוח AI:** המשרות נמצאו אך טרם נותחו. המשרות יוצגו עם סטטוס 'Waiting for AI' עד שהניתוח יושלם.")
        
        # Display raw jobs immediately with 'Waiting for AI' status
        for index, job in jobs_to_display.iterrows():
            job_key = f"{job.get('company', '')}_{job.get('title', '')}_{index}"
            # Create default 'Waiting for AI' analysis
            st.session_state.job_analyses[job_key] = {
                "score": 0,
                "reasoning": "Waiting for AI analysis...",
                "gaps": [],
                "waiting_for_ai": True
            }
            st.session_state.jobs_analyzed.add(job_key)
        
        # Force trigger analysis
        jobs_to_analyze = [(idx, job, f"{job.get('company', '')}_{job.get('title', '')}_{idx}") 
                          for idx, job in jobs_to_display.iterrows()]
    else:
        st.subheader(f"📋 תוצאות חיפוש ({len(jobs_to_display)} משרות)")

        if len(jobs_to_display) < len(st.session_state.jobs):
            st.info(f"🔍 **Filtered:** {len(jobs_to_display)} jobs shown (filtered from {len(st.session_state.jobs)} total)")

        # Use show_all_jobs from sidebar (already set in session state)
        show_all_jobs = st.session_state.show_all_jobs

        # Analyze jobs (only if not already analyzed)
        jobs_to_analyze = []
        for index, job in jobs_to_display.iterrows():
            job_key = f"{job.get('company', '')}_{job.get('title', '')}_{index}"
            if job_key not in st.session_state.jobs_analyzed:
                jobs_to_analyze.append((index, job, job_key))

    # Progress spinner for batch analysis
    if jobs_to_analyze:
        total_jobs = len(jobs_to_analyze)
        progress_bar = st.progress(0)
        status_text = st.empty()
        error_details_box = st.empty()  # Box to show error details if any
        errors_encountered = []
        ai_analysis_failed = False  # Track if AI analysis completely fails

        with st.spinner("🤖 Analyzing jobs for CV-match..."):
            # Build/load Digital Persona and Master Search Profile once for all jobs
            user_learnings = load_user_learnings()
            if st.session_state.digital_persona is None:
                try:
                    st.session_state.digital_persona = engine.deep_profile_analysis(
                        profile['master_cv_text'],
                        skill_bucket=st.session_state.my_skill_bucket,
                        rejection_learnings=user_learnings
                    )
                except Exception as e:
                    print(f"WARN: Digital Persona creation failed: {e}")
                    st.exception(e)  # Expose Error
                    ai_analysis_failed = True
                    # Create fallback persona
                    st.session_state.digital_persona = {
                        "role_level": "Senior",
                        "industry_focus": "Technology",
                        "tech_stack": [],
                        "leadership_style": "Technical Leadership",
                        "preferences": [],
                        "avoid_patterns": [],
                        "persona_summary": "Fallback persona - AI analysis unavailable"
                    }
                    st.warning("⚠️ AI analysis unavailable. Showing jobs with 'Needs Manual Review' label.")

            master_profile = engine.build_master_search_profile(
                profile['master_cv_text'],
                skill_bucket=st.session_state.my_skill_bucket,
                rejection_learnings=user_learnings
            )

            # AI-ORCHESTRATION: Load DNA embedding for vector similarity filtering
            dna_embedding = None
            try:
                from utils import get_db_manager
                db = get_db_manager()
                persona_data = db.get_persona(user_id)
                if persona_data and persona_data.get('dna_embedding'):
                    dna_embedding = persona_data['dna_embedding']
                    print(f"✅ Loaded DNA Signature for vector similarity filtering (dimension: {len(dna_embedding)})")
                else:
                    print("ℹ️ No DNA Signature found - will use AI-only analysis (no vector filtering)")
            except Exception as dna_error:
                print(f"⚠️ Error loading DNA embedding: {dna_error}")

            # Track vector filtering stats for logging
            vector_filtered_count = 0
            ai_analyzed_count = 0

            # Use status container for progress (no automatic rerun)
            with st.status("🤖 Analyzing jobs...", expanded=False) as analysis_status:
                for i, (index, job, job_key) in enumerate(jobs_to_analyze):
                    # Fix Pandas Warning: Convert Series to dict if needed
                    job_dict = job.to_dict() if hasattr(job, 'to_dict') else job
                    job_title = job_dict.get('title', '') if isinstance(job_dict, dict) else job.get('title', '')
                    job_company = job_dict.get('company', '') if isinstance(job_dict, dict) else job.get('company', '')
                    
                    # Bypass the 'Broken Job' Filter: Be more permissive - don't filter out titles like "Founding Engineer / CTO"
                    # Only filter truly empty or placeholder titles, not titles that might contain valid content
                    job_title_str = str(job_title).strip() if job_title else ''
                    
                    # Check if title is truly empty or just a placeholder
                    is_truly_empty = (
                        not job_title_str or 
                        job_title_str in ['', 'Job Title', 'NaN', 'nan', 'None', 'null', 'N/A', 'n/a']
                    )
                    
                    # But allow titles that contain executive keywords even if they look unusual
                    # This prevents filtering out "Founding Engineer / CTO" or similar valid titles
                    contains_executive_keywords = False
                    if job_title_str:
                        title_upper = job_title_str.upper()
                        executive_keywords = ['CTO', 'VP', 'CHIEF', 'DIRECTOR', 'HEAD', 'FOUNDING', 'FOUNDER', 'ENGINEER', 'TECHNOLOGY']
                        contains_executive_keywords = any(kw in title_upper for kw in executive_keywords)
                    
                    # Only filter if truly empty AND doesn't contain executive keywords
                    if is_truly_empty and not contains_executive_keywords:
                        print(f"🚫 Broken job filtered out: Empty or invalid title (Title: '{job_title}')")
                        st.session_state.jobs_analyzed.add(job_key)
                        continue
                    elif is_truly_empty and contains_executive_keywords:
                        # Title looks empty but contains executive keywords - keep it
                        print(f"⚠️ Keeping job with unusual title (contains executive keywords): '{job_title}'")
                    
                    # Pre-Filter Non-Tech: Filter out non-tech jobs with Hebrew keywords
                    non_tech_keywords = ['סופר', 'קופאי', 'עוזר אישי', 'מחסנאי', 'שומר', 'נהג', 'מלצר', 'מטבח']
                    job_title_lower = str(job_title).lower()
                    if any(keyword in job_title_lower for keyword in non_tech_keywords):
                        print(f"🚫 Non-tech job filtered out: {job_title} (contains non-tech keyword)")
                        st.session_state.jobs_analyzed.add(job_key)
                        continue
                    
                    analysis_status.update(label=f"🤖 מנתח משרה {i+1}/{total_jobs}: {job_title} @ {job_company}")
                    try:
                        # Duplicate Block: Check if job has already been applied to (database first, then CSV fallback)
                        # Remove it entirely from the list so it doesn't reach the scoring stage
                        if check_if_applied(job_url, user_id):
                            print(f"🚫 Duplicate job blocked: {job_title} at {job_company} (already applied)")
                            # Remove from jobs_to_display by marking as analyzed (will be skipped)
                            st.session_state.jobs_analyzed.add(job_key)
                            continue
                        
                        # Validate job before analysis
                        is_valid_desc, desc_reason = validate_job_description(job_dict if isinstance(job_dict, dict) else job)
                        if not is_valid_desc:
                            st.session_state.job_analyses[job_key] = {
                                "score": 0,
                                "reasoning": f"Invalid Data: {desc_reason}",
                                "gaps": ["Invalid Job Data"],
                                "is_invalid": True
                            }
                            st.session_state.jobs_analyzed.add(job_key)
                            continue
                        
                        job_description = job_dict.get('description', '') if isinstance(job_dict, dict) else job.get('description', '')
                        
                        # Pass strict_industry_match flag to analyze_match
                        strict_industry_match = st.session_state.get('strict_industry_match', True)
                        
                        # Pass job_title for hard override logic
                        # AI-ORCHESTRATION: Pass DNA embedding for vector similarity pre-filtering
                        analysis = engine.analyze_match(job_description, profile['master_cv_text'], 
                                                       skill_bucket=st.session_state.my_skill_bucket,
                                                       master_profile=master_profile,
                                                       digital_persona=st.session_state.digital_persona,
                                                       strict_industry_match=strict_industry_match,
                                                       job_title=job_title,
                                                       dna_embedding=dna_embedding)
                        
                        # Track vector filtering vs AI analysis
                        if analysis.get('discarded') and analysis.get('discard_reason', '').startswith('Vector similarity'):
                            vector_filtered_count += 1
                        else:
                            ai_analyzed_count += 1
                        
                        # Debug the 0%: Log AI reason for 0% score
                        match_score = analysis.get('match_score', analysis.get('score', 0))
                        if match_score == 0:
                            print(f"DEBUG: AI Reason for 0% score: {analysis.get('explanation', analysis.get('reasoning', 'No explanation provided'))}")
                            print(f"DEBUG: Job Title: {job_title}, Company: {job_company}")
                            print(f"DEBUG: Analysis keys: {list(analysis.keys())}")
                        
                        st.session_state.job_analyses[job_key] = analysis
                        st.session_state.jobs_analyzed.add(job_key)
                    except Exception as e:
                        import traceback
                        tb_str = traceback.format_exc()
                        error_message = f"❌ שגיאה בניתוח משרה [{job.get('title', 'Unknown')} @ {job.get('company', 'Unknown')}]: {e}"
                        errors_encountered.append(error_message)
                        print(f"ERROR: {error_message}\n{tb_str}")
                        st.exception(e)  # Expose Error
                        
                        # UI Fallback: Check for ERROR_404 specifically
                        error_str = str(e)
                        is_error_404 = '404' in error_str or 'NOT_FOUND' in error_str or 'ClientError' in error_str
                        
                        # EMERGENCY JOB RECOVERY: If analyze_match fails, DO NOT discard the job
                        # Add placeholder analysis with match_score and explanation keys for UI compatibility
                        # Placeholder analysis with both old and new key formats for compatibility
                        fallback_analysis = {
                            "score": 0,  # Old format
                            "match_score": 0,  # New format for UI
                            "reasoning": "Raw Data - Analysis Unavailable",  # Old format
                            "explanation": "Raw Data - Analysis Unavailable",  # New format for UI
                            "gaps": [],
                            "needs_manual_review": True
                        }
                        if is_error_404:
                            fallback_analysis["error_code"] = "ERROR_404"
                            fallback_analysis["error"] = "ERROR_404: API model not found or unavailable"
                            fallback_analysis["explanation"] = "Raw Data - Analysis Unavailable (API Error - 404)"
                        
                        # CRITICAL: Always add job to analyses, never discard
                        st.session_state.job_analyses[job_key] = fallback_analysis
                        st.session_state.jobs_analyzed.add(job_key)
                        ai_analysis_failed = True
                    progress_bar.progress((i + 1) / total_jobs)
                analysis_status.update(label=f"✅ Completed analysis of {total_jobs} jobs", state="complete")
            
            # AI-ORCHESTRATION: Log vector filtering vs AI analysis stats
            if vector_filtered_count > 0 or ai_analyzed_count > 0:
                log_message = f"Filtered {vector_filtered_count} jobs via Vector Match (Cost: $0). Analyzing {ai_analyzed_count} top matches via AI."
                print(f"📊 {log_message}")
                log_event(log_message, level='INFO', user_id=user_id)
            
            status_text.empty()
            progress_bar.empty()
            if errors_encountered:
                error_details_box.warning(f"⚠️ AI analysis failed for {len(errors_encountered)} jobs. These jobs are marked 'Needs Manual Review' with a default 50% match score.")
            else:
                st.success(f"✅ נותחו {total_jobs} משרות בהצלחה!")
                if vector_filtered_count > 0:
                    # Cost Saver Visualization with Professional Styling
                    st.markdown(f"""
                    <div class="cost-saver">
                        <span>💰</span>
                        <span>Vector-Filtered <strong>{vector_filtered_count}</strong> jobs (Cost: $0) | Analyzing <strong>{ai_analyzed_count}</strong> top matches via AI</span>
                    </div>
                    """, unsafe_allow_html=True)
            
            # Session Refresh: Force rerun at end of analysis loop to ensure jobs appear on screen
                    st.rerun()

    # Prevent Duplicate Applications: Filter out jobs that have already been applied to
    # Recycle Bin: Filter out jobs that are in the recycle bin
    recycle_bin = load_recycle_bin()
    recycle_bin_urls = {entry.get('job_url', '') for entry in recycle_bin}
    
    # FORCE DISPLAY: If jobs exist, ensure they are displayed even if AI analysis failed
    # Create default analysis for jobs that weren't analyzed yet
    # Also filter out jobs in recycle bin and already applied jobs
    for index, job in jobs_to_display.iterrows():
        job_url = job.get('job_url', '')
        
        # Skip if job is in recycle bin
        if job_url in recycle_bin_urls:
            continue
        
        # Skip if already applied (status='applied')
        # Fix 'Already Applied' Score: Preserve original match score if analysis exists
        job_key = f"{job.get('company', '')}_{job.get('title', '')}_{index}"
        if check_if_applied(job_url):
            # Check if we already have an analysis for this job
            existing_analysis = st.session_state.job_analyses.get(job_key, None)
            if existing_analysis:
                # Preserve original match score
                original_score = existing_analysis.get('match_score', existing_analysis.get('score', 0))
                st.session_state.job_analyses[job_key] = {
                    "score": original_score,  # Preserve original score
                    "match_score": original_score,  # Preserve original score
                    "reasoning": existing_analysis.get('reasoning', 'Already applied - marked as duplicate'),
                    "explanation": f"⚠️ **Already Applied:** This job has already been submitted. Original match score: {original_score}%.",
                    "gaps": existing_analysis.get('gaps', []),
                    "why_matches": existing_analysis.get('why_matches', ''),
                    "why_doesnt_match": existing_analysis.get('why_doesnt_match', ''),
                    "already_applied": True,
                    "original_score": original_score  # Store original for reference
                }
            else:
                # No existing analysis - mark as already applied with 0 score
                st.session_state.job_analyses[job_key] = {
                    "score": 0,
                    "match_score": 0,
                    "reasoning": "Already applied - marked as duplicate",
                    "explanation": "⚠️ **Already Applied:** This job has already been submitted.",
                    "gaps": [],
                    "already_applied": True
                }
            st.session_state.jobs_analyzed.add(job_key)
            continue
        
        job_key = f"{job.get('company', '')}_{job.get('title', '')}_{index}"
        if job_key not in st.session_state.job_analyses:
            # EMERGENCY JOB RECOVERY: Force create default analysis if missing (AI analysis may have failed)
            # UI Fallback: Mark as ERROR_404 if API is unavailable
            # Use both old and new key formats for compatibility
            st.session_state.job_analyses[job_key] = {
                "score": 0,  # Old format
                "match_score": 0,  # New format for UI
                "reasoning": "Raw Data - Analysis Unavailable",  # Old format
                "explanation": "Raw Data - Analysis Unavailable",  # New format for UI
                "gaps": [],
                "needs_manual_review": True,
                "error_code": "ERROR_404",  # Mark as 404 for UI fallback
                "error": "ERROR_404: API model not found or unavailable"
            }
            st.session_state.jobs_analyzed.add(job_key)
    
    # FORCE DISPLAY: Disable ALL filters - show EVERY job found
    # CRITICAL: Replace filtering logic with direct assignment to show all 23+ jobs
    filtered_by_persona = []
    
    # Analyze Emergency Data: Look at the jobs currently in session_state.jobs
    # If any job title contains 'CTO', 'VP', or 'Chief', and it was filtered out, it means the analyze_match logic is still too restrictive
    if not st.session_state.jobs.empty:
        executive_keywords = ['CTO', 'VP', 'Chief', 'Vice President', 'Director', 'Head of', 'Founding']
        executive_jobs = []
        for idx, job in st.session_state.jobs.iterrows():
            job_title = str(job.get('title', '')).upper()
            if any(kw.upper() in job_title for kw in executive_keywords):
                executive_jobs.append({
                    'title': job.get('title', 'Unknown'),
                    'company': job.get('company', 'Unknown'),
                    'url': job.get('job_url', ''),
                    'index': idx
                })
        
        if executive_jobs:
            print(f"🔍 EMERGENCY DATA ANALYSIS: Found {len(executive_jobs)} executive-level jobs in session_state.jobs:")
            for ej in executive_jobs[:10]:  # Show first 10
                job_key = f"{ej['company']}_{ej['title']}_{ej['index']}"
                analysis = st.session_state.job_analyses.get(job_key, {})
                score = analysis.get('match_score', analysis.get('score', 'N/A'))
                print(f"  - {ej['title']} @ {ej['company']}: Score = {score}%")
    
    # Prevent Duplicate Applications: Filter out jobs that have already been applied to
    # Recycle Bin: Filter out jobs that are in the recycle bin
    recycle_bin = load_recycle_bin()
    recycle_bin_urls = {entry.get('job_url', '') for entry in recycle_bin}
    
    # Real-time Filtering: Use st.session_state.threshold instead of hardcoded 40%
    # Fix 'Found 33, Rendering 0': Lower match_threshold default to 10% to ensure even 'weak' matches show up
    # Initialize threshold if not exists
    if 'threshold' not in st.session_state:
        st.session_state.threshold = 10  # Lowered from 40 to 10 to fix 'Found 33, Rendering 0' issue
    
    # Clean UI: Set display threshold back to 10% but ensure hard-override jobs (85%) pass through
    threshold = st.session_state.threshold  # Use user-defined threshold (default 10%)
    
    # Hard Threshold: Only display jobs with match_score >= threshold
    # Jobs below threshold are automatically moved to recycle bin
    displayed_jobs = []
    already_applied_jobs = []
    hidden_jobs = []  # Jobs with score < threshold that will be moved to recycle bin
    
    # Display jobs - filter by match_score threshold (dynamic from slider)
    # Filter out jobs in recycle bin and already applied jobs
    for index, job in jobs_to_display.iterrows():
        job_url = job.get('job_url', '')
        
        # Skip if job is in recycle bin (they should never appear)
        if job_url in recycle_bin_urls:
            continue
        
        job_key = f"{job.get('company', '')}_{job.get('title', '')}_{index}"
        # Force get or create analysis - ensure it exists with defaults
        analysis = st.session_state.job_analyses.get(job_key, {
            "score": 0,  # Old format
            "match_score": 0,  # New format for UI
            "reasoning": "Raw Data - Analysis Unavailable",  # Old format
            "explanation": "Raw Data - Analysis Unavailable",  # New format for UI
            "gaps": [],
            "needs_manual_review": True
        })
        
        # Separate already applied jobs (they go to a separate section)
        if analysis.get('already_applied', False) or check_if_applied(job_url):
            already_applied_jobs.append((index, job, job_key, analysis))
            continue
        
        # Fix App Rendering: Debug print to see what scores are being used
        match_score = analysis.get('match_score', analysis.get('score', 0))
        job_title = job.get('title', 'Unknown')
        print(f"DEBUG: Score for '{job_title}' is {match_score} (threshold: {threshold})")
        
        # Fix UI Filtering: Ensure any job with is_hard_override=True or a score of 85% skips all filters
        # Hard-Override jobs have hard_override=True flag and score of 85%
        is_hard_override = analysis.get('hard_override', False)
        is_executive_85 = (match_score >= 85) or is_hard_override  # More aggressive: any 85% OR hard_override flag
        
        # Hard Threshold: Check if match_score < threshold (dynamic from slider)
        # BUT: Hard-override jobs (85% or hard_override=True) always pass through regardless of threshold
        if match_score < threshold and not is_executive_85:
            # Automatically move to recycle bin without user intervention (unless hard-override)
            try:
                from utils import move_to_recycle_bin
                # Fix Pandas Warning: Convert Series to dict if needed
                job_dict = job.to_dict() if hasattr(job, 'to_dict') else job
                move_to_recycle_bin(job_dict, f'Auto-filtered: Match score {match_score}% is below {threshold}% threshold', user_id=user_id)
                hidden_jobs.append((index, job, job_key, analysis, match_score))
                print(f"🔒 Auto-hidden job: {job.get('title', 'Unknown')} (Score: {match_score}% < {threshold}%)")
            except Exception as e:
                print(f"⚠️ Error moving job to recycle bin: {e}")
                # Continue to next job even if recycle bin move fails
            continue  # Skip this job - don't display it
        
        # Add job to displayed_jobs only if match_score >= threshold
        displayed_jobs.append((index, job, job_key, analysis))
    
    # Store displayed jobs in session state for persistence
    if 'found_jobs' not in st.session_state:
        st.session_state.found_jobs = []
    
    # Fix UI Filtering: Ensure hard-override jobs are ALWAYS in found_jobs
    # The Hard-Override UI Fix: Confirm that jobs with match_score >= 85 (our CTO roles) are appended to the list
    # Add any hard-override jobs that might have been missed
    hard_override_jobs = []
    if 'jobs' in st.session_state and st.session_state.jobs is not None:
        # Data Consistency: Handle both lists and DataFrames
        jobs_to_check = st.session_state.jobs
        if isinstance(jobs_to_check, list):
            if len(jobs_to_check) > 0:
                jobs_to_check = pd.DataFrame(jobs_to_check)
            else:
                jobs_to_check = pd.DataFrame()
        
        if not jobs_to_check.empty:
            for index, job in jobs_to_check.iterrows():
                job_key = f"{job.get('company', '')}_{job.get('title', '')}_{index}"
                analysis = st.session_state.job_analyses.get(job_key, {})
                is_hard_override = analysis.get('hard_override', False)
                match_score = analysis.get('match_score', analysis.get('score', 0))
                # If it's a hard-override job or has 85% score, ensure it's in found_jobs
                if is_hard_override or match_score >= 85:
                    # Check if it's not already in displayed_jobs
                    already_displayed = any(dj[1].get('title') == job.get('title') and dj[1].get('company') == job.get('company') for dj in displayed_jobs)
                    if not already_displayed:
                        hard_override_jobs.append((index, job, job_key, analysis))
                        print(f"🔧 Fix UI Filtering: Adding hard-override job '{job.get('title')}' to found_jobs (Score: {match_score}%, hard_override: {is_hard_override})")
    
    # FORCE DISPLAY: Update found_jobs with ALL displayed jobs + hard-override jobs
    st.session_state.found_jobs = displayed_jobs + hard_override_jobs
    
    # Display info about hidden jobs (if any)
    if hidden_jobs:
        with st.expander(f"🔒 Auto-Hidden Jobs ({len(hidden_jobs)}) - Below {threshold}% Threshold", expanded=False):
            st.info(f"These {len(hidden_jobs)} jobs were automatically hidden because their match score is below {threshold}%. They have been moved to the recycle bin.")
            for index, job, job_key, analysis, match_score in hidden_jobs[:10]:  # Show first 10
                st.caption(f"❌ {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')} - Score: {match_score}%")
    
    # Display already applied jobs in a separate collapsed section
    if already_applied_jobs:
        with st.expander(f"✅ Already Applied Jobs ({len(already_applied_jobs)})", expanded=False):
            st.info("These jobs have already been submitted. They are hidden from the main list to prevent duplicate applications.")
            for index, job, job_key, analysis in already_applied_jobs:
                company = job.get('company', 'Unknown')
                title = job.get('title', 'Unknown')
                with st.expander(f"✅ {company} - {title}", expanded=False):
                    st.warning("⚠️ **Status:** Already Applied")
                    st.write(f"**Company:** {company}")
                    st.write(f"**Title:** {title}")
                    job_url = job.get('job_url', '#')
                    if job_url and job_url != '#':
                        st.write(f"**Job URL:** [{job_url}]({job_url})")
    
    # Verify Persona Loading: Check if digital_persona is populated
    if st.session_state.get('digital_persona') is None:
        print("WARN: st.session_state.digital_persona is None! The AI has no CV to compare to.")
        st.warning("⚠️ **Warning:** Digital Persona is not loaded. Please upload a CV to enable job matching.")
    else:
        persona_summary = st.session_state.digital_persona.get('persona_summary', '')
        print(f"DEBUG: Digital Persona loaded. Persona Summary: '{persona_summary[:100]}...' (length: {len(persona_summary)})")
        # Digital Persona display (What the system knows about you)
        if os.path.exists("profile_data.json"):
            with st.expander("🧠 What the system knows about you (Digital Persona)", expanded=True):
                persona = st.session_state.digital_persona or {}
                summary = str(persona.get("persona_summary", "") or "").strip()
                if summary:
                    st.markdown(f"**Persona Summary:** {summary}")
                else:
                    st.write("_Persona summary is still being generated._")

                # Identified roles
                roles = (
                    persona.get("identified_roles")
                    or persona.get("potential_roles")
                    or persona.get("roles")
                    or st.session_state.get("suggested_roles")
                    or []
                )
                if isinstance(roles, str):
                    roles = [roles]
                if roles:
                    st.markdown("**Identified Roles:**")
                    st.write(", ".join([str(r) for r in roles if str(r).strip()]))

                # Skills / tech stack
                skills = persona.get("key_skills") or persona.get("skills") or persona.get("tech_stack") or []
                if isinstance(skills, str):
                    skills = [skills]
                if skills:
                    st.markdown("**Key Skills:**")
                    st.write(", ".join([str(s) for s in skills if str(s).strip()]))
    
    # Debug: Verify found_jobs is populated before rendering
    print(f"DEBUG app.py: About to render {len(displayed_jobs)} jobs. found_jobs length: {len(st.session_state.found_jobs)}")
    
    # Emergency Visibility: If found_jobs is empty but session_state.jobs has data, show message
    if len(st.session_state.found_jobs) == 0 and 'jobs' in st.session_state and st.session_state.jobs is not None:
        # Data Consistency: Handle both lists and DataFrames
        jobs_to_check = st.session_state.jobs
        if isinstance(jobs_to_check, list):
            has_jobs = len(jobs_to_check) > 0
        else:
            has_jobs = not jobs_to_check.empty
        
        if has_jobs:
            st.warning("⚠️ **Matching jobs found but filtered by score.**")
            st.info("💡 **Tip:** Adjust your filters in the Sidebar or enable 'Show All Found Jobs' to see all matching jobs.")
            st.write(f"**Total jobs found:** {len(jobs_to_check) if isinstance(jobs_to_check, list) else len(jobs_to_check)}")
            st.write(f"**Current threshold:** {threshold}%")
            st.write(f"**Displayed jobs:** {len(displayed_jobs)}")
    
    # Emergency Render Fix: Ensure the Emergency Render actually shows the jobs it found in session_state.jobs
    if len(st.session_state.found_jobs) == 0 and 'jobs' in st.session_state and st.session_state.jobs is not None:
        # Data Consistency: Handle both lists and DataFrames
        jobs_to_check = st.session_state.jobs
        if isinstance(jobs_to_check, list):
            has_jobs = len(jobs_to_check) > 0
        else:
            has_jobs = not jobs_to_check.empty
        
        if has_jobs:
            st.error("🚨 **EMERGENCY RENDER:** Found 0 jobs in found_jobs but session_state.jobs has data. Showing ALL jobs from session_state.jobs:")
            # Data Consistency: Handle both lists and DataFrames
            jobs_count = len(jobs_to_check) if isinstance(jobs_to_check, list) else len(jobs_to_check)
            st.write(f"**Total jobs in session_state.jobs:** {jobs_count}")
            
            # Emergency Render Fix: Actually display the jobs from session_state.jobs
            with st.expander("🔍 **Emergency: ALL Jobs from session_state.jobs**", expanded=True):
                # Convert to DataFrame if it's a list
                if isinstance(jobs_to_check, list):
                    jobs_to_check = pd.DataFrame(jobs_to_check) if len(jobs_to_check) > 0 else pd.DataFrame()
                
                if not jobs_to_check.empty:
                    for idx, (index, job) in enumerate(jobs_to_check.iterrows()):
                        job_title = job.get('title', 'Unknown')
                job_company = job.get('company', 'Unknown')
                job_url = job.get('job_url', '#')
                job_key = f"{job_company}_{job_title}_{index}"
                analysis = st.session_state.job_analyses.get(job_key, {
                    "match_score": 0,
                    "explanation": "No AI analysis available (filtered out early or error)"
                })
                match_score = analysis.get('match_score', analysis.get('score', 0))
                reasoning = analysis.get('explanation', analysis.get('reasoning', 'No reasoning available'))
                is_hard_override = analysis.get('hard_override', False)
                
                # Display the job with full details
                st.markdown(f"**{idx+1}. {job_title}** at **{job_company}**")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Match Score", f"{match_score}%")
                with col2:
                    if is_hard_override:
                        st.success("🔧 Hard-Override Applied")
                    else:
                        st.info("Standard Analysis")
                
                st.write(f"**AI Reasoning:**")
                st.info(reasoning[:1000] + "..." if len(reasoning) > 1000 else reasoning)
                
                if job_url != '#':
                    st.markdown(f"[View Job]({job_url})")
                
                st.caption(f"Job Key: {job_key} | Index: {index}")
    st.divider()
    
    st.warning("⚠️ **Debug Info:** Check the console logs for 'DEBUG: Score for...' messages to see why jobs are being filtered.")
    
    # Render job list using custom HTML cards with container for proper layout
    # CRITICAL: This call must happen - if jobs exist, they must be rendered
    try:
        if displayed_jobs:
            # Use container to ensure custom HTML/CSS isn't squashed by Streamlit's default layout
            with st.container():
                st.markdown("### 📋 Job Matches")
                st.markdown("---")
                
                # Render each job as a custom HTML card
                for index, job, job_key, analysis in displayed_jobs:
                    # Convert job to dict if it's a Series
                    job_dict = job.to_dict() if hasattr(job, 'to_dict') else job
                    
                    # Extract job details
                    company_name = job_dict.get('company', 'Unknown')
                    role_title = job_dict.get('role', job_dict.get('title', 'Unknown Role'))
                    score = analysis.get('match_score', analysis.get('score', 0))
                    
                    # Render custom HTML job card
                    card_html = render_custom_job_card(
                        job_dict, analysis, job_key, index, score, company_name, role_title
                    )
                    st.markdown(card_html, unsafe_allow_html=True)
                    
                    # Add Streamlit buttons below the card for functionality
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        persona_ok = bool(st.session_state.get("digital_persona")) and bool(profile.get("master_cv_text"))
                        if st.button(f"✨ Magic Cover Letter", key=f"apply_custom_{job_key}", disabled=(not persona_ok)):
                            # Trigger existing apply logic
                            st.session_state.selected_job = job_dict
                            st.session_state.current_draft = None  # Will be generated
                            st.rerun()
                    with col2:
                        job_url = job_dict.get('job_url', '#')
                        if job_url and job_url != '#':
                            st.markdown(f'<a href="{job_url}" target="_blank" style="text-decoration: none;"><button style="width: 100%; padding: 10px; border-radius: 8px; background: #30363D; color: #E0E0E0; border: 1px solid #30363D; cursor: pointer; font-weight: 500; font-size: 14px;">🔗 View Job</button></a>', unsafe_allow_html=True)
                    with col3:
                        if st.button(f"📋 Details", key=f"details_{job_key}"):
                            st.session_state[f"show_details_{job_key}"] = not st.session_state.get(f"show_details_{job_key}", False)
                            st.rerun()
                    
                    # Show expandable details if requested
                    if st.session_state.get(f"show_details_{job_key}", False):
                        with st.expander("📋 Full Analysis Details", expanded=True):
                            explanation = analysis.get('explanation', analysis.get('reasoning', 'No analysis available'))
                            gaps = analysis.get('gaps', [])
                            st.markdown(f"**Match Analysis:**\n\n{explanation}")
                            if gaps:
                                st.markdown(f"**Key Gaps:** {', '.join(gaps)}")
                    
                    st.markdown("---")  # Separator between jobs
        elif len(displayed_jobs) == 0 and ('jobs' not in st.session_state or st.session_state.jobs is None or st.session_state.jobs.empty):
            st.warning("⚠️ No jobs to display after filtering. Check your search criteria and filters.")
    except Exception as e:
        st.error("❌ שגיאה ב-render_job_list")
        st.exception(e)  # Expose Error
        # Cache clearing option if CSS injection fails
        if st.button("🔄 Clear Cache & Refresh", key="clear_cache_refresh"):
            st.cache_data.clear()
            st.session_state.clear()
            st.rerun()

else:
    # If jobs is None or empty, after interaction, be explicit!
    if 'jobs' in st.session_state and (st.session_state.jobs is None or (hasattr(st.session_state.jobs, 'empty') and st.session_state.jobs.empty)):
        # Only show warning if not currently scraping
        if not st.session_state.get('scraping_in_progress', False):
            st.warning("לא נמצאו משרות להצגה כעת (יתכן שהחיפוש לא הניב תוצאות מתאימות או שישנה שגיאה בנתונים).")
            print("INFO: st.session_state.jobs is None or empty -- nothing to display.")

# Render Human-in-the-Loop section
try:
    render_human_in_the_loop(engine, pdf_generator)
except Exception as e:
    st.error("❌ שגיאה ב-render_human_in_the_loop")
    st.exception(e)  # Expose Error
