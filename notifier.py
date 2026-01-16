import csv
from datetime import datetime

class Notifier:
    def __init__(self, log_file="applications_log.csv"):
        self.log_file = log_file
        self.init_log()

    def init_log(self):
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Company", "Role", "Link", "Status"])

    def log_application(self, company, role, link):
        date = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(self.log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([date, company, role, link, "Submitted"])
        print(f"📧 Notifier: Application logged for {company}")

    def send_email_summary(self):
        # כאן יבוא חיבור ל-SMTP או SendGrid
        print("📧 Notifier: Email summary sent to your profile address.")