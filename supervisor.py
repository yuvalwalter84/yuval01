import os
import subprocess
import time

def run_stack():
    print("🚀 Supervisor: Starting...")
    # ניקוי קבצים ישנים
    for f in os.listdir():
        if f.startswith("CV_") and f.endswith(".pdf"):
            os.remove(f)
    
    subprocess.Popen(["streamlit", "run", "app.py"])
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    run_stack()