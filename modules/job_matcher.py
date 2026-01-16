"""Job matching module for scoring and gap analysis."""
import logging
import json
from typing import Dict, List, Tuple, Optional
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


class JobMatcher:
    """Match jobs with resumes using semantic similarity and gap analysis."""
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        """Initialize job matcher.
        
        Args:
            llm_client: Optional LLM client for advanced analysis
        """
        self.llm_client = llm_client or LLMClient()
        self.model = None
        self._load_model()
    
    def _load_model(self) -> None:
        """Load sentence transformer model for semantic similarity."""
        try:
            logger.info("Loading sentence transformer model...")
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise
    
    def calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score between 0 and 1
        """
        if not self.model:
            self._load_model()
        
        try:
            embeddings = self.model.encode([text1, text2])
            similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    def extract_requirements(self, job_description: str) -> Dict[str, List[str]]:
        """Extract requirements from job description using LLM.
        
        Args:
            job_description: Job description text
            
        Returns:
            Dictionary with skills, technologies, experience_required, etc.
        """
        system_prompt = """You are an expert job description analyzer. Extract key requirements from job postings.
        Return a JSON object with the following structure:
        {
            "skills": ["skill1", "skill2", ...],
            "technologies": ["tech1", "tech2", ...],
            "experience_years": <number or null>,
            "education": ["requirement1", ...],
            "certifications": ["cert1", ...],
            "soft_skills": ["skill1", ...]
        }
        Be comprehensive and accurate."""
        
        user_prompt = f"""Extract requirements from this job description:

{job_description}

