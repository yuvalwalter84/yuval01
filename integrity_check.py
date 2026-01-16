"""
Vision Stack 2026: System Integrity Check
-----------------------------------------
This script verifies that all core components, integrations, and key guardrails required for the Autonomous CTO Agent project 
are present and unbroken. It prevents accidental regressions by scanning for required functions, classes, key strings, and data fields 
across the entire system (code and profile data). You MUST run this check before every launch.
"""

import os
import json
import re

def check_file_contains(file_path, patterns):
    """
    Checks whether all required patterns (functions/classes/keys) exist in the given file.
    Returns missing patterns. Handles both code (regex/function/class) and JSON keys.
    """
    missing = []
    if not os.path.exists(file_path):
        return patterns  # All missing if file not found

    # For JSON
    if file_path.endswith('.json'):
        try:
            with open(file_path, 'r', encoding='utf-8') as jf:
                data = json.load(jf)
                for key in patterns:
                    if key not in data:
                        missing.append(key)
        except Exception:
            missing.extend(patterns)
        return missing

    # For code/scripts
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            for pat in patterns:
                # Use regex for function/class names, and also direct string match as fallback
                func_regex = rf'def\s+{pat}\s*\('
                class_regex = rf'class\s+{pat}\s*[\(:]'
                if (re.search(func_regex, content) or 
                    re.search(class_regex, content) or
                    pat in content):
                    continue  # Found
                else:
                    missing.append(pat)
    except Exception:
        missing.extend(patterns)
    return missing

def verify_system():
    """
    Verifies that all essential files, functions, and user data keys are present.
    This check guards against regressions and missing capabilities per the Vision Stack guardrails.
    Returns a list of errors that must be addressed.
    """

    # Core code/data assets and guardrail mappings.
    core_assets = {
        "app.py": [
            # UI/stack
            "file_uploader",
            "st.session_state.jobs",
            "current_draft",
            # Manual Draft/Final Launch
            "Final Launch",
            "'Draft'",
            # Guardrails
            "verify_system",
            "log_application",
            # Integration points
            "auto_fill_ats",
            "send_confirmation_email",
        ],
        "browser_bot.py": [
            # SMTP/Notification
            "send_confirmation_email",
            # ATS Integration
            "auto_fill_ats",
            # App logic
            "JobAppBot",
            "submit_application",
        ],
        "pdf_tailor.py": [
            "analyze_match",
            "reframing_analysis",
            "create_tailored_pdf",
        ],
        "profile_data.json": [
            "master_cv_text",
            "auto_query",
            "email"
        ]
    }
    # Always include black-hole prevention (historical log)
    if not os.path.exists("applications_history.csv"):
        # Don't scan log—just flag missing
        history_csv_error = ["applications_history.csv"]
    else:
        history_csv_error = []

    errors = []
    for file, patterns in core_assets.items():
        missing = check_file_contains(file, patterns)
        if missing:
            for m in missing:
                if file.endswith('.json'):
                    errors.append(f"Missing Key: '{m}' in {file}")
                else:
                    errors.append(f"Regression: '{m}' missing in {file}")

    # Extra regression protection
    # Check that NO code shrinkage has occurred (warn if any core file is <50 lines)
    for code_file in ["app.py", "browser_bot.py", "pdf_tailor.py"]:
        if os.path.isfile(code_file):
            with open(code_file, 'r', encoding='utf-8') as f:
                line_count = sum(1 for _ in f)
                if line_count < 50:
                    errors.append(f"Regression: File length anomaly—{code_file} has only {line_count} lines (possible shrinkage)")

    # Black-hole CSV check
    for err in history_csv_error:
        errors.append(f"Missing File: {err}")

    return errors

if __name__ == "__main__":
    errs = verify_system()
    if not errs:
        print("✅ System Integrity Verified. All core guardrails and persistence requirements are present.")
    else:
        print("❌ Detected system integrity violations:")
        for e in errs:
            print("-", e)