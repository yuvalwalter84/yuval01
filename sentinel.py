import os
import subprocess
import time
import asyncio
from google import genai

class Sentinel:
    def __init__(self):
        self.vision_components = {
            "Scraper": "job_scraper.py",
            "Analyzer": "browser_bot.py",
            "Notifier": "notifier.py",
            "App": "app.py"
        }
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None
        
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            print("⚠️ Sentinel: Warning - No API Key found. Healing mode disabled.")

    def check_integrity(self):
        print(f"🕵️ Sentinel Check: {time.strftime('%H:%M:%S')}")
        for name, file in self.vision_components.items():
            if not os.path.exists(file):
                print(f"🚨 MISSING: {name} ({file})")
                continue
            
            # בדיקת סינטקס מהירה
            res = subprocess.run([sys.executable, "-m", "py_compile", file], capture_output=True)
            if res.returncode != 0:
                print(f"❌ CORRUPTED: {name}")
                if self.client:
                    self.heal_file(file, res.stderr.decode())

    def heal_file(self, file_path, error):
        # הלוגיקה של התיקון שכבר כתבנו
        pass

    async def main_loop(self):
        while True:
            self.check_integrity()
            await asyncio.sleep(60)

if __name__ == "__main__":
    import sys
    s = Sentinel()
    asyncio.run(s.main_loop())