"""
UI Layout components for Vision Stack 2026.
Contains Sidebar components, Global Search Status display, and job rendering loops.
"""
import streamlit as st
import subprocess
import os
import json
import time
import csv
import uuid
from utils import load_blacklist, save_blacklist, add_to_blacklist, load_user_learnings, add_rejection_learning, check_system_integrity, update_preferences, add_skill_to_preferences, move_to_recycle_bin, check_if_applied, get_user_id

# ============================================================================
# GLOBAL CSS & STYLING (Hybrid HTML/CSS Approach)
# ============================================================================
def inject_global_css():
    """Inject global CSS for modern dark theme."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        /* Global Dark Matte Background */
        .stApp {
            background: #0B0E11 !important;
            font-family: 'Inter', 'Roboto', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }
        
        /* Mobile-Responsive: Work from anywhere */
        @media (max-width: 768px) {
            .stApp {
                padding: 8px !important;
            }
            
            .custom-job-card {
                padding: 16px !important;
                margin-bottom: 12px !important;
            }
            
            .match-gauge-container {
                flex-direction: column !important;
                gap: 12px !important;
            }
            
            .job-card-header {
                flex-direction: column !important;
                align-items: flex-start !important;
            }
            
            .job-actions {
                flex-direction: column !important;
                width: 100% !important;
            }
            
            .magic-button {
                width: 100% !important;
                margin-bottom: 8px !important;
            }
            
            .dna-helix {
                height: 150px !important;
            }
            
            .capability-pill {
                font-size: 11px !important;
                padding: 6px 12px !important;
            }
        }
        
        @media (max-width: 480px) {
            .custom-job-card {
                padding: 12px !important;
            }
            
            .job-title {
                font-size: 18px !important;
            }
            
            .job-company {
                font-size: 12px !important;
            }
        }
        
        /* Hide Streamlit Default Borders */
        .stExpander {
            border: none !important;
            background: transparent !important;
        }
        
        .stExpander > div {
            border: none !important;
            background: transparent !important;
        }
        
        /* Custom Job Card Styling */
        .custom-job-card {
            background: #161B22;
            border: 1px solid #30363D;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 16px;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
        }
        
        .custom-job-card:hover {
            border-color: #3B82F6;
            box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);
            transform: translateY(-2px);
        }
        
        /* Match Score Gauge SVG */
        .match-gauge-container {
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .gauge-svg {
            filter: drop-shadow(0 0 8px currentColor);
        }
        
        .gauge-high {
            color: #10B981;
        }
        
        .gauge-medium {
            color: #3B82F6;
        }
        
        .gauge-low {
            color: #6B7280;
        }
        
        /* Magic Button */
        .magic-button {
            background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%);
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            color: white;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 0 15px rgba(59, 130, 246, 0.3);
            font-family: 'Inter', sans-serif;
        }
        
        .magic-button:hover {
            box-shadow: 0 0 25px rgba(59, 130, 246, 0.6);
            transform: translateY(-2px);
        }
        
        /* DNA Helix Animation */
        @keyframes dnaScan {
            0%, 100% {
                opacity: 0.3;
                transform: translateY(0);
            }
            50% {
                opacity: 1;
                transform: translateY(-10px);
            }
        }
        
        .dna-helix {
            position: relative;
            width: 100%;
            height: 200px;
            margin: 20px 0;
        }
        
        .dna-strand {
            position: absolute;
            width: 2px;
            background: linear-gradient(180deg, #3B82F6 0%, #10B981 100%);
            animation: dnaScan 2s ease-in-out infinite;
        }
        
        /* Latent Capabilities Pills */
        .capability-pill {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            margin: 6px 4px;
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(59, 130, 246, 0.1) 100%);
            border: 1px solid #3B82F6;
            color: #3B82F6;
            box-shadow: 0 0 10px rgba(59, 130, 246, 0.3);
            font-family: 'Inter', sans-serif;
        }
        
        /* Job Card Content */
        .job-card-header {
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 16px;
        }
        
        .job-title {
            font-size: 20px;
            font-weight: 600;
            color: #E0E0E0;
            margin: 0;
        }
        
        .job-company {
            font-size: 14px;
            color: #8B949E;
            margin: 4px 0 0 0;
        }
        
        .job-actions {
            display: flex;
            gap: 12px;
            margin-top: 20px;
        }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# CUSTOM HTML COMPONENTS
# ============================================================================

def create_circular_gauge_svg(score, size=80):
    """
    Create a circular SVG gauge for match score.
    
    Args:
        score: Match score (0-100)
        size: Size of the gauge in pixels
    
    Returns:
        SVG string
    """
    # Determine color based on score
    if score > 80:
        color = "#10B981"  # Emerald
        glow_color = "rgba(16, 185, 129, 0.4)"
    elif score >= 60:
        color = "#3B82F6"  # Cyber Blue
        glow_color = "rgba(59, 130, 246, 0.4)"
    else:
        color = "#6B7280"  # Gray
        glow_color = "rgba(107, 114, 128, 0.2)"
    
    # Calculate stroke-dasharray for progress
    circumference = 2 * 3.14159 * (size / 2 - 8)
    offset = circumference * (1 - score / 100)
    
    svg = f"""
    <svg width="{size}" height="{size}" class="gauge-svg" style="filter: drop-shadow(0 0 8px {glow_color});">
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 8}" 
                fill="none" stroke="#30363D" stroke-width="6"/>
        <circle cx="{size/2}" cy="{size/2}" r="{size/2 - 8}" 
                fill="none" stroke="{color}" stroke-width="6"
                stroke-dasharray="{circumference}"
                stroke-dashoffset="{offset}"
                stroke-linecap="round"
                transform="rotate(-90 {size/2} {size/2})"
                style="transition: stroke-dashoffset 0.5s ease;"/>
        <text x="{size/2}" y="{size/2 + 6}" 
              text-anchor="middle" 
              fill="{color}" 
              font-size="20" 
              font-weight="700"
              font-family="Inter, sans-serif">{score}%</text>
    </svg>
    """
    return svg

def render_custom_job_card(job, analysis, job_key, index, score, company_name, role_title):
    """
    Render a custom HTML job card with modern styling.
    
    Args:
        job: Job dictionary
        analysis: Analysis dictionary
        job_key: Unique job key
        index: Job index
        score: Match score
        company_name: Company name
        role_title: Role title
    
    Returns:
        HTML string
    """
    # Get additional info
    job_url = job.get('job_url', '#')
    explanation = analysis.get('explanation', analysis.get('reasoning', 'No analysis available'))
    gaps = analysis.get('gaps', [])
    
    # Create gauge SVG
    gauge_svg = create_circular_gauge_svg(score)
    
    # Determine gauge class for styling
    gauge_class = "gauge-high" if score > 80 else "gauge-medium" if score >= 60 else "gauge-low"
    
    # Create gaps display
    gaps_html = ""
    if gaps:
        gaps_html = f"""
        <div style="margin-top: 12px;">
            <strong style="color: #8B949E; font-size: 12px;">Key Gaps:</strong>
            <div style="margin-top: 6px;">
                {', '.join([f'<span style="color: #E0E0E0; font-size: 12px;">{gap}</span>' for gap in gaps[:3]])}
            </div>
        </div>
        """
    
    html = f"""
    <div class="custom-job-card">
        <div class="job-card-header">
            <div class="match-gauge-container">
                <div class="{gauge_class}">
                    {gauge_svg}
                </div>
                <div style="flex: 1;">
                    <h3 class="job-title">{role_title}</h3>
                    <p class="job-company">{company_name}</p>
                </div>
            </div>
        </div>
        
        <div style="color: #E0E0E0; font-size: 14px; line-height: 1.6; margin-bottom: 16px;">
            {explanation[:200]}{'...' if len(explanation) > 200 else ''}
        </div>
        
        {gaps_html}
        
        <div class="job-actions">
            <!-- Buttons will be rendered via Streamlit below the HTML card -->
        </div>
    </div>
    """
    return html

def render_dna_helix_visualization(latent_capabilities=None):
    """
    Render DNA helix visualization with scanning pulse effect.
    
    Args:
        latent_capabilities: List of latent capabilities to display as pills
    
    Returns:
        HTML string
    """
    # Create DNA helix SVG
    helix_svg = """
    <svg width="100%" height="200" viewBox="0 0 300 200" style="overflow: visible;">
        <defs>
            <linearGradient id="dnaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:#3B82F6;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#10B981;stop-opacity:1" />
            </linearGradient>
        </defs>
        <!-- Left strand -->
        <path d="M 50 20 Q 80 60, 50 100 Q 80 140, 50 180" 
              stroke="url(#dnaGradient)" 
              stroke-width="3" 
              fill="none"
              style="animation: dnaScan 2s ease-in-out infinite; animation-delay: 0s;"/>
        <path d="M 50 30 Q 75 70, 50 110 Q 75 150, 50 190" 
              stroke="url(#dnaGradient)" 
              stroke-width="2" 
              fill="none"
              opacity="0.6"
              style="animation: dnaScan 2s ease-in-out infinite; animation-delay: 0.3s;"/>
        
        <!-- Right strand -->
        <path d="M 250 20 Q 220 60, 250 100 Q 220 140, 250 180" 
              stroke="url(#dnaGradient)" 
              stroke-width="3" 
              fill="none"
              style="animation: dnaScan 2s ease-in-out infinite; animation-delay: 0.5s;"/>
        <path d="M 250 30 Q 225 70, 250 110 Q 225 150, 250 190" 
              stroke="url(#dnaGradient)" 
              stroke-width="2" 
              fill="none"
              opacity="0.6"
              style="animation: dnaScan 2s ease-in-out infinite; animation-delay: 0.8s;"/>
        
        <!-- Connecting rungs -->
        <line x1="50" y1="50" x2="250" y2="50" stroke="#3B82F6" stroke-width="2" opacity="0.4" style="animation: dnaScan 2s ease-in-out infinite; animation-delay: 0.1s;"/>
        <line x1="50" y1="100" x2="250" y2="100" stroke="#10B981" stroke-width="2" opacity="0.4" style="animation: dnaScan 2s ease-in-out infinite; animation-delay: 1s;"/>
        <line x1="50" y1="150" x2="250" y2="150" stroke="#3B82F6" stroke-width="2" opacity="0.4" style="animation: dnaScan 2s ease-in-out infinite; animation-delay: 1.5s;"/>
    </svg>
    """
    
    # Create capability pills
    pills_html = ""
    if latent_capabilities and isinstance(latent_capabilities, list):
        pills_html = '<div style="margin-top: 20px; display: flex; flex-wrap: wrap; gap: 8px;">'
        for capability in latent_capabilities[:8]:  # Limit to 8 for display
            pills_html += f'<span class="capability-pill">{capability}</span>'
        pills_html += '</div>'
    
    html = f"""
    <div style="background: #161B22; border: 1px solid #30363D; border-radius: 12px; padding: 24px; margin: 20px 0;">
        <h3 style="color: #E0E0E0; font-family: 'Inter', sans-serif; margin-bottom: 16px; font-size: 18px;">
            🧬 Career DNA Analysis
        </h3>
        <div class="dna-helix">
            {helix_svg}
        </div>
        {pills_html}
    </div>
    """
    return html

def render_sidebar(engine, profile):
    """
    Renders the complete sidebar with Search Preferences, Skill Bucket, Global Search Status,
    Agent Source Network, Strategy Preview, and Job Management.
    Returns tuple: (must_have_keywords, exclude_keywords)
    """
    # Inject global CSS for modern dark theme
    inject_global_css()
    
    with st.sidebar:
        # Branding & UI Header with Gradient Text
        st.markdown("""
        <div style="text-align: center; padding: 10px 0;">
            <h2 style="background: linear-gradient(135deg, #3B82F6 0%, #8B5CF6 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; font-weight: 700;">
                🧬 Persona
            </h2>
            <p style="color: #8B949E; font-size: 12px; margin-top: -10px;">Your Autonomous Digital Recruitment Agent</p>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        # Turbo Status (Paid tier)
        try:
            model_id = getattr(engine, "model_id", "") or ""
            if ":free" not in str(model_id).lower():
                st.caption("🚀 Paid API Mode: Active")
        except Exception:
            pass

        # ------------------------------------------------------------
        # System Maintenance (Reset & Debug Tools)
        # ------------------------------------------------------------
        st.subheader("🛠️ System Maintenance")
        try:
            if os.path.exists("persona_cache.json"):
                st.caption("🟢 Persona Active (cache exists)")
            else:
                st.caption("🔴 No Persona (cache missing)")
        except Exception:
            st.caption("🔴 No Persona (cache status unknown)")

        if st.button("🧹 Reset Persona & Locks", key="reset_persona_and_locks_btn"):
            errors = []
            # Delete persona cache + lock
            for path in ["persona_cache.json", ".ai_persona.lock", ".ai_enrich.lock"]:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception as e:
                    errors.append(f"{path}: {e}")

            # Clear ALL session state keys
            try:
                for k in list(st.session_state.keys()):
                    try:
                        del st.session_state[k]
                    except Exception:
                        pass
            except Exception as e:
                errors.append(f"session_state_clear: {e}")

            if errors:
                st.error("❌ Reset completed with warnings.")
                with st.expander("Show Technical Details"):
                    st.code("\n".join(errors))
            else:
                st.success("✅ Persona cache + locks reset. Restarting…")

            # Let filesystem settle before rerun
            time.sleep(0.2)
            st.rerun()

        st.divider()

        # Admin Console navigation (in-app)
        if "show_admin_console" not in st.session_state:
            st.session_state.show_admin_console = False
        col_admin_a, col_admin_b = st.columns(2)
        with col_admin_a:
            if st.button("🛠️ Admin Console", key="open_admin_console_btn"):
                st.session_state.show_admin_console = True
                st.rerun()
        with col_admin_b:
            if st.button("⬅️ Back to Persona", key="close_admin_console_btn"):
                st.session_state.show_admin_console = False
                st.rerun()

        st.header("🔍 Search Preferences")

        must_have_keywords_input = st.text_input(
            "Must-have Keywords",
            value="",
            help="Comma-separated keywords (e.g., Shopify, Magento, E-commerce). Jobs must contain at least one.",
            key="must_have_keywords"
        )

        exclude_keywords_input = st.text_input(
            "Exclude Keywords",
            value="",
            help="Comma-separated keywords (e.g., Gaming, Cyber). Jobs containing these will be hidden.",
            key="exclude_keywords"
        )

        # Parse keywords
        must_have_keywords = [k.strip().lower() for k in must_have_keywords_input.split(',') if k.strip()] if must_have_keywords_input else []
        exclude_keywords = [k.strip().lower() for k in exclude_keywords_input.split(',') if k.strip()] if exclude_keywords_input else []

        st.divider()

        # Background AI queue status (non-blocking)
        try:
            pending = 0
            if os.path.exists("discovered_jobs.csv"):
                with open("discovered_jobs.csv", "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        status = str(r.get("status", "") or "").strip().lower()
                        ms_raw = r.get("match_score", "")
                        try:
                            ms = int(float(ms_raw)) if str(ms_raw).strip() != "" else 0
                        except Exception:
                            ms = 0
                        if status == "candidate" or ms == 70:
                            pending += 1
            if pending > 0:
                st.caption(f"🤖 AI is analyzing {pending} more matches in the background…")
        except Exception:
            pass

        # ------------------------------------------------------------
        # User Hub: 5-step Personal DNA + Career Horizon Wizard
        # ------------------------------------------------------------
        st.header("👤 User Hub")
        with st.expander("🧬 Personal DNA & Career Horizon Wizard (5 steps)", expanded=False):
            from utils import load_preferences, save_preferences
            prefs = load_preferences()
            prefs.setdefault("personal_dna", {})
            prefs["personal_dna"].setdefault("hard_constraints", {})
            prefs["personal_dna"].setdefault("soft_traits", {})
            prefs.setdefault("career_horizon", {})

            if "dna_wizard_step" not in st.session_state:
                st.session_state.dna_wizard_step = 1

            step = int(st.session_state.dna_wizard_step)
            st.caption(f"Step {step}/5")

            hc = prefs["personal_dna"]["hard_constraints"]
            stt = prefs["personal_dna"]["soft_traits"]
            ch = prefs["career_horizon"]

            def _persist():
                save_preferences(prefs, preserve_user_settings=True)
                st.toast("Persona updated. Preferences saved.")

            if step == 1:
                st.subheader("1) Location & Travel (Hard)")
                loc = hc.get("location_flexibility", {}) or {}
                allowed = loc.get("allowed_cities", ["Tel Aviv", "Kfar Saba", "Petah Tikva"])
                allowed_cities = st.multiselect(
                    "Allowed cities",
                    options=["Tel Aviv", "Kfar Saba", "Petah Tikva", "Herzliya", "Raanana", "Haifa", "Jerusalem", "Netanya", "Beer Sheva", "Modiin"],
                    default=allowed,
                    key="dna_allowed_cities"
                )
                israel_only = st.checkbox("Israel only", value=bool(loc.get("israel_only", True)), key="dna_israel_only")
                allow_relocation = st.checkbox("Allow relocation", value=bool(loc.get("allow_relocation", False)), key="dna_allow_relocation")

                travel = hc.get("travel_limits", {}) or {}
                max_commute = st.slider("Max commute minutes", 0, 180, int(travel.get("max_commute_minutes", 45) or 45), key="dna_max_commute")
                overseas = st.selectbox(
                    "Overseas travel",
                    options=["none", "rare", "some", "frequent"],
                    index=["none", "rare", "some", "frequent"].index(str(travel.get("overseas_travel", "none"))),
                    key="dna_overseas"
                )

                hc["location_flexibility"] = {"allowed_cities": allowed_cities, "israel_only": israel_only, "allow_relocation": allow_relocation}
                hc["travel_limits"] = {"max_commute_minutes": int(max_commute), "overseas_travel": str(overseas)}
                prefs["personal_dna"]["hard_constraints"] = hc

            elif step == 2:
                st.subheader("2) Work Model (Hard)")
                wm = hc.get("work_model", {}) or {}
                remote_only = st.checkbox("Remote only", value=bool(wm.get("remote_only", False)), key="dna_remote_only")
                hybrid_allowed = st.checkbox("Hybrid allowed", value=bool(wm.get("hybrid_allowed", True)), key="dna_hybrid_allowed")
                min_home_days = st.slider("Minimum home days per week", 0, 5, int(wm.get("min_home_days", 2) or 2), key="dna_min_home_days")
                hc["work_model"] = {"remote_only": remote_only, "hybrid_allowed": hybrid_allowed, "min_home_days": int(min_home_days)}
                prefs["personal_dna"]["hard_constraints"] = hc

            elif step == 3:
                st.subheader("3) Hobbies & Values (Soft)")
                hobbies_csv = ", ".join(stt.get("hobbies", []) or [])
                hobbies_in = st.text_input("Hobbies (comma-separated)", value=hobbies_csv, key="dna_hobbies")
                hobbies = [h.strip() for h in hobbies_in.split(",") if h.strip()]
                stt["hobbies"] = hobbies
                prefs["personal_dna"]["soft_traits"] = stt

            elif step == 4:
                st.subheader("4) Tone & Communication (Soft)")
                comm = st.text_input("Communication style", value=str(stt.get("communication_style", "Professional yet authentic")), key="dna_comm_style")
                tone = st.text_input("Tone of voice", value=str(stt.get("tone_voice", "Bold, result-oriented, empathetic")), key="dna_tone_voice")
                stt["communication_style"] = comm
                stt["tone_voice"] = tone
                prefs["personal_dna"]["soft_traits"] = stt

            elif step == 5:
                st.subheader("5) Career Horizon Goals (Additive)")
                roles = ch.get("target_roles", ["CTO", "Head of AI", "Product Architect"])
                target_roles = st.multiselect(
                    "Target roles (long-term)",
                    options=["CTO", "Head of AI", "Product Architect", "VP Engineering", "Chief Architect", "Principal Engineer"],
                    default=roles,
                    key="dna_target_roles"
                )
                w = float(ch.get("additive_weight", 0.2) or 0.2)
                additive_weight = st.slider("Additive weight", 0.0, 1.0, float(w), 0.05, key="dna_additive_weight")
                prefs["career_horizon"] = {"target_roles": target_roles, "additive_weight": float(additive_weight)}

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("⬅️ Back", disabled=(step <= 1), key="dna_back"):
                    st.session_state.dna_wizard_step = max(1, step - 1)
                    _persist()
                    st.rerun()
            with col_b:
                if st.button("💾 Save", key="dna_save"):
                    _persist()
                    st.success("Saved.")
            with col_c:
                if st.button("Next ➡️", disabled=(step >= 5), key="dna_next"):
                    st.session_state.dna_wizard_step = min(5, step + 1)
                    _persist()
                    st.rerun()

        # ------------------------------------------------------------
        # Career Horizon Section (Horizon Roles with Gap Analysis)
        # ------------------------------------------------------------
        st.header("🎯 Career Horizon")
        
        # Load preferences for user ambitions
        from utils import load_preferences, save_preferences, get_user_id
        user_id = get_user_id()
        preferences = load_preferences(user_id)
        user_ambitions = preferences.get('user_identity', {}).get('user_ambitions', '')
        
        # Interactive Learning: Ambitions text area
        st.subheader("📝 Tell Persona More About Your Ambitions")
        ambitions_text = st.text_area(
            "What are your career goals and ambitions? (This influences job matching and Horizon Role suggestions)",
            value=user_ambitions,
            height=150,
            placeholder="Example: I want to transition from Marketing Director to VP Product. I'm interested in leading cross-functional teams and building product strategy...",
            key="user_ambitions_input",
            help="Describe your career goals, desired transitions, or strategic pivots. This helps the AI better match jobs and suggest Horizon Roles."
        )
        
        # Save ambitions when changed
        if ambitions_text != user_ambitions:
            if st.button("💾 Save Ambitions", key="save_ambitions_btn"):
                preferences['user_identity']['user_ambitions'] = ambitions_text
                save_preferences(preferences, preserve_user_settings=True, user_id=user_id)
                st.success("✅ Ambitions saved! This will influence job matching and Horizon Role suggestions.")
                st.rerun()
        
        st.divider()
        
        # Dynamic UI Update: Fetch horizon roles strictly from newly generated Persona in DB
        # NO fallback to old cached data - ensures fresh data after CV upload
        horizon_roles = None
        
        # Priority 1: Check session state (if just generated)
        if 'horizon_roles' in st.session_state and st.session_state.horizon_roles:
            horizon_roles = st.session_state.horizon_roles
            print(f"✅ Using horizon roles from session state (freshly generated)")
        else:
            # Priority 2: Load from database (fresh data, no cache fallback)
            try:
                from utils import get_db_manager
                db = get_db_manager()
                horizon_roles = db.get_horizon_roles(user_id)
                if horizon_roles:
                    st.session_state.horizon_roles = horizon_roles
                    print(f"✅ Loaded horizon roles from database for user {user_id} (no cache fallback)")
                else:
                    print(f"ℹ️ No horizon roles found in database for user {user_id}")
            except Exception as db_error:
                print(f"⚠️ Error loading horizon roles from DB for user {user_id}: {db_error}")
        
        # NO fallback to old cached data - if not in DB, horizon_roles remains None
        
        if horizon_roles:
            st.subheader("🚀 Horizon Roles (Strategic Next Steps)")
            
            for idx, role_info in enumerate(horizon_roles, 1):
                if isinstance(role_info, dict):
                    role_title = role_info.get('role', 'Unknown Role')
                    gap_analysis = role_info.get('gap_analysis', 'Gap analysis not available')
                    rationale = role_info.get('rationale', 'Rationale not available')
                    
                    with st.expander(f"{idx}. {role_title}", expanded=(idx == 1)):
                        st.markdown(f"**Rationale:** {rationale}")
                        st.markdown("---")
                        st.markdown(f"**Gap Analysis:** {gap_analysis}")
                else:
                    # Fallback if role_info is just a string
                    st.markdown(f"{idx}. {role_info}")
        else:
            st.info("👤 Upload your CV to generate Horizon Roles with gap analysis.")
        
        st.divider()
        
        # Professional DNA Section
        st.header("🧬 Professional DNA")
        
        # Load preferences for Professional DNA
        professional_dna = preferences.get('professional_dna', {})
        
        # Career DNA Visualization with Helix Animation
        if 'digital_persona' in st.session_state and st.session_state.digital_persona:
            latent_capabilities = st.session_state.digital_persona.get('latent_capabilities', [])
            dna_html = render_dna_helix_visualization(latent_capabilities)
            st.markdown(dna_html, unsafe_allow_html=True)
        
        # Professional DNA UI: Display Industry Focus that AI identified
        if 'digital_persona' in st.session_state and st.session_state.digital_persona:
            industry_focus = st.session_state.digital_persona.get('industry_focus', 'Not yet identified')
            st.subheader("🎯 AI-Identified Industry Focus")
            st.info(f"**Current Focus:** {industry_focus}")
            
            # Add 'Update Focus' button to manually refine
            if st.button("✏️ Update Focus", key="update_industry_focus_button"):
                st.session_state.show_industry_focus_input = True
            
            if st.session_state.get('show_industry_focus_input', False):
                new_industry_focus = st.text_input(
                    "Enter your preferred industry focus:",
                    value=industry_focus,
                    key="industry_focus_input",
                    help="Examples: 'Fintech and Digital Payments Systems', 'E-commerce and Retail Tech', 'SaaS and B2B Platforms'"
                )
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("💾 Save", key="save_industry_focus"):
                        # Update digital persona
                        if 'digital_persona' in st.session_state:
                            st.session_state.digital_persona['industry_focus'] = new_industry_focus
                        # Save to preferences
                        preferences['user_identity']['industry_focus'] = new_industry_focus
                        save_preferences(preferences)
                        st.session_state.show_industry_focus_input = False
                        st.success(f"✅ Industry Focus updated to: {new_industry_focus}")
                        st.rerun()
                with col_cancel:
                    if st.button("❌ Cancel", key="cancel_industry_focus"):
                        st.session_state.show_industry_focus_input = False
                        st.rerun()
        
        st.divider()
        
        # Target Industries multiselect
        available_industries = ['Retail', 'Fintech', 'SaaS', 'Cyber', 'E-commerce', 'Healthcare Tech', 'EdTech', 'PropTech', 'Gaming', 'Media Tech']
        default_industries = professional_dna.get('target_industries', [])
        target_industries = st.multiselect(
            "Target Industries",
            options=available_industries,
            default=default_industries,
            help="Select industries you're interested in. The AI will prioritize jobs in these industries.",
            key="target_industries_sidebar"
        )
        
        # Custom Skills/Keywords text area
        custom_skills = st.text_area(
            "Custom Skills/Keywords",
            value=professional_dna.get('custom_skills', ''),
            help="Enter specific skills or keywords that are important to you (comma-separated or one per line).",
            key="custom_skills_sidebar",
            height=100
        )
        
        # Save Professional DNA to preferences.json
        if st.button("💾 Save Professional DNA", key="save_professional_dna"):
            preferences['professional_dna'] = {
                'target_industries': target_industries,
                'custom_skills': custom_skills
            }
            save_preferences(preferences)
            st.success("✅ Professional DNA saved!")
            st.rerun()
        
        st.divider()

        # Match Sensitivity Mechanism
        st.header("🎚️ Match Sensitivity")
        
        # Initialize threshold in session state if not exists
        # Default minimum display score: 60% (was previously treated as ~85% in some flows)
        try:
            # Prefer persisted admin/user preference if available (admin_console can change this)
            preferences = load_preferences()
            persisted_threshold = preferences.get('user_identity', {}).get('match_threshold', 60)
            persisted_threshold = int(persisted_threshold) if persisted_threshold is not None else 60
        except Exception:
            persisted_threshold = 60

        # Sync session_state.threshold from preferences so Admin Console changes take effect on next rerun
        if 'threshold' not in st.session_state or st.session_state.threshold != persisted_threshold:
            st.session_state.threshold = persisted_threshold
        
        # Threshold Slider: Match Threshold (%)
        threshold = st.slider(
            "Match Threshold (%)",
            min_value=0,
            max_value=100,
            value=st.session_state.threshold,
            help="Jobs below this match score will be moved to 'Auto-hidden' section. Lower threshold shows more jobs.",
            key="threshold_slider"
        )
        st.session_state.threshold = threshold
        # Persist immediately (Active Engine Rule)
        try:
            preferences = load_preferences()
            preferences.setdefault('user_identity', {})
            preferences['user_identity']['match_threshold'] = int(threshold)
            save_preferences(preferences, preserve_user_settings=True)
        except Exception:
            pass
        
        # Pivot Mode Toggle (Styled and Visible)
        st.divider()
        try:
            preferences = load_preferences()
            pivot_mode = preferences.get('user_identity', {}).get('pivot_mode', False)
        except Exception:
            pivot_mode = False
        
        pivot_mode_enabled = st.checkbox(
            "🔀 Pivot Mode: Search by Skills (Not Just Titles)",
            value=pivot_mode,
            help="When enabled, the system searches for jobs based on your skills and core competencies, not just job titles. This enables cross-industry matching.",
            key="pivot_mode_toggle"
        )
        
        if pivot_mode_enabled != pivot_mode:
            try:
                preferences = load_preferences()
                preferences.setdefault('user_identity', {})
                preferences['user_identity']['pivot_mode'] = pivot_mode_enabled
                save_preferences(preferences, preserve_user_settings=True)
                st.success("✅ Pivot Mode updated!")
            except Exception:
                pass
        st.caption(f"Current threshold: {threshold}%")
        
        # Strictness Mode: Strict Industry Match toggle
        if 'strict_industry_match' not in st.session_state:
            st.session_state.strict_industry_match = True
        
        strict_industry_match = st.toggle(
            "Strict Industry Match",
            value=st.session_state.strict_industry_match,
            help="If ON: Aggressive filtering for industry match. If OFF: Flexible matching prioritizes leadership skills over industry keywords.",
            key="strict_industry_match_toggle"
        )
        st.session_state.strict_industry_match = strict_industry_match
        # Persist immediately (Active Engine Rule)
        try:
            preferences = load_preferences()
            preferences.setdefault('user_identity', {})
            preferences['user_identity']['strict_industry_match'] = bool(strict_industry_match)
            save_preferences(preferences, preserve_user_settings=True)
        except Exception:
            pass
        
        if strict_industry_match:
            st.info("🔒 **Strict Mode:** Industry matching is aggressive. Jobs must match your industry focus.")
        else:
            st.info("🔓 **Flexible Mode:** Leadership skills prioritized. Industry differences are acceptable for tech roles.")
        
        st.divider()

        # Debug Mode (Temporary): show everything in UI, even 0% score, to understand filtering
        st.header("🧪 Debug Mode")
        if 'debug_mode' not in st.session_state:
            st.session_state.debug_mode = False
        debug_mode = st.toggle(
            "Debug Mode (show all jobs, even 0%)",
            value=st.session_state.debug_mode,
            help="When ON, Persona shows every job found and disables score-based hiding so you can see what's being filtered.",
            key="debug_mode_toggle"
        )
        st.session_state.debug_mode = debug_mode
        if debug_mode:
            st.info("🧪 Debug Mode is ON: filtering is disabled and low-score jobs will still render.")

        st.divider()

        # Restore Skills DNA: Full Skills Management section in Sidebar
        st.sidebar.subheader("🎯 Skill DNA")
        
        # Load preferences for skills
        from utils import load_preferences, save_preferences
        preferences = load_preferences()
        user_identity = preferences.get('user_identity', {})
        added_skills = user_identity.get('added_skills', [])
        blacklisted_skills = user_identity.get('blacklisted_skills', [])
        
        # Initialize if not exists
        if 'added_skills' not in user_identity:
            user_identity['added_skills'] = []
        if 'blacklisted_skills' not in user_identity:
            user_identity['blacklisted_skills'] = []
        
        # Add new skill text input
        new_skill_input = st.sidebar.text_input(
            "Add Skill",
            key="new_skill_input_sidebar",
            help="Enter a skill to add to your profile. It will boost match scores for jobs requiring this skill."
        )
        if st.sidebar.button("➕ Add", key="add_skill_sidebar_button"):
            if new_skill_input and new_skill_input.strip():
                skill = new_skill_input.strip()
                if skill not in added_skills and skill not in blacklisted_skills:
                    added_skills.append(skill)
                    user_identity['added_skills'] = added_skills
                    preferences['user_identity'] = user_identity
                    save_preferences(preferences)
                    # Update session state
                    st.session_state.my_skill_bucket = added_skills.copy()
                    st.sidebar.success(f"✅ Added: {skill}")
                    st.rerun()
                else:
                    st.sidebar.warning(f"⚠️ Skill '{skill}' already exists.")
        
        # Display Active Skills
        st.sidebar.caption("**Active Skills:**")
        if added_skills:
            for skill in added_skills:
                col_skill, col_move = st.sidebar.columns([3, 1])
                with col_skill:
                    st.sidebar.write(f"• {skill}")
                with col_move:
                    if st.sidebar.button("🗑️", key=f"move_to_trash_sidebar_{skill}", help="Move to Trash/Blacklist"):
                        # Move skill from added_skills to blacklisted_skills
                        added_skills.remove(skill)
                        if skill not in blacklisted_skills:
                            blacklisted_skills.append(skill)
                        user_identity['added_skills'] = added_skills
                        user_identity['blacklisted_skills'] = blacklisted_skills
                        preferences['user_identity'] = user_identity
                        save_preferences(preferences)
                        # Update session state
                        st.session_state.my_skill_bucket = added_skills.copy()
                        # Update Digital Persona immediately
                        if st.session_state.get('digital_persona'):
                            # Remove skill from persona tech_stack if present
                            tech_stack = st.session_state.digital_persona.get('tech_stack', [])
                            if skill in tech_stack:
                                tech_stack.remove(skill)
                                st.session_state.digital_persona['tech_stack'] = tech_stack
                        st.sidebar.success(f"✅ Moved '{skill}' to Trash/Blacklist")
                        st.rerun()
        else:
            st.sidebar.write("_No active skills._")
        
        # Display Blacklisted/Trashed Skills
        st.sidebar.caption("**🗑️ Trash/Blacklist:**")
        if blacklisted_skills:
            st.sidebar.caption("_Jobs containing these skills will have significantly lower match scores._")
            for skill in blacklisted_skills:
                col_skill, col_restore = st.sidebar.columns([3, 1])
                with col_skill:
                    st.sidebar.write(f"• ~~{skill}~~")
                with col_restore:
                    if st.sidebar.button("↩️", key=f"restore_skill_sidebar_{skill}", help="Restore to Active Skills"):
                        # Move skill from blacklisted_skills back to added_skills
                        blacklisted_skills.remove(skill)
                        if skill not in added_skills:
                            added_skills.append(skill)
                        user_identity['added_skills'] = added_skills
                        user_identity['blacklisted_skills'] = blacklisted_skills
                        preferences['user_identity'] = user_identity
                        save_preferences(preferences)
                        # Update session state
                        st.session_state.my_skill_bucket = added_skills.copy()
                        st.sidebar.success(f"✅ Restored '{skill}' to Active Skills")
                        st.rerun()
        else:
            st.sidebar.write("_No blacklisted skills._")
        
        # Legacy Skill Bucket display (for compatibility)
        if st.session_state.my_skill_bucket:
            # Sync with added_skills
            if set(st.session_state.my_skill_bucket) != set(added_skills):
                st.session_state.my_skill_bucket = added_skills.copy()

        st.divider()
        
        # AI-Driven Role Suggestions: Suggested Roles for You
        st.header("💡 Suggested Roles for You")
        if 'suggested_roles' not in st.session_state:
            st.session_state.suggested_roles = []
        
        # Generate role suggestions if profile exists and suggestions haven't been generated
        if profile and profile.get('master_cv_text') and not st.session_state.suggested_roles:
            try:
                # Generate role suggestions using AI
                suggestions_prompt = (
                    "Based on this CV, suggest 5-7 job titles/roles that would be a good fit. "
                    "Focus on senior technology leadership roles (CTO, VP, Director, Head of). "
                    "Return ONLY a JSON array: [\"role1\", \"role2\", ...]\n\n"
                    f"CV Text:\n{profile['master_cv_text'][:2000]}"
                )
                response = engine.api_client.call_api_with_fallback(suggestions_prompt)
                from utils import parse_json_safely
                suggested_roles = parse_json_safely(response.text) or []
                if isinstance(suggested_roles, list):
                    st.session_state.suggested_roles = suggested_roles[:7]
            except Exception as e:
                print(f"Error generating role suggestions: {e}")
                st.session_state.suggested_roles = []
        
        # Display suggested roles with checkboxes
        if st.session_state.suggested_roles:
            selected_roles = []
            for role in st.session_state.suggested_roles:
                is_selected = st.checkbox(role, key=f"suggested_role_{role}", value=role in preferences.get('user_identity', {}).get('preferred_roles', []))
                if is_selected:
                    selected_roles.append(role)
            
            # Update preferences with selected roles
            if selected_roles:
                preferences['user_identity']['preferred_roles'] = list(set(preferences.get('user_identity', {}).get('preferred_roles', []) + selected_roles))
                save_preferences(preferences)
        else:
            st.write("_Upload a CV to see suggested roles._")
        
        st.divider()
        
        # Visual Identity Summary: Profile Strength / Identity Map
        st.header("🎯 Profile Strength")
        if profile and profile.get('master_cv_text'):
            try:
                # Extract core pillars from Digital Persona
                if st.session_state.get('digital_persona'):
                    persona = st.session_state.digital_persona
                    st.write("**Core Pillars:**")
                    
                    # Role Level
                    role_level = persona.get('role_level', 'Senior')
                    st.write(f"• **Role Level:** {role_level}")
                    
                    # Industry Focus
                    industry = persona.get('industry_focus', 'Technology')
                    st.write(f"• **Industry Focus:** {industry}")
                    
                    # Tech Stack (top 5)
                    tech_stack = persona.get('tech_stack', [])[:5]
                    if tech_stack:
                        st.write(f"• **Key Technologies:** {', '.join(tech_stack)}")
                    
                    # Leadership Style
                    leadership = persona.get('leadership_style', 'Technical Leadership')
                    st.write(f"• **Leadership Style:** {leadership}")
                else:
                    st.write("_Digital Persona not yet generated. Upload a CV first._")
            except Exception as e:
                st.write("_Profile analysis pending..._")
        else:
            st.write("_Upload a CV to see your Profile Strength._")
        
        st.divider()
        
        # Show All Jobs toggle in sidebar - Make it more prominent
        st.divider()
        st.header("⚙️ Display Options")
        # Emergency Visibility: Make show_all_jobs toggle more prominent
        show_all_jobs = st.checkbox(
            '🔓 **Show ALL Found Jobs (Ignore Filters)**',
            value=st.session_state.show_all_jobs,
            key="show_all_jobs_sidebar",
            help="Turn this ON to see all jobs regardless of match score. Useful if jobs are being filtered out."
        )
        st.session_state.show_all_jobs = show_all_jobs
        if show_all_jobs:
            st.success("✅ **All jobs will be displayed, ignoring match score filters.**")
        else:
            st.info("ℹ️ Jobs are filtered by match score threshold.")
        
        st.divider()
        
        # Global Search Status: Visual status indicator
        st.header("📊 Global Search Status")
        
        # AI Model Status
        model_status = st.session_state.get('active_model', 'gemini-1.5-flash')
        st.write(f"**Active AI Model:** `{model_status}`")
        if model_status == 'gemini-1.5-flash':
            st.success("✅ Primary model active")
        elif model_status == 'gemini-pro':
            st.info("ℹ️ Using fallback model")
        else:
            st.warning("⚠️ Model status unknown")
        
        # Scraper Status
        scraper_status = st.session_state.get('scraper_status', {})
        st.write("**Scraper Status:**")
        for scraper_name, status_info in scraper_status.items():
            status = status_info.get('status', 'idle')
            if status == 'success':
                st.write(f"✅ {scraper_name.title()}: Success")
            elif status == 'failed':
                st.write(f"❌ {scraper_name.title()}: Failed")
            elif status == 'running':
                st.write(f"⏳ {scraper_name.title()}: Running...")
            else:
                st.write(f"⚪ {scraper_name.title()}: Idle")
        
        st.divider()
        
        # Agent Source Network: Display current target domains
        st.header("🌐 Agent Source Network")
        source_domains = [
            "linkedin.com/jobs",
            "indeed.com",
            "alljobs.co.il",
            "drushim.co.il",
            "jobmaster.co.il"
        ]
        for domain in source_domains:
            st.write(f"• {domain}")
        
        st.divider()
        
        # Strategy Preview: Display Search Strategy for user approval
        st.header("🎯 Search Strategy Preview")
        if st.session_state.optimized_queries:
            st.write("**Generated Search Queries:**")
            for i, query in enumerate(st.session_state.optimized_queries[:5], 1):
                st.write(f"{i}. `{query}`")
        else:
            st.write("_No strategy generated yet. Click 'Find Jobs' to generate._")
        
        st.divider()
        
        # Task 3: Integration - Autonomous Agent Control (Pause/Resume Buttons)
        st.header("🚀 Autonomous Agent Control")
        
        col_pause, col_resume = st.columns(2)
        with col_pause:
            if st.button('⏸️ השהה חיפוש', key='pause_hunting', disabled=not st.session_state.get('hunting_active', False)):
                st.session_state.hunting_active = False
                # Terminate background scout process if running
                if 'scout_process' in st.session_state and st.session_state.scout_process is not None:
                    try:
                        st.session_state.scout_process.terminate()
                        st.session_state.scout_process.wait(timeout=5)
                        print(f"✅ Background scout process terminated (PID: {st.session_state.scout_process.pid})")
                    except subprocess.TimeoutExpired:
                        st.session_state.scout_process.kill()
                        print(f"⚠️ Background scout process force-killed (PID: {st.session_state.scout_process.pid})")
                    finally:
                        st.session_state.scout_process = None
                st.rerun()
        with col_resume:
            if st.button('▶️ חדוש חיפוש', key='resume_hunting', disabled=st.session_state.get('hunting_active', False)):
                st.session_state.hunting_active = True
                # Launch background scout process if not running
                if 'scout_process' not in st.session_state or st.session_state.scout_process is None:
                    try:
                        st.session_state.scout_process = subprocess.Popen(
                            ['python', 'background_scout.py'],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                        print(f"✅ Background scout process started (PID: {st.session_state.scout_process.pid})")
                    except Exception as e:
                        st.error(f"❌ Error launching background scout: {e}")
                        print(f"❌ Error launching background scout: {e}")
                        st.session_state.hunting_active = False
                st.rerun()
        
        # Show current status
        if st.session_state.get('hunting_active', False):
            st.success("✅ חיפוש פעיל")
        else:
            st.info("⏸️ חיפוש מושהה")
        
        st.divider()
        
        # Task 3: Integration - Live Monitor (Agent Live Activity)
        with st.sidebar.expander("🕵️ Agent Live Activity", expanded=True):
            # Read and display last 10 lines from scout_logs.json
            # Note: background_scout.py writes to scout_logs.json (JSON format)
            # This reads the JSON file and displays the last 10 entries as formatted text lines
            try:
                scout_logs_file = 'scout_logs.json'
                if os.path.exists(scout_logs_file):
                    with open(scout_logs_file, 'r', encoding='utf-8') as f:
                        logs = json.load(f)
                        # Get last 10 log entries (user requested 10 lines)
                        last_logs = logs[-10:] if len(logs) > 10 else logs
                        
                        # Display logs (newest first for better visibility)
                        log_display = []
                        for log_entry in reversed(last_logs):
                            timestamp = log_entry.get('timestamp', '')
                            # Format timestamp (remove microseconds if present)
                            if 'T' in timestamp:
                                timestamp = timestamp.split('T')[1].split('.')[0] if '.' in timestamp else timestamp.split('T')[1]
                            log_type = log_entry.get('type', 'info')
                            message = log_entry.get('message', '')
                            
                            # Color code by type
                            if log_type == 'success':
                                log_display.append(f"✅ `[{timestamp}]` {message}")
                            elif log_type == 'warning':
                                log_display.append(f"⚠️ `[{timestamp}]` {message}")
                            elif log_type == 'error':
                                log_display.append(f"❌ `[{timestamp}]` {message}")
                            else:
                                log_display.append(f"ℹ️ `[{timestamp}]` {message}")
                        
                        if log_display:
                            st.markdown('\n\n'.join(log_display))
                        else:
                            st.info("No activity logs yet. Start Autonomous Hunting Mode to see activity.")
                else:
                    st.info("No activity logs yet. Start Autonomous Hunting Mode to see activity.")
            except json.JSONDecodeError as e:
                st.warning(f"Log file format error: {e}")
            except Exception as e:
                st.error(f"Error reading logs: {e}")
        
        st.divider()
        
        # Blacklist management in sidebar
        st.header("🗑️ Job Management")
        blacklist = load_blacklist()
        st.write(f"**Blacklisted:** {len(blacklist['urls']) + len(blacklist['titles'])} jobs")
        if st.button("Clear Blacklist", key="clear_blacklist"):
            save_blacklist({"urls": [], "titles": []})
            st.success("Blacklist cleared!")
            st.rerun()
        
        st.divider()
        
        # Visual Debugger: System Health expander at bottom of sidebar
        with st.expander('🛠️ System Health', expanded=False):
            try:
                health_status = check_system_integrity()
                
                # API Client Status
                api_status = health_status.get('api_client', {})
                api_status_val = api_status.get('status', 'unknown')
                if api_status_val == 'healthy':
                    st.success(f"✅ **API Client:** {api_status.get('message', 'Operational')}")
                elif api_status_val == 'warning':
                    st.warning(f"⚠️ **API Client:** {api_status.get('message', 'Warning')}")
                else:
                    st.error(f"❌ **API Client:** {api_status.get('message', 'Error')}")
                
                # Session State Status
                session_status = health_status.get('session_state', {})
                session_status_val = session_status.get('status', 'unknown')
                if session_status_val == 'healthy':
                    st.success(f"✅ **Session State:** {session_status.get('message', 'All keys initialized')}")
                elif session_status_val == 'warning':
                    st.warning(f"⚠️ **Session State:** {session_status.get('message', 'Warning')}")
                else:
                    st.error(f"❌ **Session State:** {session_status.get('message', 'Error')}")
                
                # Persona Engine Status
                engine_status = health_status.get('persona_engine', {})
                engine_status_val = engine_status.get('status', 'unknown')
                if engine_status_val == 'healthy':
                    st.success(f"✅ **Persona Engine:** {engine_status.get('message', 'Operational')}")
                elif engine_status_val == 'warning':
                    st.warning(f"⚠️ **Persona Engine:** {engine_status.get('message', 'Warning')}")
                else:
                    st.error(f"❌ **Persona Engine:** {engine_status.get('message', 'Error')}")
                
                # Timestamp
                if api_status.get('timestamp'):
                    st.caption(f"Last check: {api_status.get('timestamp', 'N/A')}")
            except Exception as e:
                st.error(f"❌ System Health Check Error: {str(e)[:100]}")
    
    return must_have_keywords, exclude_keywords

def render_job_list(engine, pdf_generator, profile, filtered_by_persona):
    """
    Renders the complete job list with all expanders, skill buckets, job dossiers, and action buttons.
    Handles both normal jobs and empty analysis fallback display.
    """
    # Debug: Check if found_jobs exists and has data
    if 'found_jobs' not in st.session_state:
        st.warning("⚠️ Debug: st.session_state.found_jobs does not exist")
        return
    
    if not st.session_state.found_jobs:
        st.warning("⚠️ Debug: st.session_state.found_jobs is empty")
        return
    
    # Debug line: Show how many jobs we're rendering
    st.write(f'🔍 **Debug: Rendering {len(st.session_state.found_jobs)} jobs**')
    
    # Smart Re-ordering: sort by score descending so upgraded jobs bubble to the top
    def _score_of(item):
        try:
            a = item[3] if len(item) > 3 else {}
            if not isinstance(a, dict):
                return 0
            s = a.get("match_score", a.get("score", 0))
            return int(float(s)) if s is not None else 0
        except Exception:
            return 0

    sorted_jobs = sorted(list(st.session_state.found_jobs), key=_score_of, reverse=True)

    # Split into sections
    recommended = [it for it in sorted_jobs if _score_of(it) > 80]
    basic = [it for it in sorted_jobs if _score_of(it) == 70]
    other = [it for it in sorted_jobs if it not in recommended and it not in basic]

    if recommended:
        st.subheader("✨ Recommended (Top Choices)")
    for index, job, job_key, analysis in recommended:
        # Render via existing logic below
        pass

    if basic:
        st.subheader("⚡ Basic Matches")
    for index, job, job_key, analysis in basic:
        pass

    if other:
        st.subheader("📋 Other Matches")
    for index, job, job_key, analysis in other:
        pass

    # Flatten back in desired order and render
    render_order = recommended + basic + other
    for index, job, job_key, analysis in render_order:
        # FORCE DISPLAY: Always render - NO conditional check, just render every job
        # Do NOT check for job.get('analysis') - render immediately
        # Force UI Display: Don't wait for analysis to be a dict - render immediately
        # Safely access analysis - ensure it's a dict, but don't block rendering
        if not isinstance(analysis, dict):
            analysis = {}
        
        # Force UI Display: If analysis is empty or failed, create fallback display immediately
        # Check for ERROR_404 or empty analysis
        # UI Robustness: Handle both old format (score, reasoning) and new format (match_score, explanation)
        is_error_404 = analysis.get('error_code') == 'ERROR_404' or 'ERROR_404' in str(analysis.get('error', ''))
        
        # Check for placeholder analysis (has explanation key indicating API error)
        is_placeholder = 'explanation' in analysis and 'AI Analysis Pending' in str(analysis.get('explanation', ''))
        
        # Check if analysis is empty - support both old and new formats
        has_old_format = analysis.get('score') is not None or analysis.get('reasoning')
        has_new_format = analysis.get('match_score') is not None or analysis.get('explanation')
        is_empty_analysis = not analysis or len(analysis) == 0 or (not has_old_format and not has_new_format)
        
        # Get score from either format
        # Fix Rendering: match_score defaults to 0 if missing
        score = analysis.get('score') or analysis.get('match_score', 0)
        if score is None:
            score = 0  # Default to 0 if empty
        
        needs_manual_review = analysis.get('needs_manual_review', False) or is_empty_analysis or is_placeholder
        waiting_for_ai = analysis.get('waiting_for_ai', False)
        
        # Immediate Visibility: If analysis is empty, ERROR_404, or placeholder, show appropriate label
        # UI Robustness: Handle placeholder analysis gracefully
        if is_error_404 or is_placeholder:
            match_label = "[AI Temporarily Unavailable]"
        elif is_empty_analysis or waiting_for_ai:
            match_label = "[Pending AI]"
        else:
            # Dynamic Explanation: Show badge if job passes threshold
            debug_mode = bool(st.session_state.get('debug_mode', False))
            threshold = 0 if debug_mode else st.session_state.get('threshold', 60)
            if score >= threshold:
                match_label = f"⭐ [{score}% Match] ✅ Passes your {threshold}% bar"
            else:
                match_label = f"⭐ [{score}% Match] ⚠️ Below your {threshold}% bar"
            if needs_manual_review:
                match_label = f"⚠️ [{score}% Match - Needs Manual Review]"

        # Visual Evolution Labels
        if score == 70:
            match_label = f"⚡ Basic Match | {match_label}"
        elif score > 80:
            match_label = f"✨ Top Choice | {match_label}"

        # Career Horizon: visual indicator when additive bonus was applied
        try:
            ch_bonus = int(float(analysis.get("career_horizon_bonus_points", 0) or 0))
        except Exception:
            ch_bonus = 0
        if ch_bonus > 0:
            match_label = f"🔀 Pivot Opportunity (+{ch_bonus}) | {match_label}"
        
        # Expander Integrity: Use proper format with company and role
        # Immediate Visibility: Show appropriate label when analysis is empty or ERROR_404
        # FORCE DISPLAY: Create st.expander for EVERY job - no conditional check
        # Prevent Duplicate Applications: Mark clearly if already applied
        company_name = job.get('company', 'Unknown')
        role_title = job.get('role', job.get('title', 'Unknown Role'))  # Try 'role' first, fallback to 'title'
        
        # Check if already applied (shouldn't appear in main list, but safety check)
        if analysis.get('already_applied', False):
            match_label = "⚠️ [Already Applied]"
        
        # Custom HTML Job Card (Hybrid Approach)
        # Render the visual card as HTML, but keep Streamlit buttons for functionality
        if is_error_404 or is_placeholder or is_empty_analysis or waiting_for_ai:
            # For jobs without analysis, show simplified card
            card_html = f"""
            <div class="custom-job-card">
                <div class="job-card-header">
                    <div class="match-gauge-container">
                        <div class="gauge-low">
                            {create_circular_gauge_svg(0)}
                        </div>
                        <div style="flex: 1;">
                            <h3 class="job-title">{role_title}</h3>
                            <p class="job-company">{company_name}</p>
                        </div>
                    </div>
                </div>
                <div style="color: #8B949E; font-size: 14px; padding: 12px; background: #0B0E11; border-radius: 8px; margin: 12px 0;">
                    ⏳ Waiting for AI analysis...
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)
        else:
            # Render custom HTML card for analyzed jobs
            card_html = render_custom_job_card(job, analysis, job_key, index, score, company_name, role_title)
            st.markdown(card_html, unsafe_allow_html=True)
        
        # Use Streamlit container for expandable details (maintains all existing logic)
        with st.expander("📋 View Details", expanded=False):
            
            if ch_bonus > 0:
                try:
                    ch_score = float(analysis.get("career_horizon_score", 0.0) or 0.0)
                except Exception:
                    ch_score = 0.0
                st.info(f"🔀 **Pivot Opportunity:** Career Horizon bonus applied (+{ch_bonus} points, horizon_score={ch_score:.2f}).")
            # Hook display for Top Choice
            if score > 80:
                hook = (analysis.get("hook") or "").strip()
                if hook:
                    st.markdown(f"**Hook:** {hook}")
            # FORCE DISPLAY: If AI analysis failed (empty dict), ERROR_404, or placeholder, display raw job data immediately
            # UI Fallback: Show raw description for ERROR_404, placeholder, or empty analysis
            # UI Robustness: Handle placeholder analysis with match_score/explanation keys
            # Analyze Job button visibility rule:
            # If a job came from discovered_jobs.csv but has no score yet (waiting_for_ai),
            # we treat it like a pending/empty analysis so the Analyze button is clearly visible.
            if is_error_404 or is_placeholder or is_empty_analysis or waiting_for_ai:
                st.subheader("📄 Raw Job Information (AI Analysis Temporarily Unavailable)")
                st.write(f"**Company:** {company_name}")
                st.write(f"**Role:** {role_title}")
                job_url = job.get('job_url', '#')
                if job_url and job_url != '#':
                    st.write(f"**Job URL:** [{job_url}]({job_url})")
                
                # UI Fallback: Display full job description (up to 1000 chars) when AI fails
                job_description = job.get('description', job.get('job_description', 'No description available'))
                
                # Show explanation from placeholder analysis if available
                # Fix Rendering: explanation defaults to 'Raw Data - AI Offline' if missing
                explanation = analysis.get('explanation') or analysis.get('reasoning', 'Raw Data - AI Offline')
                st.warning(f"⚠️ {explanation}. Showing raw description.")
                st.info(f"**Job Description:**\n\n{job_description[:1000]}{'...' if len(job_description) > 1000 else ''}")
                
                if is_error_404 or is_placeholder:
                    error_msg = analysis.get('error', 'API Error')
                    st.info(f"💡 **Note:** {error_msg}. This is usually temporary. The job is still available for manual review.")
                st.divider()
                
                # Manual Analysis Button: AI calls happen ONLY on click (rate-limit shield)
                col1, col2, col3 = st.columns(3)
                with col1:
                    persona_ok = bool(st.session_state.get("digital_persona")) and bool(profile.get("master_cv_text"))
                    if not persona_ok:
                        st.info("ℹ️ Please upload/initialize your CV first.")
                    if st.button("🔍 Analyze Job", key=f"analyze_raw_{job_key}", disabled=(not persona_ok)):
                        try:
                            # Cost Efficiency: avoid redundant spending
                            existing = st.session_state.job_analyses.get(job_key, {})
                            existing_score = 0
                            try:
                                existing_score = int(float(existing.get("match_score", existing.get("score", 0)) or 0))
                            except Exception:
                                existing_score = 0
                            if existing and existing_score > 0 and not existing.get("waiting_for_ai", False):
                                st.info(f"💾 Already analyzed (score={existing_score}%). No new API call made.")
                                # Do not re-run analysis; keep rendering
                                raise StopIteration("already_analyzed")

                            user_learnings = load_user_learnings()
                            master_profile = engine.build_master_search_profile(
                                profile.get('master_cv_text', ''),
                                skill_bucket=st.session_state.get('my_skill_bucket', []),
                                rejection_learnings=user_learnings
                            )
                            result = engine.analyze_match(
                                job.get('description', ''),
                                profile.get('master_cv_text', ''),
                                skill_bucket=st.session_state.get('my_skill_bucket', []),
                                master_profile=master_profile,
                                digital_persona=st.session_state.digital_persona,
                                job_url=job.get('job_url', ''),
                                job_title=job.get('title', role_title)
                            )
                            st.session_state.job_analyses[job_key] = result if isinstance(result, dict) else {"match_score": 0, "explanation": "Analysis returned non-dict"}
                            st.session_state.jobs_analyzed.add(job_key)
                            st.success("✅ Analysis complete.")
                            st.rerun()
                        except StopIteration:
                            pass
                        except Exception as e:
                            st.error(f"❌ Analysis failed: {e}")
                            st.exception(e)
                
                # Still show apply button even if analysis failed
                with col2:
                    if st.button(f"🚀 Apply with AI Bot", key=f"apply_raw_{index}", disabled=(not persona_ok)):
                        with st.status("📝 **יוצר טיוטה מותאמת...**", expanded=True) as draft_status:
                            try:
                                draft_status.update(label="🤖 מנתח משרה עם Gemini AI...")
                                user_learnings = load_user_learnings()
                                master_profile = engine.build_master_search_profile(
                                    profile['master_cv_text'],
                                    skill_bucket=st.session_state.my_skill_bucket,
                                    rejection_learnings=user_learnings
                                )
                                # Cover Letter Guard: Validate result before storing
                                cover_letter_result = engine.reframing_analysis(
                                    job.get('description', ''), 
                                    profile['master_cv_text'], 
                                    skill_bucket=st.session_state.my_skill_bucket,
                                    master_profile=master_profile,
                                    digital_persona=st.session_state.digital_persona
                                )
                                # Soft Traits Injection (Writing-only): enrich tone without changing facts
                                try:
                                    from utils import detect_language
                                    lang = detect_language(job.get('description', ''))
                                    cover_letter_result = pdf_generator.inject_soft_traits_into_cover_letter(
                                        cover_letter_result, language=lang
                                    )
                                except Exception:
                                    pass
                                # Validation: Ensure cover letter is not None
                                if cover_letter_result and isinstance(cover_letter_result, str) and len(cover_letter_result) > 0:
                                    st.session_state.current_draft = cover_letter_result
                                else:
                                    # Fallback: Generate basic cover letter
                                    from utils import detect_language
                                    job_lang = detect_language(job.get('description', ''))
                                    st.session_state.current_draft = engine._generate_fallback_cover_letter(
                                        job.get('description', ''),
                                        profile['master_cv_text'],
                                        job_lang
                                    )
                                st.session_state.selected_job = job.to_dict() if hasattr(job, 'to_dict') else dict(job)
                                draft_status.update(label="✅ טיוטה מוכנה!", state="complete")
                                st.rerun()
                            except Exception as e:
                                draft_status.update(label=f"❌ שגיאה: {e}", state="error")
                                st.error(f"שגיאה ביצירת טיוטה: {e}")
                                import traceback
                                print(f"ERROR on job draft for {role_title}: {e}\n{traceback.format_exc()}")
                with col3:
                    if st.button(f"🗑️ Not Interested", key=f"blacklist_raw_{index}"):
                        add_to_blacklist(job.get('job_url', ''), job.get('title', ''))
                        st.success(f"Job blacklisted: {role_title}")
                        st.rerun()
                
                continue  # Skip to next job - don't process normal display logic
            
            # Normal display logic for jobs with analysis
            # Manual Analysis Mode: do NOT run AI automatically inside the job loop.
            # Everything is behind explicit button clicks to avoid rate limits.
            action_col1, action_col2, action_col3 = st.columns(3)
            with action_col1:
                persona_ok = bool(st.session_state.get("digital_persona")) and bool(profile.get("master_cv_text"))
                if st.button("🔍 Re-Analyze Job", key=f"reanalyze_{job_key}", disabled=(not persona_ok)):
                    try:
                        # Cost Efficiency: avoid redundant spending unless user explicitly re-analyzes
                        # (Re-Analyze button is explicit; we still allow the call.)
                        user_learnings = load_user_learnings()
                        master_profile = engine.build_master_search_profile(
                            profile.get('master_cv_text', ''),
                            skill_bucket=st.session_state.get('my_skill_bucket', []),
                            rejection_learnings=user_learnings
                        )
                        result = engine.analyze_match(
                            job.get('description', ''),
                            profile.get('master_cv_text', ''),
                            skill_bucket=st.session_state.get('my_skill_bucket', []),
                            master_profile=master_profile,
                            digital_persona=st.session_state.digital_persona,
                            job_url=job.get('job_url', ''),
                            job_title=job.get('title', role_title)
                        )
                        st.session_state.job_analyses[job_key] = result if isinstance(result, dict) else {"match_score": 0, "explanation": "Analysis returned non-dict"}
                        st.session_state.jobs_analyzed.add(job_key)
                        st.success("✅ Analysis updated.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Re-analysis failed: {e}")
                        st.exception(e)
            with action_col2:
                if st.button("🧩 Extract Top Skills", key=f"extract_skills_{job_key}", disabled=(not persona_ok)):
                    try:
                        top_skills = engine.extract_top_skills(job.get('description', ''), cv_text=profile.get('master_cv_text', ''))
                        st.session_state.job_top_skills[job_key] = top_skills if isinstance(top_skills, list) else []
                        st.success("✅ Skills extracted.")
                        st.rerun()
                    except Exception as e:
                        st.session_state.job_top_skills[job_key] = []
                        st.error(f"❌ Skill extraction failed: {e}")
                        st.exception(e)
            with action_col3:
                if st.button("📑 Generate Job Dossier", key=f"generate_dossier_{job_key}", disabled=(not persona_ok)):
                    try:
                        dossier = engine.job_dossier(job.get('description', ''), profile.get('master_cv_text', ''), digital_persona=st.session_state.digital_persona)
                        st.session_state.job_dossiers[job_key] = dossier if isinstance(dossier, dict) else {}
                        st.success("✅ Dossier generated.")
                        st.rerun()
                    except Exception as e:
                        st.session_state.job_dossiers[job_key] = {}
                        st.error(f"❌ Dossier generation failed: {e}")
                        st.exception(e)

            top_skills = st.session_state.job_top_skills.get(job_key, [])

            # Skill Bucket Feature: Display skills as buttons/tags
            if top_skills:
                st.subheader("🎯 Key Skills")
                skill_cols = st.columns(len(top_skills))
                for idx, skill in enumerate(top_skills):
                    with skill_cols[idx]:
                        if st.button(f"+ {skill}", key=f"skill_{job_key}_{idx}", help=f"Add '{skill}' to your Skill Bucket"):
                            if skill not in st.session_state.my_skill_bucket:
                                st.session_state.my_skill_bucket.append(skill)
                                # Skill Augmentation: Add to preferences.json user_identity['added_skills']
                                add_skill_to_preferences(skill, user_id=get_user_id())
                                st.success(f"Added '{skill}' to Skill Bucket!")
                                st.rerun()
                            else:
                                st.info(f"'{skill}' is already in your Skill Bucket")
            st.divider()

            # Comprehensive Job Dossier Section
            dossier = st.session_state.job_dossiers.get(job_key, {})
            
            # Fallback Mechanism: If job_dossier or analysis is missing/empty, show Raw Description
            if not analysis:
                st.subheader("📄 Raw Description")
                # Fix the Missing Content: Use st.info with job description as guaranteed fallback
                job_description = job.get('description', job.get('job_description', 'No description available'))
                # Force UI Display: Always show description using st.info as guaranteed fallback
                st.info(f"**Job Description (First 500 characters):**\n\n{job_description[:500]}{'...' if len(job_description) > 500 else ''}")
                st.divider()
            else:
                # Conditional Rendering: Only display sections if data exists and is not empty
                st.subheader("📋 Job Dossier")
            
                # Role Essence - only if not empty
                role_essence = dossier.get('role_essence', '').strip()
                if role_essence and role_essence not in ['Loading...', 'Analysis unavailable', 'No summary available']:
                    st.write(f"**Role Essence:** {role_essence}")
                
                # Technical Skills - only if list is not empty
                tech_stack = dossier.get('tech_stack', [])
                if tech_stack and isinstance(tech_stack, list) and len(tech_stack) > 0:
                    st.write(f"**Critical Tech Stack:** {', '.join(tech_stack)}")
                
                # Company Context - only if not empty
                company_context = dossier.get('company_context', '').strip()
                if company_context and company_context not in ['Loading...', 'Information unavailable']:
                    st.write(f"**Company Context:** {company_context}")
                
                # Persona Fit Analysis - only if not empty
                persona_fit = dossier.get('persona_fit_analysis', '').strip()
                if persona_fit and persona_fit not in ['Loading...', 'Analysis unavailable']:
                    st.write(f"**Persona Fit Analysis:** {persona_fit}")

                st.divider()

                # Match Analysis - use st.markdown for clear presentation
                match_reasoning = analysis.get('reasoning', '').strip()
                if match_reasoning and match_reasoning not in ['אין נימוק זמין', 'No reasoning available']:
                    st.markdown(f"**ניתוח התאמה (Match Analysis):**\n\n{match_reasoning}")
                
                # Gaps - only if list is not empty
                gaps = analysis.get('gaps', [])
                if gaps and isinstance(gaps, list) and len(gaps) > 0:
                    gaps_str = ', '.join(gaps)
                    if gaps_str.strip():
                        st.write(f"**פערים מרכזיים (Key Gaps):** {gaps_str}")
                else:
                    st.write("**פערים מרכזיים:** לא דווחו פערי מיומנויות.")
                
                job_url = job.get('job_url', '#')
                if job_url and job_url != '#':
                    st.write(f"[קישור למשרה (Job Link)]({job_url})")

            st.divider()
            
            # CV Adaptation & PDF Export: Sync & Generate Tailored PDF button
            if st.button("📄 Sync & Generate Tailored PDF", key=f"generate_pdf_{job_key}"):
                with st.status("📄 **Generating Tailored PDF...**", expanded=True) as pdf_status:
                    try:
                        pdf_status.update(label="🤖 Adapting CV for ATS optimization...")
                        # Get original CV text
                        original_cv_text = profile.get('master_cv_text', '')
                        job_description = job.get('description', '')
                        
                        # Generate tailored PDF using CV adaptation
                        tailored_pdf_path = pdf_generator.generate_tailored_pdf(
                            original_cv=original_cv_text,
                            job_description=job_description
                        )
                        
                        pdf_status.update(label="✅ Tailored PDF generated!", state="complete")
                        st.success(f"✅ Tailored PDF created: `{tailored_pdf_path}`")
                        st.info("📄 The CV has been optimized for ATS without adding false information. Review the file before submission.")
                    except Exception as e:
                        pdf_status.update(label=f"❌ Error: {e}", state="error")
                        st.error(f"Error generating tailored PDF: {e}")
                        import traceback
                        print(f"ERROR generating tailored PDF: {e}\n{traceback.format_exc()}")

            st.divider()

            # Job-to-Skill Bridge: Add buttons for hidden/low score jobs
            match_score = analysis.get('match_score', analysis.get('score', 0))
            debug_mode = bool(st.session_state.get('debug_mode', False))
            threshold = 0 if debug_mode else st.session_state.get('threshold', 60)
            is_hidden = match_score < threshold or analysis.get('is_hidden', False)
            
            if (not debug_mode) and (is_hidden or match_score < threshold):
                st.divider()
                st.subheader("🔧 Job-to-Skill Bridge")
                col_force, col_train = st.columns(2)
                with col_force:
                    # Force Analysis button
                    persona_ok = bool(st.session_state.get("digital_persona")) and bool(profile.get("master_cv_text"))
                    if st.button(f"🔍 Force Analysis", key=f"force_analysis_{job_key}", disabled=(not persona_ok)):
                        # Re-analyze job with relaxed criteria
                        try:
                            job_description = job.get('description', '')
                            user_learnings = load_user_learnings()
                            master_profile = engine.build_master_search_profile(
                                profile.get('master_cv_text', ''),
                                skill_bucket=st.session_state.get('my_skill_bucket', []),
                                rejection_learnings=user_learnings
                            )
                            # Re-analyze with force flag
                            forced_analysis = engine.analyze_match(
                                job_description, 
                                profile['master_cv_text'],
                                skill_bucket=st.session_state.my_skill_bucket,
                                master_profile=master_profile,
                                digital_persona=st.session_state.digital_persona,
                                job_title=job.get('title', ''),
                                job_url=job.get('job_url', '')
                            )
                            # Update analysis
                            st.session_state.job_analyses[job_key] = forced_analysis
                            st.success("✅ Job re-analyzed with relaxed criteria!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error re-analyzing job: {e}")
                
                with col_train:
                    # Train System button
                    if st.button(f"🎓 Train System: This role/skill is a perfect match", key=f"train_system_{job_key}"):
                        # Extract key skills from job and add to Professional DNA
                        try:
                            job_description = job.get('description', '')
                            top_skills = engine.extract_top_skills(job_description, profile['master_cv_text'])
                            
                            # Add skills to preferences.json Professional DNA
                            from utils import load_preferences, save_preferences
                            preferences = load_preferences()
                            professional_dna = preferences.get('professional_dna', {})
                            custom_skills = professional_dna.get('custom_skills', '')
                            
                            # Add new skills to custom_skills
                            new_skills = [s for s in top_skills if s not in custom_skills and s != 'Irrelevant Role']
                            if new_skills:
                                if custom_skills:
                                    custom_skills += f", {', '.join(new_skills)}"
                                else:
                                    custom_skills = ', '.join(new_skills)
                                
                                professional_dna['custom_skills'] = custom_skills
                                preferences['professional_dna'] = professional_dna
                                save_preferences(preferences)
                                
                                st.success(f"✅ Added skills to Professional DNA: {', '.join(new_skills)}")
                                st.rerun()
                            else:
                                st.info("No new skills to add from this job.")
                        except Exception as e:
                            st.error(f"Error training system: {e}")
            
            # Buttons row
            col1, col2 = st.columns(2)
            with col1:
                # Apply with AI Bot button - always visible for every displayed job
                persona_ok = bool(st.session_state.get("digital_persona")) and bool(profile.get("master_cv_text"))
                if not persona_ok:
                    st.info("ℹ️ Please upload/initialize your CV first.")
                # Magic Cover Letter Button with Glow Effect
                button_html = f"""
                <style>
                    .magic-button-{index} {{
                        background: linear-gradient(135deg, #3B82F6 0%, #2563EB 100%);
                        border: none;
                        border-radius: 8px;
                        padding: 10px 20px;
                        color: white;
                        font-weight: 600;
                        cursor: pointer;
                        transition: all 0.3s ease;
                        box-shadow: 0 0 15px rgba(59, 130, 246, 0.3);
                    }}
                    .magic-button-{index}:hover {{
                        box-shadow: 0 0 25px rgba(59, 130, 246, 0.6);
                        transform: translateY(-2px);
                    }}
                </style>
                """
                st.markdown(button_html, unsafe_allow_html=True)
                if st.button(f"✨ Magic Cover Letter", key=f"apply_{index}", disabled=(not persona_ok)):
                    # Update preferences: Mark job as approved (boosts skill weights)
                    job_data_for_prefs = {
                        'company': job.get('company', 'Unknown'),
                        'title': job.get('title', 'Unknown'),
                        'job_url': job.get('job_url', ''),
                        'description': job.get('description', '')
                    }
                    update_preferences(job_data_for_prefs, 'approve', user_id=get_user_id())
                    
                    with st.status("📝 **יוצר טיוטה מותאמת...**", expanded=True) as draft_status:
                        try:
                            draft_status.update(label="🤖 מנתח משרה עם Gemini AI...")
                            # Build Master Search Profile and ensure Digital Persona exists
                            user_learnings = load_user_learnings()
                            master_profile = engine.build_master_search_profile(
                                profile['master_cv_text'],
                                skill_bucket=st.session_state.my_skill_bucket,
                                rejection_learnings=user_learnings
                            )
                            # Cover Letter Guard: Validate result before storing
                            cover_letter_result = engine.reframing_analysis(
                                job['description'], 
                                profile['master_cv_text'], 
                                skill_bucket=st.session_state.my_skill_bucket,
                                master_profile=master_profile,
                                digital_persona=st.session_state.digital_persona
                            )
                            # Soft Traits Injection (Writing-only): enrich tone without changing facts
                            try:
                                from utils import detect_language
                                lang = detect_language(job.get('description', ''))
                                cover_letter_result = pdf_generator.inject_soft_traits_into_cover_letter(
                                    cover_letter_result, language=lang
                                )
                            except Exception:
                                pass
                            # Validation: Ensure cover letter is not None
                            if cover_letter_result and isinstance(cover_letter_result, str) and len(cover_letter_result) > 0:
                                st.session_state.current_draft = cover_letter_result
                            else:
                                # Fallback: Generate basic cover letter
                                from utils import detect_language
                                job_lang = detect_language(job.get('description', ''))
                                st.session_state.current_draft = engine._generate_fallback_cover_letter(
                                    job.get('description', ''),
                                    profile['master_cv_text'],
                                    job_lang
                                )
                            st.session_state.selected_job = job.to_dict()  # Convert Series to dict for session state
                            draft_status.update(label="✅ טיוטה מוכנה!", state="complete")
                            st.rerun()
                        except Exception as e:
                            import traceback
                            draft_status.update(label=f"❌ שגיאה: {e}", state="error")
                            st.error(f"שגיאה ביצירת טיוטה: {e}")
                            print(f"ERROR on job draft for {job.get('title', '')}: {e}\n{traceback.format_exc()}")

            with col2:
                    # Smart Rejection (Learning Trash) - Show menu with AI-generated reasons using Digital Persona
                    if job_key not in st.session_state.show_rejection_menu:
                        st.session_state.show_rejection_menu[job_key] = False

                    if not st.session_state.show_rejection_menu.get(job_key, False):
                        if st.button(f"🗑️ Not Interested", key=f"blacklist_{index}"):
                            # Show rejection form with predefined reasons
                            st.session_state.show_rejection_menu[job_key] = True
                            st.rerun()
                    else:
                        # Show rejection form with predefined reasons
                        st.write("**Why is this job not relevant?**")
                        
                        # Predefined reasons for rejection
                        predefined_reasons = [
                            'Wrong Role',
                            'Salary too low',
                            'Company reputation',
                            'Already applied',
                            'Location',
                            'Other (Custom text)'
                        ]
                        
                        selected_reason = st.radio(
                            "Select reason:",
                            predefined_reasons,
                            key=f"rejection_reason_{job_key}"
                        )

                        # Show custom text input if "Other" is selected
                        custom_reason_text = ""
                        if selected_reason == 'Other (Custom text)':
                            custom_reason_text = st.text_input(
                                "Please specify the reason:",
                                key=f"custom_reason_input_{job_key}",
                                placeholder="e.g., 'Too far from home', 'Company size too small'"
                            )
                            if not custom_reason_text.strip():
                                st.warning("Please enter a custom reason before confirming.")
                        
                        col_reject, col_cancel = st.columns(2)
                        with col_reject:
                            # Only enable confirm if custom reason is provided (if Other selected)
                            confirm_disabled = (selected_reason == 'Other (Custom text)' and not custom_reason_text.strip())
                            if st.button("✅ Confirm Rejection", key=f"confirm_reject_{job_key}", disabled=confirm_disabled):
                                # Use custom reason if "Other" was selected
                                final_reason = custom_reason_text.strip() if selected_reason == 'Other (Custom text)' else selected_reason
                                
                                # Generate unique job_id for feedback storage
                                job_id = f"{job.get('company', '')}_{job.get('title', '')}_{job.get('job_url', '')}"
                                
                                # Store user feedback in feedback_log.json
                                engine.store_user_feedback(job_id, final_reason)
                                
                                # Move job to recycle bin
                                # Fix Pandas Warning: Convert Series to dict if needed
                                job_dict = job.to_dict() if hasattr(job, 'to_dict') else job
                                move_to_recycle_bin(job_dict, final_reason)
                                
                                # Add to blacklist (for backwards compatibility)
                                add_to_blacklist(job.get('job_url', ''), job.get('title', ''))
                                
                                # Save learning
                                add_rejection_learning(final_reason)
                                
                                # Update preferences: Add to rejected_jobs in preferences.json
                                job_data_for_prefs = {
                                    'company': job.get('company', 'Unknown'),
                                    'title': job.get('title', 'Unknown'),
                                    'job_url': job.get('job_url', ''),
                                    'description': job.get('description', ''),
                                    'reason': final_reason
                                }
                                update_preferences(job_data_for_prefs, 'reject', user_id=get_user_id())
                                
                                # Hide job immediately by removing from display
                                # Remove from session state jobs
                                if st.session_state.jobs is not None and not st.session_state.jobs.empty:
                                    mask = st.session_state.jobs['job_url'] != job.get('job_url', '')
                                    st.session_state.jobs = st.session_state.jobs[mask]
                                
                                # Remove from found_jobs list
                                st.session_state.found_jobs = [
                                    (idx, j, jk, an) for idx, j, jk, an in st.session_state.found_jobs
                                    if jk != job_key
                                ]
                                
                                # Clear menu state
                                st.session_state.show_rejection_menu[job_key] = False
                                if job_key in st.session_state.rejection_reasons:
                                    del st.session_state.rejection_reasons[job_key]
                                
                                st.success(f"Job moved to recycle bin. Reason: {final_reason}")
                                st.rerun()

                        with col_cancel:
                            if st.button("❌ Cancel", key=f"cancel_reject_{job_key}"):
                                st.session_state.show_rejection_menu[job_key] = False
                                if job_key in st.session_state.rejection_reasons:
                                    del st.session_state.rejection_reasons[job_key]
                                st.rerun()  # Only rerun on user action (cancel button)
                        
                        # AI-Powered Manual Reason: Add 'Other/Custom Reason' text field
                        st.write("---")
                        custom_reason = st.text_input(
                            "Or enter a custom reason:",
                            key=f"custom_reason_{job_key}",
                            placeholder="e.g., 'Too far from home', 'Company size too small'"
                        )
                        
                        if custom_reason.strip():
                            if st.button("✅ Use Custom Reason", key=f"use_custom_{job_key}"):
                                # Extract avoid rule from custom text using AI
                                try:
                                    avoid_rule = engine.extract_avoid_rule_from_text(
                                        custom_reason,
                                        job.get('description', ''),
                                        st.session_state.digital_persona
                                    )
                                    # Add to blacklist
                                    add_to_blacklist(job.get('job_url', ''), job.get('title', ''))
                                    
                                    # Update Digital Persona with new avoid rule
                                    if st.session_state.digital_persona:
                                        if 'avoid_patterns' not in st.session_state.digital_persona:
                                            st.session_state.digital_persona['avoid_patterns'] = []
                                        if avoid_rule not in st.session_state.digital_persona['avoid_patterns']:
                                            st.session_state.digital_persona['avoid_patterns'].append(avoid_rule)
                                    
                                    # Hide job immediately
                                    if st.session_state.jobs is not None and not st.session_state.jobs.empty:
                                        mask = st.session_state.jobs['job_url'] != job.get('job_url', '')
                                        st.session_state.jobs = st.session_state.jobs[mask]
                                    
                                    # Clear menu state
                                    st.session_state.show_rejection_menu[job_key] = False
                                    if job_key in st.session_state.rejection_reasons:
                                        del st.session_state.rejection_reasons[job_key]
                                    
                                    st.success(f"Job rejected. Learned new avoid rule: '{avoid_rule}'")
                                    st.rerun()  # Only rerun on user action
                                except Exception as e:
                                    st.error(f"Error processing custom reason: {e}")
                                    print(f"ERROR extracting avoid rule: {e}")
    
    # Display filtered jobs in collapsed "Low Match" section
    if filtered_by_persona:
        with st.expander(f"⚠️ Low Match Jobs ({len(filtered_by_persona)} filtered by Digital Persona)", expanded=False):
            st.info("These jobs were filtered out because they don't match your Digital Persona criteria. Review them to see what you might be missing.")
            for filtered_item in filtered_by_persona:
                job = filtered_item['job']
                job_key = filtered_item['job_key']
                analysis = filtered_item['analysis']
                reason = filtered_item['reason']
                
                with st.expander(f"{job.get('title', 'Unknown')} @ {job.get('company', 'Unknown')} - {reason}"):
                    st.write(f"**Reason:** {reason}")
                    st.write(f"**Score:** {analysis.get('score', 0)}%")
                    st.write(f"**Analysis:** {analysis.get('reasoning', 'N/A')}")
                    job_url = job.get('job_url', '#')
                    if job_url and job_url != '#':
                        st.write(f"[View Job]({job_url})")

def render_human_in_the_loop(engine, pdf_generator):
    """
    Renders the Human-in-the-Loop section for draft review and final submission.
    """
    if 'current_draft' in st.session_state and 'selected_job' in st.session_state:
        st.divider()
        selected_job_dict = st.session_state.selected_job
        st.subheader(f"📝 טיוטה להגשה עבור {selected_job_dict.get('company', 'Unknown')} ({selected_job_dict.get('title', 'Unknown')})")
        # Cover Letter Guard: Validate current_draft before accessing
        current_draft_text = st.session_state.current_draft
        if not current_draft_text or not isinstance(current_draft_text, str):
            # Fallback: Generate basic cover letter
            from utils import detect_language
            job_description = selected_job_dict.get('description', '')
            job_lang = detect_language(job_description)
            # Need engine and profile - use fallback text if unavailable
            if 'master_cv_text' in st.session_state:
                cv_text = st.session_state.get('master_cv_text', '')
            else:
                cv_text = ''
            current_draft_text = engine._generate_fallback_cover_letter(job_description, cv_text, job_lang)
            st.session_state.current_draft = current_draft_text
        final_text = st.text_area("ערוך את הטקסט לפני יצירת ה-PDF:", current_draft_text, height=200)
        
        if st.button("🔥 שלח מועמדות אוטומטית (Final Launch Only After Review)"):
            from browser_bot import JobAppBot, send_confirmation_email, auto_fill_ats
            from utils import log_application
            import asyncio
            
            with st.status("🚀 **שולח מועמדות...**", expanded=True) as submission_status:
                try:
                    # הכנת קובץ הגשה מותאם
                    company = selected_job_dict.get('company', '')
                    title = selected_job_dict.get('title', '')
                    job_url = selected_job_dict.get('job_url', '')

                    submission_status.update(label="📄 יוצר קובץ PDF מותאם...")
                    tailored_pdf_path = pdf_generator.create_tailored_pdf(title, company, final_text)

                    # ATS auto-fill integration (Lever / Greenhouse / LinkedIn)
                    ats_result = {"status": False, "error": ""}
                    try:
                        submission_status.update(label="⚡ ממלא שדות ATS אוטומטית...")
                        job_description = selected_job_dict.get('description', '')
                        ats_result = asyncio.run(auto_fill_ats(
                            site_name=selected_job_dict.get('site_name', ''),
                            company=company,
                            job_url=job_url,
                            profile_data_path='profile_data.json',
                            tailored_cv_path=tailored_pdf_path,
                            cover_letter_text=final_text,  # Language-aware cover letter (800-1200 chars)
                            job_description=job_description  # For AI question answering
                        ))
                    except Exception as e:
                        ats_result = {"status": False, "error": str(e)}
                        submission_status.update(label=f"⚠️ ATS Auto-fill error: {e}")
                        print(f"ERROR in auto_fill_ats: {e}")

                        # בוט דפדפן אוטונומי
                    submission_status.update(label="🌐 מפעיל בוט דפדפן...")
                    job_description = selected_job_dict.get('description', '')
                    bot = JobAppBot(
                        site_name=selected_job_dict.get('site_name', ''),
                        company=company,
                        job_url=job_url,
                        profile_data_path='profile_data.json',
                        tailored_cv_path=tailored_pdf_path,
                        cover_letter_text=final_text,  # Language-aware cover letter (800-1200 chars)
                        job_description=job_description  # For AI question answering
                    )

                    # Run async apply_to_job
                    try:
                        submission_status.update(label="🔗 מדפדף לאתר ומגיש מועמדות...")
                        submission_result = asyncio.run(bot.apply_to_job())
                    except Exception as e:
                        submission_result = {"status": False, "error": str(e)}
                        submission_status.update(label=f"❌ Browser bot error: {e}")
                        print(f"ERROR in JobAppBot.apply_to_job: {e}")

                    # לוגינג למניעת Black Hole
                    submission_status.update(label="📝 רושם ביומן...")
                    try:
                        log_application(selected_job_dict, final_text)
                    except Exception as e:
                        st.warning(f"שגיאת לוגינג: {e}")
                        print(f"ERROR in log_application: {e}")

                    # שליחת אישור במייל למשתמש
                    submission_status.update(label="📧 שולח אישור במייל...")
                    try:
                        email_result = send_confirmation_email(company=company, job_title=title, result=submission_result)
                    except Exception as e:
                        st.warning(f"שגיאה בשליחת מייל: {e}")
                        print(f"ERROR in send_confirmation_email: {e}")

                        # הודעה למשתמש
                    if submission_result.get('status', False):
                        submission_status.update(label=f"✅ המועמדות נשלחה ל-{company}!", state="complete")
                        st.success(f"✉️ המועמדות נשלחה ל-{company}. קיבלת אישור למייל.")
                    else:
                        submission_status.update(label=f"❌ שליחה נכשלה: {submission_result.get('error', 'לא ידועה')}", state="error")
                        st.error(f"שליחה נכשלה: {submission_result.get('error', 'לא ידועה')}")

                    # ATS הודעת הצלחה/כישלון
                    if ats_result.get('status', False):
                        st.info("📝 נתוני ATS מולאו אוטומטית בהצלחה.")
                    else:
                        st.warning(f"ATS Auto-fill לא הושלם: {ats_result.get('error', '')}")

                    # ניקוי הטיוטה על מנת למנוע שיגור נוסף (רק אחרי לחיצה על 'Final Launch')
                    del st.session_state.current_draft
                    del st.session_state.selected_job
                    # Clear notification flags
                    for key in list(st.session_state.keys()):
                        if key.startswith('high_match_'):
                            del st.session_state[key]
                    st.rerun()
                    
                except Exception as e:
                    submission_status.update(label=f"❌ שגיאה כללית: {e}", state="error")
                    st.error(f"שגיאה כללית בהגשה: {e}")
                    import traceback
                    st.code(traceback.format_exc())
                    print(f"ERROR in final submission flow: {e}")
