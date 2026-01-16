"""
Persona - Admin Console
Provides an admin control panel for sensitivity settings and a quick job feed view.
"""

import os
import time
import pandas as pd
import streamlit as st

from utils import load_preferences, save_preferences, reset_system_data
from background_scout import run_job_scout_cycle
from core_engine import CoreEngine, load_persona_cache


st.set_page_config(page_title="Persona - Admin Console", layout="wide")

st.title("🛠️ Persona Admin Console")
st.caption("Administrative controls for scoring sensitivity and visibility.")


def _load_jobs_feed():
    """
    Load a lightweight job feed for admin visibility.
    Prefer discovered_jobs.csv (produced by background_scout), otherwise return empty DF.
    """
    path = "discovered_jobs.csv"
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        return df
    except Exception:
        return pd.DataFrame()


prefs = load_preferences()
prefs.setdefault("user_identity", {})

default_threshold = int(prefs.get("user_identity", {}).get("match_threshold", 60) or 60)

st.sidebar.header("🎚️ Sensitivity Controls")

def _save_threshold():
    new_val = int(st.session_state.admin_min_score)
    prefs = load_preferences()
    prefs.setdefault("user_identity", {})
    prefs["user_identity"]["match_threshold"] = new_val
    save_preferences(prefs, preserve_user_settings=True)
    st.toast("Persona updated. Minimum Matching Score saved.")


min_score = st.sidebar.slider(
    "Minimum Matching Score",
    min_value=0,
    max_value=100,
    value=default_threshold,
    key="admin_min_score",
    help="Lower this to show more jobs in the feed (e.g., 50).",
    on_change=_save_threshold
)

debug_mode = st.sidebar.toggle(
    "Debug Mode (show all, even 0%)",
    value=False,
    help="Temporary debug: disable score filtering entirely in this admin feed."
)

st.sidebar.divider()
st.sidebar.header("🕵️ Scout Controls")

def _tail_file(path: str, lines: int = 50) -> str:
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            content = f.readlines()
        return "".join(content[-lines:])
    except Exception:
        return ""

if st.sidebar.button("🚨 Force Manual Crawl", key="force_manual_crawl_btn"):
    with st.status("Running one Background Scout cycle (manual)...", expanded=True) as s:
        try:
            s.update(label="Starting scout cycle...")
            result = run_job_scout_cycle()
            s.update(label=f"Scout cycle finished (result={result})", state="complete")
            st.success("✅ Manual crawl completed. See logs below.")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            s.update(label=f"❌ Manual crawl failed: {e}", state="error")
            st.error("Manual crawl failed. See technical details.")
            with st.expander("Show Technical Details"):
                st.code(tb)

st.divider()
st.subheader("📜 Scout Status Log (tail)")
status_tail = _tail_file("scout_status.log", lines=80)
if status_tail:
    st.code(status_tail)
else:
    st.info("No `scout_status.log` yet. Run a crawl to generate it.")

st.divider()
st.subheader("📋 Job Feed")

jobs_df = _load_jobs_feed()
if jobs_df.empty:
    st.info("No jobs feed found yet. Waiting for `discovered_jobs.csv` from the background scout.")
else:
    # Normalize match_score to numeric if present
    if "match_score" in jobs_df.columns:
        jobs_df["match_score"] = pd.to_numeric(jobs_df["match_score"], errors="coerce").fillna(0).astype(int)
    else:
        jobs_df["match_score"] = 0

    if debug_mode:
        filtered = jobs_df.copy()
        st.info(f"Debug Mode ON: showing all {len(filtered)} jobs.")
    else:
        filtered = jobs_df[jobs_df["match_score"] >= int(min_score)].copy()
        st.info(f"Showing {len(filtered)} jobs with match_score >= {int(min_score)} (out of {len(jobs_df)} total).")

    # Show newest first if timestamp exists
    if "timestamp" in filtered.columns:
        try:
            filtered = filtered.sort_values("timestamp", ascending=False)
        except Exception:
            pass

    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True
    )

st.divider()
st.subheader("🌐 Manual Social Paste (Back-office)")
st.caption("Paste raw job lead text (LinkedIn post, WhatsApp message, email snippet). Persona will pre-filter hard constraints before any AI call.")

engine = CoreEngine()
persona = load_persona_cache()

social_text = st.text_area("Manual Social Paste", height=200, placeholder="Paste raw job lead text here...")
if st.button("🔍 Analyze Social Lead", key="analyze_social_lead_btn"):
    if not social_text.strip():
        st.warning("Please paste some text first.")
    elif not persona:
        st.warning("Persona not initialized. Please initialize Persona from CV first.")
    else:
        # Hard constraints pre-filter (no AI spend if failed)
        kept, dropped = engine.pre_filter_jobs(social_text, prefs=load_preferences())
        if dropped:
            reason = dropped[0].get("discard_reason", "Hard constraint failed")
            st.error(f"❌ Discarded by Hard Constraints: {reason}")
        else:
            with st.status("Analyzing social lead...", expanded=True) as s:
                try:
                    s.update(label="Running match analysis...")
                    analysis = engine.analyze_match(
                        social_text,
                        load_preferences().get("profile", {}).get("master_cv_text", "") or "",  # may be missing; engine will warn
                        digital_persona=persona,
                        job_title="Social Lead",
                        job_url="social://manual_paste"
                    )
                    s.update(label="Done.", state="complete")
                    st.write(analysis)
                except Exception as e:
                    s.update(label=f"Failed: {e}", state="error")
                    st.exception(e)

st.divider()
st.subheader("🧹 System Maintenance")
st.caption("Danger zone: this will delete preferences/professional DNA and clear uploaded files.")

confirm_reset = st.checkbox(
    "I understand this will permanently delete local system data",
    value=False,
    key="confirm_reset_entire_system",
)

if st.button("🗑️ Reset Entire System", key="reset_entire_system_btn", disabled=(not confirm_reset)):
    with st.status("Resetting Persona system data...", expanded=True) as s:
        ok = False
        try:
            ok = bool(reset_system_data(uploads_dir="uploads"))
        except Exception as e:
            ok = False
            s.update(label=f"Reset failed: {e}", state="error")
            st.exception(e)

        # Clean Session Start: Clear session state and rerun after reset
        try:
            st.session_state.clear()
            print("✅ Session state cleared")
        except Exception as e:
            print(f"⚠️ Could not clear session state: {e}")

        if ok:
            s.update(label="Reset completed successfully. Restarting...", state="complete")
            st.success("✅ System reset complete. Restarting...")
            print("PRINT: System is now 100% empty when the reset is complete.")
        else:
            s.update(label="Reset completed with errors. Restarting...", state="error")
            st.error("⚠️ Reset finished with errors (some files may be in use). Restarting anyway...")
            print("PRINT: System is now 100% empty when the reset is complete (with some errors).")

        # Force rerun to kill memory and restart from clean state
        time.sleep(0.5)  # Let filesystem settle
        st.rerun()
