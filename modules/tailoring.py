from typing import List, Optional
"""Resume and cover letter tailoring module."""
import logging
from typing import Dict, Optional
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class TailoringEngine:
    """Generate tailored resume summaries and cover letters."""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """Initialize tailoring engine.
        
        Args:
            llm_client: Optional LLM client instance
        """
        self.llm_client = llm_client or LLMClient()
    
    def generate_resume_summary(
        self,
        resume_data: Dict[str, any],
        job_description: str,
        job_title: str,
        company: str
    ) -> str:
        """Generate a tailored resume summary for a specific job.
        
        Args:
            resume_data: Parsed resume data
            job_description: Job description
            job_title: Job title
            company: Company name
            
        Returns:
            Tailored resume summary
        """
        system_prompt = """You are an expert resume writer. Create compelling, tailored resume summaries
        that highlight relevant experience and skills for specific job positions. Keep summaries concise
        (2-3 sentences) and impactful."""
        
        user_prompt = f"""Create a tailored resume summary for the following position:

Job Title: {job_title}
Company: {company}

Job Description:
{job_description}

Resume Information:
- Tech Stack: {', '.join(resume_data.get('tech_stack', []))}
- Years of Experience: {resume_data.get('years_experience', 0)}
- Seniority Level: {resume_data.get('seniority_level', 'mid')}
- Previous Titles: {', '.join(resume_data.get('job_titles', []))}
- Current Summary: {resume_data.get('summary', '')}

Create a new, tailored summary that:
1. Emphasizes relevant experience and skills
2. Aligns with the job requirements
3. Is compelling and professional
4. Is 2-3 sentences long

Return only the summary text, no additional formatting."""
        
        try:
            summary = self.llm_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7
            )
            
            logger.info(f"Generated tailored resume summary for {job_title} at {company}")
            return summary.strip()
        
        except Exception as e:
            logger.error(f"Error generating resume summary: {e}")
            # Fallback to original summary
            return resume_data.get("summary", "")
    
    def generate_cover_letter(
        self,
        resume_data: Dict[str, any],
        job_description: str,
        job_title: str,
        company: str,
        gaps: Optional[list] = None
    ) -> str:
        """Generate a tailored cover letter for a specific job.
        
        Args:
            resume_data: Parsed resume data
            job_description: Job description
            job_title: Job title
            company: Company name
            gaps: Optional list of identified gaps
            
        Returns:
            Tailored cover letter
        """
        system_prompt = """You are an expert cover letter writer. Create professional, compelling cover letters
        that effectively communicate the candidate's value proposition while addressing potential gaps.
        Keep the tone professional, enthusiastic, and authentic."""
        
        gaps_text = ""
        if gaps:
            gaps_text = f"\n\nNote: The following gaps were identified: {', '.join(gaps)}"
            gaps_text += "\nAddress these gaps positively, focusing on transferable skills and willingness to learn."
        
        user_prompt = f"""Write a tailored cover letter for the following position:

Job Title: {job_title}
Company: {company}

Job Description:
{job_description}

Candidate Information:
- Tech Stack: {', '.join(resume_data.get('tech_stack', []))}
- Years of Experience: {resume_data.get('years_experience', 0)}
- Seniority Level: {resume_data.get('seniority_level', 'mid')}
- Previous Titles: {', '.join(resume_data.get('job_titles', []))}
- Summary: {resume_data.get('summary', '')}
{gaps_text}

Create a professional cover letter that:
1. Opens with a strong, engaging introduction
2. Highlights relevant experience and achievements
3. Demonstrates understanding of the role and company
4. Addresses any gaps positively (if applicable)
5. Closes with enthusiasm and a call to action
6. Is approximately 3-4 paragraphs long

Return the complete cover letter text, properly formatted with paragraphs."""
        
        try:
            cover_letter = self.llm_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=1000
            )
            
            logger.info(f"Generated tailored cover letter for {job_title} at {company}")
            return cover_letter.strip()
        
        except Exception as e:
            logger.error(f"Error generating cover letter: {e}")
            return f"""Dear Hiring Manager,

I am writing to express my interest in the {job_title} position at {company}. 

Based on the job description, I believe my experience with {', '.join(resume_data.get('tech_stack', [])[:3])} and {resume_data.get('years_experience', 0)} years of experience make me a strong candidate for this role.

I would welcome the opportunity to discuss how my skills and experience align with your needs.

Sincerely,
[Your Name]"""
    
    def generate_cv_suggestions(
        self,
        resume_data: Dict[str, any],
        job_description: str,
        job_title: str,
        company: str,
        missing_skills: Optional[List[str]] = None
    ) -> List[str]:
        """Generate 3 specific suggestions to modify CV for this job.
        
        Args:
            resume_data: Parsed resume data
            job_description: Job description
            job_title: Job title
            company: Company name
            missing_skills: Optional list of missing skills
            
        Returns:
            List of 3 specific CV modification suggestions
        """
        system_prompt = """You are an expert resume writer. Provide specific, actionable suggestions for modifying a CV.
        Each suggestion should be concrete and tell the user exactly what to change (e.g., "In the experience section, 
        change 'X' to 'Y' to highlight your SQL expertise"). Keep suggestions practical and specific."""
        
        missing_skills_text = ""
        if missing_skills:
            missing_skills_text = f"\nMissing Skills to Address: {', '.join(missing_skills[:5])}"
        
        user_prompt = f"""Generate 3 specific suggestions to modify the CV for this job:

Job Title: {job_title}
Company: {company}

Job Description:
{job_description[:1500]}

Current Resume Info:
- Tech Stack: {', '.join(resume_data.get('tech_stack', []))}
- Experience: {resume_data.get('years_experience', 0)} years
- Summary: {resume_data.get('summary', '')[:200]}
{missing_skills_text}

Provide 3 specific, actionable suggestions. Each should:
1. Specify which section to modify (e.g., "In the experience section", "In the skills section")
2. Give a concrete example of what to change
3. Explain why it helps for this specific job

Return as JSON array:
{{
    "suggestions": [
        "Suggestion 1 with specific section and example",
        "Suggestion 2 with specific section and example",
        "Suggestion 3 with specific section and example"
    ]
}}"""
        
        try:
            response = self.llm_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7
            )
            
            # Clean response
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            import json
            result = json.loads(response)
            suggestions = result.get("suggestions", [])
            
            # Ensure we have exactly 3 suggestions
            while len(suggestions) < 3:
                suggestions.append("Review the job description and highlight relevant experience.")
            
            logger.info(f"Generated CV suggestions for {job_title} at {company}")
            return suggestions[:3]
        
        except Exception as e:
            logger.error(f"Error generating CV suggestions: {e}")
            # Fallback suggestions
            return [
                f"In the skills section, emphasize {', '.join(resume_data.get('tech_stack', [])[:2])} which align with this role.",
                f"In the experience section, highlight projects that demonstrate {missing_skills[0] if missing_skills else 'relevant'} expertise.",
                f"In the summary, mention your {resume_data.get('years_experience', 0)} years of experience in {resume_data.get('seniority_level', 'software development')}."
            ]
    
    def generate_linkedin_message(
        self,
        resume_data: Dict[str, any],
        job_title: str,
        company: str,
        job_description: str
    ) -> str:
        """Generate a short, personalized LinkedIn message (under 300 characters).
        
        Args:
            resume_data: Parsed resume data
            job_title: Job title
            company: Company name
            job_description: Job description
            
        Returns:
            LinkedIn message (under 300 characters)
        """
        system_prompt = """You are an expert at writing concise, professional LinkedIn messages. 
        Keep messages under 300 characters. Be friendly, specific, and show genuine interest."""
        
        user_prompt = f"""Write a short LinkedIn message for a hiring manager/recruiter about this job:

Job: {job_title} at {company}

My Background:
- {resume_data.get('years_experience', 0)} years experience with {', '.join(resume_data.get('tech_stack', [])[:3])}
- {resume_data.get('seniority_level', 'mid')} level

Job Description:
{job_description[:500]}

Write a concise, personalized message (under 300 characters) that:
1. Shows I've researched the role
2. Highlights 1-2 relevant skills
3. Expresses genuine interest
4. Includes a soft call to action

Return only the message text, no additional formatting."""
        
        try:
            message = self.llm_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.8,
                max_tokens=150
            )
            
            message = message.strip()
            
            # Ensure it's under 300 characters
            if len(message) > 300:
                message = message[:297] + "..."
            
            logger.info(f"Generated LinkedIn message for {job_title} at {company}")
            return message
        
        except Exception as e:
            logger.error(f"Error generating LinkedIn message: {e}")
            # Fallback message
            return f"Hi! I'm interested in the {job_title} role at {company}. With {resume_data.get('years_experience', 0)} years of {', '.join(resume_data.get('tech_stack', [])[:2])} experience, I'd love to discuss how I can contribute. Would you be open to a quick chat?"