Return only valid JSON, no additional text."""
        
        try:
            response = self.llm_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3
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
            requirements = json.loads(response)
            
            # Set defaults
            requirements.setdefault("skills", [])
            requirements.setdefault("technologies", [])
            requirements.setdefault("experience_years", None)
            requirements.setdefault("education", [])
            requirements.setdefault("certifications", [])
            requirements.setdefault("soft_skills", [])
            
            return requirements
        
        except Exception as e:
            logger.error(f"Error extracting requirements: {e}")
            return {
                "skills": [],
                "technologies": [],
                "experience_years": None,
                "education": [],
                "certifications": [],
                "soft_skills": []
            }
    
    def analyze_skills_gap(
        self,
        resume_data: Dict[str, any],
        job_requirements: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """Analyze skills gap and identify missing and bonus skills.
        
        Args:
            resume_data: Parsed resume data
            job_requirements: Extracted job requirements
            
        Returns:
            Dictionary with 'missing_skills' and 'bonus_skills' lists
        """
        resume_tech = set([t.lower().strip() for t in resume_data.get("tech_stack", [])])
        resume_skills = set([s.lower().strip() for s in resume_data.get("tech_stack", [])])
        
        job_tech = set([t.lower().strip() for t in job_requirements.get("technologies", [])])
        job_skills = set([s.lower().strip() for s in job_requirements.get("skills", [])])
        job_soft_skills = set([s.lower().strip() for s in job_requirements.get("soft_skills", [])])
        
        # Missing skills/technologies
        missing_tech = job_tech - resume_tech
        missing_skills = job_skills - resume_skills
        missing_soft_skills = job_soft_skills - resume_skills
        
        missing_all = list(missing_tech | missing_skills | missing_soft_skills)
        
        # Bonus skills (skills I have that are not required but valuable)
        bonus_tech = resume_tech - job_tech
        bonus_skills = resume_skills - job_skills
        
        # Filter out common/irrelevant terms
        common_terms = {"experience", "years", "development", "software", "engineering"}
        bonus_all = [s for s in list(bonus_tech | bonus_skills) if s not in common_terms]
        
        return {
            "missing_skills": missing_all[:10],  # Top 10 missing
            "bonus_skills": bonus_all[:10]  # Top 10 bonus
        }
    
    def identify_gaps(
        self,
        resume_data: Dict[str, any],
        job_requirements: Dict[str, List[str]]
    ) -> List[str]:
        """Identify missing skills/technologies in resume compared to job requirements.
        
        Args:
            resume_data: Parsed resume data
            job_requirements: Extracted job requirements
            
        Returns:
            List of gap descriptions
        """
        gaps = []
        skills_analysis = self.analyze_skills_gap(resume_data, job_requirements)
        
        if skills_analysis["missing_skills"]:
            gaps.append(f"Missing skills: {', '.join(skills_analysis['missing_skills'][:5])}")
        
        # Experience gap
        resume_years = resume_data.get("years_experience", 0)
        job_years = job_requirements.get("experience_years")
        if job_years and resume_years < job_years:
            gaps.append(f"Experience gap: {job_years - resume_years} years less than required")
        
        # Education gap
        job_education = job_requirements.get("education", [])
        if job_education:
            gaps.append(f"Education requirements: {', '.join(job_education[:3])}")
        
        return gaps
    
    def check_seniority_match(
        self,
        resume_data: Dict[str, any],
        job_description: str,
        job_title: str
    ) -> Tuple[float, str]:
        """Check if seniority level matches and return penalty/adjustment.
        
        Args:
            resume_data: Parsed resume data
            job_description: Job description text
            job_title: Job title
            
        Returns:
            Tuple of (penalty_score, explanation)
        """
        resume_seniority = resume_data.get("seniority_level", "mid").lower()
        resume_years = resume_data.get("years_experience", 0)
        
        # Extract job level from title and description
        text_lower = (job_title + " " + job_description).lower()
        
        # Determine job level
        if any(term in text_lower for term in ["junior", "jr", "entry", "associate", "intern"]):
            job_level = "junior"
        elif any(term in text_lower for term in ["senior", "sr", "lead", "principal", "staff", "architect"]):
            job_level = "senior"
        else:
            job_level = "mid"
        
        # Calculate penalty
        penalty = 0
        explanation = ""
        
        # Seniority mapping
        seniority_map = {"junior": 1, "mid": 2, "senior": 3, "lead": 4, "principal": 5}
        resume_level = seniority_map.get(resume_seniority, 2)
        job_level_num = seniority_map.get(job_level, 2)
        
        level_diff = resume_level - job_level_num
        
        if level_diff < -1:  # Resume is much lower than job
            penalty = -15
            explanation = f"Major seniority mismatch: You're {resume_seniority} but job requires {job_level}"
        elif level_diff == -1:  # Resume is slightly lower
            penalty = -5
            explanation = f"Minor seniority gap: You're {resume_seniority} but job prefers {job_level}"
        elif level_diff > 1:  # Resume is much higher than job
            penalty = -10
            explanation = f"Overqualified: You're {resume_seniority} but job is {job_level}"
        elif level_diff == 1:  # Resume is slightly higher
            penalty = 0
            explanation = f"Good match: You're {resume_seniority} for {job_level} role"
        else:  # Perfect match
            penalty = 5
            explanation = f"Perfect seniority match: {resume_seniority} for {job_level} role"
        
        return penalty, explanation
    
    def generate_match_explanation(
        self,
        resume_data: Dict[str, any],
        job_description: str,
        job_title: str,
        company: str,
        match_score: float,
        gaps: List[str],
        bonus_skills: List[str]
    ) -> Dict[str, str]:
        """Generate explanation for why this is a good fit and biggest hurdle.
        
        Args:
            resume_data: Parsed resume data
            job_description: Job description
            job_title: Job title
            company: Company name
            match_score: Calculated match score
            gaps: List of identified gaps
            bonus_skills: List of bonus skills
            
        Returns:
            Dictionary with 'good_fit' and 'biggest_hurdle' explanations
        """
        system_prompt = """You are an expert career advisor. Provide concise, actionable insights about job matches.
        Be specific and honest. Keep each explanation to exactly 1-2 sentences."""
        
        user_prompt = f"""Analyze this job match and provide two explanations:

Job: {job_title} at {company}
Match Score: {match_score}%

Resume Info:
- Tech Stack: {', '.join(resume_data.get('tech_stack', [])[:10])}
- Experience: {resume_data.get('years_experience', 0)} years
- Seniority: {resume_data.get('seniority_level', 'mid')}

Gaps Identified: {', '.join(gaps) if gaps else 'None'}
Bonus Skills: {', '.join(bonus_skills[:5]) if bonus_skills else 'None'}

Job Description:
{job_description[:1000]}

Provide:
1. "good_fit": Why this is a good fit (1-2 sentences, be specific)
2. "biggest_hurdle": What is the biggest hurdle/challenge (1-2 sentences, be honest)

