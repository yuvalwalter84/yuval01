import os
from google import genai
from google.genai import types
import json
import re

class JobSearchAgent:
    def __init__(self):
        # אתחול הלקוח החדש של גוגל - הוא שואב אוטומטית את GEMINI_API_KEY מהסביבה
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model_id = "gemini-2.5-flash" 

    def extract_skills(self, resume_text):
        prompt = f"Analyze this resume and return a JSON with 'top_job_titles' (list) and 'skills' (list):\n{resume_text[:2000]}"
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return response.text
        except Exception as e:
            print(f"❌ AI Error (Skills): {e}")
            return '{"top_job_titles": ["Software Developer"], "skills": []}'

    def match_and_score(self, resume_text, job_description):
        prompt = f"""
        CV: {resume_text[:1500]}
        Job: {job_description[:1000]}
        Return ONLY a JSON object: {{"match_score": 0-100, "reason": "short explanation"}}
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return response.text
        except Exception:
            return '{"match_score": 0}'