import json
import logging
from typing import Dict, Any, Optional
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

class ResumeParser:
    def __init__(self, *args, **kwargs):
        """
        אתחול מנתח קורות החיים.
        מקבל ארגומנטים גמישים כדי למנוע שגיאות מול dashboard.py.
        """
        self.llm = LLMClient()

    def analyze_resume(self, resume_text: str) -> Dict[str, Any]:
        """
        הפונקציה המרכזית לניתוח הטקסט.
        """
        system_prompt = """You are an expert resume analyzer. 
Return ONLY a valid JSON object with: 
- "tech_stack": list
- "years_experience": number
- "seniority_level": string
- "job_titles": list
- "summary": string"""
        
        user_prompt = f"Analyze this resume text:\n\n{resume_text}"

        try:
            response = self.llm.ask(prompt=user_prompt, system_prompt=system_prompt)
            
            # ניקוי פורמט Markdown
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:-3].strip()
            elif clean_response.startswith("```"):
                clean_response = clean_response[3:-3].strip()
                
            analysis = json.loads(clean_response)
            
            # הבטחת קיום שדות חובה
            for key in ["tech_stack", "job_titles"]:
                if key not in analysis: analysis[key] = []
            if "years_experience" not in analysis: analysis["years_experience"] = 0
            
            return analysis
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            return {
                "tech_stack": [],
                "years_experience": 0,
                "seniority_level": "unknown",
                "job_titles": [],
                "summary": f"Error during analysis: {str(e)}"
            }

    def parse(self, resume_text: str) -> Dict[str, Any]:
        """
        תיקון לשגיאת ה-AttributeError:
        פונקציה זו פשוט קוראת ל-analyze_resume כדי להתאים לדרישות ה-dashboard.
        """
        return self.analyze_resume(resume_text)