Return as JSON:
{{
    "good_fit": "...",
    "biggest_hurdle": "..."
}}"""
        
        try:
            response = self.llm_client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.5
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
            
            explanation = json.loads(response)
            
            return {
                "good_fit": explanation.get("good_fit", "Good alignment with job requirements."),
                "biggest_hurdle": explanation.get("biggest_hurdle", "Review job requirements carefully.")
            }
        
        except Exception as e:
            logger.error(f"Error generating match explanation: {e}")
            # Fallback explanation
            return {
                "good_fit": f"Your experience with {', '.join(resume_data.get('tech_stack', [])[:3])} aligns well with this role.",
                "biggest_hurdle": f"Consider addressing: {', '.join(gaps[:2]) if gaps else 'general requirements'}"
            }
    
    def calculate_match_score(
        self,
        resume_data: Dict[str, any],
        job_description: str,
        job_title: str = "",
        job_requirements: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, any]:
        """Calculate overall match score between resume and job.
        
        Args:
            resume_data: Parsed resume data
            job_description: Full job description
            job_title: Job title (for seniority matching)
            job_requirements: Optional pre-extracted requirements
            
        Returns:
            Dictionary with score, gaps, missing_skills, bonus_skills, etc.
        """
        if job_requirements is None:
            job_requirements = self.extract_requirements(job_description)
        
        # Combine resume information
        resume_text = resume_data.get("summary", "") + " " + \
                     " ".join(resume_data.get("tech_stack", [])) + " " + \
                     resume_data.get("raw_text", "")
        
        # Semantic similarity score (0-1, scaled to 0-50)
        semantic_score = self.calculate_semantic_similarity(resume_text, job_description) * 50
        
        # Keyword matching score (0-50)
        resume_tech = set([t.lower() for t in resume_data.get("tech_stack", [])])
        job_tech = set([t.lower() for t in job_requirements.get("technologies", [])])
        
        if job_tech:
            tech_match_ratio = len(resume_tech & job_tech) / len(job_tech)
        else:
            tech_match_ratio = 0.5  # Neutral if no tech requirements
        
        keyword_score = tech_match_ratio * 50
        
        # Experience match (bonus/penalty)
        resume_years = resume_data.get("years_experience", 0)
        job_years = job_requirements.get("experience_years")
        
        experience_bonus = 0
        if job_years:
            if resume_years >= job_years:
                experience_bonus = 5  # Bonus for meeting/exceeding
            elif resume_years >= job_years * 0.8:
                experience_bonus = 0  # Close enough
            else:
                experience_bonus = -5  # Penalty for significant gap
        
        # Seniority match with penalty system
        seniority_penalty, seniority_explanation = self.check_seniority_match(
            resume_data,
            job_description,
            job_title
        )
        
        # Total score (0-100)
        total_score = semantic_score + keyword_score + experience_bonus + seniority_penalty
        total_score = max(0, min(100, total_score))  # Clamp to 0-100
        
        # Identify gaps and analyze skills
        gaps = self.identify_gaps(resume_data, job_requirements)
        skills_analysis = self.analyze_skills_gap(resume_data, job_requirements)
        
        return {
            "score": round(total_score, 2),
            "gaps": gaps,
            "missing_skills": skills_analysis["missing_skills"],
            "bonus_skills": skills_analysis["bonus_skills"],
            "seniority_penalty": seniority_penalty,
            "seniority_explanation": seniority_explanation
        }
    
    def match_jobs(
        self,
        resume_data: Dict[str, any],
        jobs: List[Dict[str, str]]
    ) -> List[Dict[str, any]]:
        """Match multiple jobs with resume.
        
        Args:
            resume_data: Parsed resume data
            jobs: List of job dictionaries
            
        Returns:
            List of jobs with match scores, gaps, and explanations added
        """
        matched_jobs = []
        
        for job in jobs:
            try:
                job_description = job.get("description", "") or job.get("title", "")
                job_title = job.get("title", "")
                company = job.get("company", "")
                
                if not job_description:
                    logger.warning(f"Skipping job {job_title} - no description")
                    continue
                
                # Calculate match score with enhanced analysis
                match_result = self.calculate_match_score(
                    resume_data,
                    job_description,
                    job_title
                )
                
                # Generate match explanation
                explanation = self.generate_match_explanation(
                    resume_data,
                    job_description,
                    job_title,
                    company,
                    match_result["score"],
                    match_result["gaps"],
                    match_result["bonus_skills"]
                )
                
                matched_job = {
                    **job,
                    "match_score": match_result["score"],
                    "gaps": match_result["gaps"],
                    "missing_skills": match_result["missing_skills"],
                    "bonus_skills": match_result["bonus_skills"],
                    "seniority_penalty": match_result["seniority_penalty"],
                    "seniority_explanation": match_result["seniority_explanation"],
                    "good_fit": explanation["good_fit"],
                    "biggest_hurdle": explanation["biggest_hurdle"]
                }
                
                matched_jobs.append(matched_job)
                logger.info(f"Matched {job_title} at {company}: {match_result['score']}%")
            
            except Exception as e:
                logger.error(f"Error matching job {job.get('title')}: {e}")
                continue
        
        # Sort by match score (descending)
        matched_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        
        return matched_jobs
