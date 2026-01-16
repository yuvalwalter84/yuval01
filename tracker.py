"""
Vision Stack 2026: Application Tracker
--------------------------------------
Tracks every job application with full transparency and zero regressions. 
All fields are persisted to CSV; integrates with the guardrail system and supports 
manual review, historical analysis, and scheduled follow-ups. 
"""

import pandas as pd
import datetime
import os
import json

class AppTracker:
    def __init__(self, filename="applications_history.csv", profile_data_path="profile_data.json"):
        """
        Initialize Application Tracker.
        All job applications are logged to a CSV. The filename is configurable.
        """
        self.filename = filename
        self.profile_data_path = profile_data_path
        self.ensure_tracker_file()
        self._ensure_profile_data_json()

    def ensure_tracker_file(self):
        """
        Ensure that application log CSV exists with required columns.
        """
        required_columns = [
            "Date", "Company", "Title", "URL", "Status", "FollowUp_Date", 
            "Application_Text", "Site", "Job_ID", "ATS_Status", "User_Email"
        ]
        if not os.path.exists(self.filename):
            df = pd.DataFrame(columns=required_columns)
            df.to_csv(self.filename, index=False)
        else:
            # If columns are missing (legacy files), ensure new columns
            df = pd.read_csv(self.filename)
            for col in required_columns:
                if col not in df.columns:
                    df[col] = ""
            df.to_csv(self.filename, index=False)

    def _ensure_profile_data_json(self):
        """
        Ensure profile_data.json exists with basic required fields.
        """
        default_data = {"master_cv_text": "", "auto_query": "", "user_email": ""}
        if not os.path.exists(self.profile_data_path):
            with open(self.profile_data_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=4)
        else:
            try:
                with open(self.profile_data_path, "r+", encoding="utf-8") as f:
                    data = json.load(f)
                    updated = False
                    for key in default_data:
                        if key not in data:
                            data[key] = default_data[key]
                            updated = True
                    if updated:
                        f.seek(0)
                        json.dump(data, f, indent=4)
                        f.truncate()
            except Exception:
                with open(self.profile_data_path, "w", encoding="utf-8") as f:
                    json.dump(default_data, f, indent=4)

    def load_user_email(self):
        """
        Load user email from profile_data.json (the single source of truth).
        """
        try:
            with open(self.profile_data_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            return profile.get("user_email", "")
        except Exception:
            return ""

    def log_application(self, job, application_text, ats_status="", job_id=None, status="Applied", followup_days=7):
        """
        Log a submitted job application to CSV.
        Args:
            job (dict): contains at minimum 'company', 'title', 'job_url', 'site_name'
            application_text (str): The body or content used for submission (tailored summary, etc).
            ats_status (str): Result of ATS auto-fill (optional).
            job_id (str/int/None): Platform-specific job posting ID, if available.
            status (str): Application status, default "Applied".
            followup_days (int): Days until suggested follow-up.
        """
        self.ensure_tracker_file()
        df = pd.read_csv(self.filename)
        new_entry = {
            "Date": datetime.date.today().isoformat(),
            "Company": job.get("company", ""),
            "Title": job.get("title", ""),
            "URL": job.get("job_url", ""),
            "Status": status,
            "FollowUp_Date": (datetime.date.today() + datetime.timedelta(days=followup_days)).isoformat(),
            "Application_Text": application_text,
            "Site": job.get("site_name", ""),
            "Job_ID": job_id if job_id is not None else job.get("job_id", ""),
            "ATS_Status": ats_status,
            "User_Email": self.load_user_email()
        }
        df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
        df.to_csv(self.filename, index=False)
        print(f"📊 Tracker: Logged application to {new_entry['Company']} ({new_entry['Title']}) on {new_entry['Site']}")

    def list_applications(self, filter_status=None):
        """
        List all applications, optionally filtering by status.
        Returns a DataFrame.
        """
        self.ensure_tracker_file()
        df = pd.read_csv(self.filename)
        if filter_status:
            return df[df['Status'] == filter_status]
        return df

    def update_status(self, job_url, new_status):
        """
        Update the status of an application by job URL.
        """
        self.ensure_tracker_file()
        df = pd.read_csv(self.filename)
        changed = False
        for idx, row in df.iterrows():
            if str(row.get('URL', '')) == str(job_url):
                df.at[idx, 'Status'] = new_status
                changed = True
        if changed:
            df.to_csv(self.filename, index=False)
            print(f"🔄 Tracker: Updated status for {job_url} to {new_status}")
        else:
            print(f"⚠️ Tracker: No matching application found for {job_url}")

    def mark_followed_up(self, job_url):
        """
        Mark an application as followed up.
        """
        self.update_status(job_url, 'Followed-Up')
        print(f"✅ Tracker: Marked as followed up ({job_url})")

    def upcoming_follow_ups(self, days_ahead=2):
        """
        List applications with follow-up date within the next N days.
        """
        self.ensure_tracker_file()
        df = pd.read_csv(self.filename)
        today = datetime.date.today()
        soon = today + datetime.timedelta(days=days_ahead)
        if 'FollowUp_Date' in df.columns:
            df['FollowUp_Date'] = pd.to_datetime(df['FollowUp_Date'], errors='coerce').dt.date
            due = df[(df['FollowUp_Date'] >= today) & (df['FollowUp_Date'] <= soon) & (df['Status'] == 'Applied')]
            return due
        return pd.DataFrame([])
