from litellm import completion
import os

class JobAgent:
    def __init__(self):
        # הגדרת המפתח בסביבת העבודה עבור litellm
        os.environ["GEMINI_API_KEY"] = "AIzaSyAnK3RihXUWKMrm7c09kvlpTnsLr6Bd7iM"
        self.model = "gemini/gemini-1.5-flash"

    def analyze_match(self, resume_text, job_description):
        prompt = f"""
        Compare the following Resume and Job Description.
        
        Resume: {resume_text}
        Job Description: {job_description}
        
        Provide a JSON output with:
        1. match_score (0-100)
        2. missing_skills (list)
        3. tailored_summary (a short summary for this job)
        """
        
        response = completion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        return response.choices[0].message.content