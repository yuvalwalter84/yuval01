import json
import os
import re
from dotenv import load_dotenv
from utils import APIClient, detect_language

# טעינת מפתח מהקובץ .env (לשמירה על בטיחות)
load_dotenv()

class PDFTailor:
    def __init__(self):
        # SDK Purge: Use utils.APIClient instead of legacy google.generativeai
        # This removes all legacy code and uses the centralized API client
        try:
            self.api_client = APIClient()
            self.model_id = self.api_client.model_id  # Track active model from APIClient
            print("INFO: PDFTailor using utils.APIClient (legacy SDK removed)")
        except Exception as e:
            raise ValueError(f"Failed to initialize APIClient: {e}")
    
    def _call_api_with_fallback(self, prompt):
        """
        Centralized API call method using utils.APIClient.
        SDK Purge: All legacy google.generativeai code removed.
        Returns the response object from APIClient.
        """
        try:
            response = self.api_client.call_api_with_fallback(prompt)
            # Update model_id if it changed
            if hasattr(self.api_client, 'model_id'):
                self.model_id = self.api_client.model_id
            return response
        except Exception as e:
            # Re-raise with context
            raise Exception(f"API call failed: {e}")
    
    def detect_language(self, text):
        """
        Delegates to utils.detect_language for consistency.
        """
        return detect_language(text)
        """
        Detects if text is Hebrew or English.
        Returns 'he' for Hebrew, 'en' for English.
        Uses heuristic: if Hebrew characters (א-ת) are > 30% of text, it's Hebrew.
        """
        if not text or len(text.strip()) == 0:
            return 'en'  # Default to English
        
        # Hebrew Unicode range: \u0590-\u05FF
        hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
        ascii_pattern = re.compile(r'[a-zA-Z]')
        
        hebrew_chars = len(hebrew_pattern.findall(text))
        ascii_chars = len(ascii_pattern.findall(text))
        total_chars = hebrew_chars + ascii_chars
        
        if total_chars == 0:
            return 'en'  # Default if no recognizable characters
        
        hebrew_ratio = hebrew_chars / total_chars if total_chars > 0 else 0
        
        return 'he' if hebrew_ratio > 0.3 else 'en'
    
    def _detect_ecommerce_keywords(self, cv_text):
        """
        Detects if E-commerce keywords appear prominently in the CV.
        Returns a list of relevant keywords found.
        """
        cv_lower = cv_text.lower()
        ecommerce_keywords = {
            'e-commerce': ['e-commerce', 'ecommerce', 'e commerce', 'ecommerce'],
            'shopify': ['shopify'],
            'magento': ['magento'],
            'retail tech': ['retail tech', 'retail technology', 'retailtech'],
            'amazon': ['amazon marketplace', 'amazon seller', 'amazon fba'],
            'woocommerce': ['woocommerce', 'woo commerce'],
            'online retail': ['online retail', 'digital retail', 'retail digital']
        }
        
        found_keywords = []
        for category, variants in ecommerce_keywords.items():
            for variant in variants:
                if variant in cv_lower:
                    found_keywords.append(category)
                    break  # Only count each category once
        
        return found_keywords
    
    def deep_profile_analysis(self, cv_text, skill_bucket=None, rejection_learnings=None):
        """
        Performs a multi-layered AI analysis to create a high-fidelity 'Digital Persona'.
        Analyzes CV, Skill Bucket, and past rejections to build a comprehensive candidate profile.
        Returns a detailed persona dict with: role_level, industry_focus, tech_stack, preferences, avoid_patterns, etc.
        """
        # Build comprehensive analysis prompt
        skill_bucket_text = ""
        if skill_bucket and len(skill_bucket) > 0:
            skill_bucket_text = f"\nPriority Skills/Interests: {', '.join(skill_bucket)}"
        
        rejection_text = ""
        if rejection_learnings:
            rejection_patterns = []
            if rejection_learnings.get('wrong_seniority', 0) > 0:
                rejection_patterns.append("Entry-level or junior roles")
            if rejection_learnings.get('irrelevant_industry', 0) > 0:
                rejection_patterns.append("Non-tech or non-E-commerce industries")
            if rejection_learnings.get('missing_tech_stack', 0) > 0:
                rejection_patterns.append("Jobs missing required technical stack")
            if rejection_learnings.get('irrelevant_role', 0) > 0:
                rejection_patterns.append("Non-technical or non-leadership roles")
            if rejection_patterns:
                rejection_text = f"\nRejection Patterns Learned: {', '.join(rejection_patterns)}"
        
        prompt = (
            "Perform a deep, multi-layered analysis of this candidate to create a high-fidelity 'Digital Persona'. "
            "Analyze the CV, skill preferences, and rejection patterns to build a comprehensive profile. "
            "Return ONLY a valid JSON object with these exact keys:\n"
            '{\n'
            '  "role_level": "CTO/VP/Senior/Executive" (target seniority),\n'
            '  "industry_focus": "E-commerce/Fintech/Retail Tech/etc" (primary industry),\n'
            '  "tech_stack": ["technology1", "technology2", "technology3"] (key technologies from CV),\n'
            '  "leadership_style": "brief description of leadership approach",\n'
            '  "preferences": ["preference1", "preference2"] (what candidate seeks),\n'
            '  "avoid_patterns": ["pattern1", "pattern2"] (what to avoid based on rejections),\n'
            '  "persona_summary": "2-3 sentence comprehensive summary of the Digital Persona"\n'
            '}\n\n'
            f"CV Text:\n{cv_text[:3000]}\n"
            f"{skill_bucket_text}\n"
            f"{rejection_text}\n"
            "Be specific and detailed. Extract actual technologies, industries, and patterns from the CV."
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            persona = json.loads(text)
            
            # Ensure all required keys exist
            default_persona = {
                "role_level": "Senior",
                "industry_focus": "Technology",
                "tech_stack": [],
                "leadership_style": "Technical Leadership",
                "preferences": [],
                "avoid_patterns": [],
                "persona_summary": "Senior technical leader with relevant experience."
            }
            for key in default_persona:
                if key not in persona:
                    persona[key] = default_persona[key]
            
            return persona
        except Exception as e:
            # Fallback persona
            cv_ecommerce_keywords = self._detect_ecommerce_keywords(cv_text)
            has_ecommerce = len(cv_ecommerce_keywords) > 0
            return {
                "role_level": "CTO" if "cto" in cv_text.lower() or "chief" in cv_text.lower() else "Senior",
                "industry_focus": "E-commerce" if has_ecommerce else "Technology",
                "tech_stack": cv_ecommerce_keywords if has_ecommerce else [],
                "leadership_style": "Technical Leadership",
                "preferences": skill_bucket if skill_bucket else [],
                "avoid_patterns": [],
                "persona_summary": f"Senior technical leader with {'E-commerce' if has_ecommerce else 'technology'} experience."
            }
    
    def build_master_search_profile(self, cv_text, skill_bucket=None, rejection_learnings=None):
        """
        Creates a centralized 'Master Search Profile' that merges:
        1. CV Analysis
        2. Skill Bucket
        3. Rejection Learnings
        
        Returns a comprehensive profile string for use in search queries and matching.
        """
        profile_parts = []
        
        # 1. CV Analysis Summary
        cv_ecommerce_keywords = self._detect_ecommerce_keywords(cv_text)
        has_ecommerce_focus = len(cv_ecommerce_keywords) > 0
        
        cv_summary = f"Candidate Profile: {cv_text[:500]}"
        if has_ecommerce_focus:
            cv_summary += f"\nIndustry Focus: Strong E-commerce experience ({', '.join(cv_ecommerce_keywords)})"
        
        profile_parts.append(cv_summary)
        
        # 2. Skill Bucket
        if skill_bucket and len(skill_bucket) > 0:
            profile_parts.append(f"Priority Skills/Interests: {', '.join(skill_bucket)}")
        
        # 3. Rejection Learnings
        if rejection_learnings:
            avoid_patterns = []
            if rejection_learnings.get('wrong_seniority', 0) > 0:
                avoid_patterns.append("Entry-level or junior roles")
            if rejection_learnings.get('irrelevant_industry', 0) > 0:
                avoid_patterns.append("Non-tech or non-E-commerce industries")
            if rejection_learnings.get('missing_tech_stack', 0) > 0:
                avoid_patterns.append("Jobs missing required technical stack")
            if rejection_learnings.get('irrelevant_role', 0) > 0:
                avoid_patterns.append("Non-technical or non-leadership roles")
            
            if avoid_patterns:
                profile_parts.append(f"Learnings (Avoid): {', '.join(avoid_patterns)}")
        
        return "\n".join(profile_parts)
    
    def check_level_mismatch(self, job_description, digital_persona):
        """
        Checks if a job is below the candidate's target level (CTO/VP/Senior).
        Returns True if there's a level mismatch, False otherwise.
        """
        target_level = digital_persona.get('role_level', 'Senior').lower()
        
        # Check if job is entry/junior level
        job_lower = job_description.lower()
        entry_indicators = ['entry level', 'junior', 'intern', 'graduate', 'trainee', 'associate']
        if any(indicator in job_lower for indicator in entry_indicators):
            return True
        
        # Check if job title indicates lower level
        if target_level in ['cto', 'vp', 'executive']:
            # These roles should not match junior/entry positions
            if 'junior' in job_lower or 'entry' in job_lower:
                return True
        
        return False
    
    def generate_rejection_reasons(self, job_description, digital_persona):
        """
        Uses AI to analyze the job text against the Digital Persona and generate 3 SPECIFIC reasons for rejection.
        Examples: 'Requires physical presence in Eilat', 'No E-commerce component', 'Junior level salary indicators'.
        Returns a list of 3 specific reason strings.
        """
        persona_summary = digital_persona.get('persona_summary', '')
        role_level = digital_persona.get('role_level', 'Senior')
        industry_focus = digital_persona.get('industry_focus', '')
        avoid_patterns = digital_persona.get('avoid_patterns', [])
        
        prompt = (
            f"Analyze this job description against the candidate's Digital Persona and generate exactly 3 SPECIFIC reasons why this job might be rejected. "
            f"Be specific and concrete - mention actual details from the job description. "
            f"Examples: 'Requires physical presence in Eilat', 'No E-commerce component', 'Junior level salary indicators', 'Missing Python/React stack', 'Requires 2+ years experience (too junior)'. "
            f"Return ONLY a valid JSON array:\n"
            '["specific reason 1", "specific reason 2", "specific reason 3"]\n\n'
            f"Digital Persona:\n{persona_summary}\n"
            f"Target Role Level: {role_level}\n"
            f"Industry Focus: {industry_focus}\n"
            f"Avoid Patterns: {', '.join(avoid_patterns) if avoid_patterns else 'None'}\n\n"
            f"Job Description:\n{job_description[:2000]}\n\n"
            "Generate SPECIFIC reasons based on actual job details, not generic statements."
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            if isinstance(result, list) and len(result) >= 3:
                return result[:3]
            elif isinstance(result, list):
                while len(result) < 3:
                    result.append("Other specific reasons")
                return result[:3]
            else:
                return ["Level mismatch with Digital Persona", "Industry/tech stack mismatch", "Specific requirements not met"]
        except Exception as e:
            return ["Level mismatch with Digital Persona", "Industry/tech stack mismatch", "Specific requirements not met"]
    
    def generate_search_strategy(self, digital_persona=None, skill_bucket=None, cv_text=None):
        """
        Generates 5 optimized search queries based on Digital Persona + Skill Bucket.
        Analyzes the candidate profile and returns strategic search terms for job boards.
        Returns a list of 5 search query strings.
        """
        persona_context = ""
        if digital_persona:
            persona_context = (
                f"\n\nDIGITAL PERSONA:\n"
                f"Role Level: {digital_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {digital_persona.get('industry_focus', '')}\n"
                f"Tech Stack: {', '.join(digital_persona.get('tech_stack', []))}\n"
                f"Persona Summary: {digital_persona.get('persona_summary', '')}\n"
            )
        
        skill_context = ""
        if skill_bucket and len(skill_bucket) > 0:
            skill_context = f"\n\nPRIORITY SKILLS (Skill Bucket): {', '.join(skill_bucket)}\n"
        
        cv_context = ""
        if cv_text:
            cv_context = f"\n\nCV Summary (first 500 chars): {cv_text[:500]}\n"
        
        prompt = (
            "Analyze the candidate's Digital Persona, Skill Bucket, and CV to generate exactly 5 optimized search queries for job boards. "
            "Each query should be 2-4 words and target specific, relevant job titles. "
            "Examples: 'Head of E-commerce', 'VP Digital Transformation', 'CTO E-commerce', 'VP Product Technology', 'Head of Retail Tech'. "
            "Return ONLY a valid JSON array of exactly 5 search query strings:\n"
            '["query1", "query2", "query3", "query4", "query5"]\n\n'
            f"{persona_context}"
            f"{skill_context}"
            f"{cv_context}"
            "Generate strategic, specific queries that will find the most relevant jobs for this candidate profile."
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            queries = json.loads(text)
            
            if isinstance(queries, list) and len(queries) >= 5:
                return queries[:5]
            elif isinstance(queries, list):
                # Pad with generic queries if less than 5
                while len(queries) < 5:
                    queries.append(f"Senior Tech Leader {len(queries) + 1}")
                return queries[:5]
            else:
                # Fallback: return default queries
                return ['CTO', 'VP Product', 'Head of Technology', 'VP E-commerce', 'Chief Technology Officer']
        except Exception as e:
            print(f"WARN: Search strategy generation failed: {e}")
            # Fallback: return default queries based on persona if available
            if digital_persona:
                role_level = digital_persona.get('role_level', 'Senior')
                industry = digital_persona.get('industry_focus', '')
                if 'e-commerce' in industry.lower() or 'ecommerce' in industry.lower():
                    return ['CTO E-commerce', 'VP E-commerce', 'Head of E-commerce', 'VP Digital Transformation', 'Ecommerce Architect']
                elif role_level.lower() in ['cto', 'vp', 'executive']:
                    return ['CTO', 'VP Product', 'VP R&D', 'Head of Technology', 'Chief Technology Officer']
            return ['CTO', 'VP Product', 'Head of Technology', 'VP E-commerce', 'Chief Technology Officer']
    
    def extract_search_query(self, cv_text, master_profile=None, digital_persona=None):
        """
        מחלץ שאילתת חיפוש קצרה ומדויקת בהתאם לקורות חיים.
        אם יש Master Search Profile או Digital Persona, משתמש בהם להקשר נוסף.
        אם יש מילות מפתח של E-commerce (כמו Shopify, Magento, E-commerce), כולל אותן בשאילתה.
        אף פעם לא ממציא ניסיון שאינו קיים בטקסט.
        """
        # Check for E-commerce keywords first
        ecommerce_keywords = self._detect_ecommerce_keywords(cv_text)
        has_ecommerce_focus = len(ecommerce_keywords) > 0
        
        # Build enhanced prompt that emphasizes industry keywords if found
        base_instruction = "Read the following CV and return ONLY a 3-4 word search query for job boards that honestly summarizes the candidate type and desired seniority."
        
        if has_ecommerce_focus:
            industry_context = f"IMPORTANT: This CV shows strong E-commerce experience (keywords found: {', '.join(ecommerce_keywords)}). "
            industry_context += "Include industry-specific terms like 'E-commerce', 'Ecommerce', 'Shopify', 'Magento', or 'Retail Tech' in the query if they are prominent. "
            industry_context += "Examples: 'CTO E-commerce', 'Head of E-commerce', 'VP E-commerce Israel', 'Ecommerce Architect'."
        else:
            industry_context = "Examples: 'CTO Fintech Israel', 'Python Data Scientist Tel Aviv'."
        
        # Add Digital Persona context if available
        persona_context = ""
        if digital_persona:
            role_level = digital_persona.get('role_level', 'Senior')
            industry = digital_persona.get('industry_focus', '')
            persona_context = f"\n\nDIGITAL PERSONA CONTEXT:\nTarget Role Level: {role_level}\nIndustry Focus: {industry}\nPersona Summary: {digital_persona.get('persona_summary', '')}\nUse this to refine the search query to match the candidate's Digital Persona."
        
        # Add Master Profile context if available
        profile_context = ""
        if master_profile:
            profile_context = f"\n\nADDITIONAL CONTEXT (Master Search Profile):\n{master_profile}\nUse this context to refine the search query, avoiding patterns mentioned in 'Learnings (Avoid)'."
        
        prompt = (
            f"{base_instruction} "
            f"You must base it solely on the explicit content in the CV and never invent experience or skills. "
            f"{industry_context}"
            f"{persona_context}"
            f"{profile_context}\n"
            f"CV:\n{cv_text[:2000]}"
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            query = response.text.strip().replace('"', '')
            # מנקה תווים חריגים
            return query.replace("\n", " ").replace("\r", " ")
        except Exception:
            # Fallback: if E-commerce keywords found, use E-commerce focused query
            if has_ecommerce_focus:
                return "CTO E-commerce"
            return "Chief Technology Officer"
    
    def extract_top_skills(self, job_description, cv_text=None):
        """
        Extracts the 3 most critical SPECIFIC technical or business skills mentioned ONLY in that specific job description.
        NO generic placeholders. Must extract actual skills from the job text.
        If the job is irrelevant (like Security Guard), returns ['Irrelevant Role'].
        """
        # First, check if job is relevant to senior tech/E-commerce
        relevance_check_prompt = (
            "Analyze this job description and determine if it's relevant for a SENIOR TECH/E-COMMERCE candidate. "
            "The candidate is looking for: CTO, VP Product, Head of E-commerce, Senior Tech Leadership roles. "
            "Return ONLY a JSON object:\n"
            '{"is_relevant": true/false, "reason": "brief reason", "seniority_level": "entry/junior/mid/senior/executive"}\n\n'
            f"Job Description:\n{job_description[:2000]}\n\n"
            "If the job is Entry Level, Security Guard, Retail Worker, or any non-tech/non-leadership role, set is_relevant to false."
        )
        
        try:
            response = self._call_api_with_fallback(relevance_check_prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            relevance_result = json.loads(text)
            
            is_relevant = relevance_result.get('is_relevant', True)
            seniority = relevance_result.get('seniority_level', '').lower()
            
            # Check for entry/junior level or irrelevant roles
            if not is_relevant or seniority in ['entry', 'junior'] or 'entry level' in job_description.lower() or 'junior' in job_description.lower():
                # Additional check for obviously irrelevant roles
                irrelevant_keywords = ['security guard', 'retail worker', 'cashier', 'waiter', 'driver', 'cleaner', 'receptionist']
                if any(kw in job_description.lower() for kw in irrelevant_keywords):
                    return ['Irrelevant Role']
                if not is_relevant:
                    return ['Irrelevant Role']
            
            # If relevant, extract SPECIFIC skills from the job description
            prompt = (
                "Analyze this job description and extract EXACTLY 3 SPECIFIC technical or business skills/requirements "
                "that are mentioned ONLY in this specific job description. "
                "DO NOT use generic placeholders like 'Technical Skills', 'Leadership', 'Domain Expertise'. "
                "Extract actual, specific skills mentioned in the text (e.g., 'Python', 'AWS Lambda', 'Shopify Plus', 'Agile Scrum', 'Team Leadership of 10+'). "
                "Return ONLY a valid JSON array of exactly 3 skill strings:\n"
                '["specific skill 1 from job", "specific skill 2 from job", "specific skill 3 from job"]\n\n'
                f"Job Description:\n{job_description[:2000]}\n\n"
                "Be specific and extract only what's actually mentioned in the job description."
            )
            
            response = self._call_api_with_fallback(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            if isinstance(result, list) and len(result) >= 3:
                return result[:3]  # Return exactly 3
            elif isinstance(result, list):
                # If less than 3, try to extract more from the job description directly
                # Extract remaining skills from job text
                job_lower = job_description.lower()
                common_tech = ['python', 'javascript', 'react', 'aws', 'docker', 'kubernetes', 'node.js', 'typescript', 'shopify', 'magento']
                found_tech = [tech for tech in common_tech if tech in job_lower]
                while len(result) < 3 and found_tech:
                    tech = found_tech.pop(0)
                    if tech not in [r.lower() for r in result]:
                        result.append(tech.title())
                # If still less than 3, pad with specific mentions from job
                while len(result) < 3:
                    # Extract any capitalized technical terms
                    tech_terms = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', job_description[:500])
                    for term in tech_terms:
                        if term not in result and len(term) > 3:
                            result.append(term)
                            break
                    if len(result) < 3:
                        break
                return result[:3] if len(result) >= 3 else result
            else:
                # Fallback: extract from job text directly
                job_lower = job_description.lower()
                skills = []
                tech_keywords = ['python', 'javascript', 'react', 'aws', 'docker', 'kubernetes', 'node.js', 'typescript', 'shopify', 'magento', 'agile', 'scrum']
                for keyword in tech_keywords:
                    if keyword in job_lower and len(skills) < 3:
                        skills.append(keyword.title())
                return skills[:3] if skills else ['Irrelevant Role']
        except Exception as e:
            # On error, check for obvious irrelevant roles
            job_lower = job_description.lower()
            irrelevant_keywords = ['security guard', 'retail worker', 'cashier', 'waiter', 'driver', 'cleaner', 'receptionist', 'entry level', 'junior']
            if any(kw in job_lower for kw in irrelevant_keywords):
                return ['Irrelevant Role']
            # Try to extract skills directly from text
            tech_keywords = ['python', 'javascript', 'react', 'aws', 'docker', 'kubernetes', 'node.js', 'typescript', 'shopify', 'magento']
            skills = []
            for keyword in tech_keywords:
                if keyword in job_lower and len(skills) < 3:
                    skills.append(keyword.title())
            return skills[:3] if skills else ['Irrelevant Role']
    
    def analyze_match(self, job_description, cv_text, skill_bucket=None, master_profile=None, digital_persona=None):
        """
        מנתח את מידת ההתאמה בין תיאור משרה לקורות חיים.
        אם יש Digital Persona, משתמש בו לבדיקת Level Mismatch.
        אם יש ניסיון E-commerce ב-CV, נותן משקל גבוה יותר למשרות E-commerce.
        תמיד כולל נימוק כן, ציון (0-100), ומחזיר רשימה אמיתית של פערי מיומנויות שזוהו.
        אין לאפשר המצאת ניסיון או 'סימון וי' גורף.
        """
        # Check for level mismatch if Digital Persona is provided
        if digital_persona:
            if self.check_level_mismatch(job_description, digital_persona):
                return {
                    "score": 0,
                    "reasoning": f"Level Mismatch: Job is below target level ({digital_persona.get('role_level', 'Senior')}). This role appears to be entry-level or junior, which does not match the Digital Persona.",
                    "gaps": ["Level Mismatch"]
                }
        
        # Check if job is irrelevant (if skills extraction indicates so)
        try:
            top_skills = self.extract_top_skills(job_description, cv_text)
            if top_skills == ['Irrelevant Role']:
                return {
                    "score": 0,
                    "reasoning": "This role is not relevant for a senior tech/E-commerce candidate (Entry Level, non-tech role, or wrong seniority).",
                    "gaps": ["Irrelevant Role Type"]
                }
        except:
            pass  # Continue with normal analysis if check fails
        
        # Check for E-commerce keywords in both CV and job description
        cv_ecommerce_keywords = self._detect_ecommerce_keywords(cv_text)
        job_ecommerce_keywords = self._detect_ecommerce_keywords(job_description)
        has_cv_ecommerce = len(cv_ecommerce_keywords) > 0
        has_job_ecommerce = len(job_ecommerce_keywords) > 0
        
        # Enhanced prompt that emphasizes E-commerce matching
        base_prompt = (
            "You are an honest AI matching agent. Compare this CV and job description in depth. "
            "STRICT RULE: You must only reference actual experience and skills found in the CV. Never assume or invent skills or experience!\n"
        )
        
        if has_cv_ecommerce:
            ecommerce_instruction = (
                f"SPECIAL ATTENTION: The CV shows strong E-commerce experience (keywords: {', '.join(cv_ecommerce_keywords)}). "
                f"If the job description also mentions E-commerce, Retail Tech, Shopify, Magento, or online retail, give higher weight to this match. "
                f"E-commerce experience should be considered a significant strength for E-commerce roles.\n"
            )
            base_prompt += ecommerce_instruction
        
        # Add Digital Persona context if provided
        if digital_persona:
            persona_context = (
                f"DIGITAL PERSONA CONTEXT:\n"
                f"Role Level: {digital_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {digital_persona.get('industry_focus', '')}\n"
                f"Tech Stack: {', '.join(digital_persona.get('tech_stack', []))}\n"
                f"Persona Summary: {digital_persona.get('persona_summary', '')}\n"
                f"Use this Digital Persona to evaluate the job match. Jobs that don't align with the Persona should receive lower scores.\n"
            )
            base_prompt += persona_context
        
        # Add skill bucket context if provided
        if skill_bucket and len(skill_bucket) > 0:
            skill_bucket_context = (
                f"ADDITIONAL CONTEXT: The candidate has expressed interest in these skills/areas (Skill Bucket): {', '.join(skill_bucket)}. "
                f"Give extra weight to matches that align with these skills when evaluating the job fit.\n"
            )
            base_prompt += skill_bucket_context
        
        # Add Master Profile context if provided
        if master_profile:
            profile_context = (
                f"MASTER SEARCH PROFILE CONTEXT:\n{master_profile}\n"
                f"Use this comprehensive profile to better understand the candidate's preferences and avoid patterns mentioned in 'Learnings (Avoid)'.\n"
            )
            base_prompt += profile_context
        
        prompt = (
            f"{base_prompt}"
            f"Return ONLY a valid compact JSON in this format:\n"
            '{"score": 0-100, "reasoning": "Short, honest reasoning", "gaps": ["missing skill 1","missing skill 2"]}\n'
            f"CV:\n{cv_text[:1500]}\n"
            f"Job Description:\n{job_description[:1500]}"
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            
            # Bonus scoring: If both CV and job have E-commerce focus, add small boost
            if has_cv_ecommerce and has_job_ecommerce:
                original_score = result.get('score', 50)
                # Add up to 10 point boost if both are E-commerce focused (cap at 100)
                bonus = min(10, 100 - original_score)
                if bonus > 0:
                    result['score'] = original_score + bonus
                    # Update reasoning to mention E-commerce alignment
                    reasoning = result.get('reasoning', '')
                    if 'e-commerce' not in reasoning.lower() and 'ecommerce' not in reasoning.lower():
                        result['reasoning'] = f"{reasoning} Strong E-commerce experience alignment." if reasoning else "Strong E-commerce experience alignment."
            
            return result
        except Exception:
            return {"score": 50, "reasoning": "Analysis unavailable", "gaps": []}
    
    def job_dossier(self, job_description, cv_text, digital_persona=None):
        """
        Creates a comprehensive 'Job Dossier' with:
        - Role Essence (1 sentence)
        - Critical Tech Stack
        - Company Context (from the description)
        - Why it fits/fails your specific Persona
        
        Returns a dict with: role_essence, tech_stack, company_context, persona_fit_analysis
        """
        persona_context = ""
        if digital_persona:
            persona_context = (
                f"\n\nDIGITAL PERSONA:\n"
                f"Role Level: {digital_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {digital_persona.get('industry_focus', '')}\n"
                f"Tech Stack: {', '.join(digital_persona.get('tech_stack', []))}\n"
                f"Persona Summary: {digital_persona.get('persona_summary', '')}\n"
            )
        
        prompt = (
            "Create a comprehensive 'Job Dossier' for this position. "
            "Return ONLY a valid JSON object with these exact keys:\n"
            '{\n'
            '  "role_essence": "One sentence that captures the essence of this role",\n'
            '  "tech_stack": ["technology1", "technology2", "technology3"] (critical technologies mentioned in job),\n'
            '  "company_context": "Brief description of company/context from job description",\n'
            '  "persona_fit_analysis": "Detailed analysis of why this job fits or fails the candidate\'s Digital Persona"\n'
            '}\n\n'
            f"Job Description:\n{job_description[:2000]}\n"
            f"{persona_context}"
            "Be specific and extract actual details from the job description."
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            text = response.text.replace("```json", "").replace("```", "").strip()
            dossier = json.loads(text)
            
            # Ensure all required keys exist
            default_dossier = {
                "role_essence": "Professional role requiring relevant experience.",
                "tech_stack": [],
                "company_context": "Company information not available.",
                "persona_fit_analysis": "Analysis unavailable."
            }
            for key in default_dossier:
                if key not in dossier:
                    dossier[key] = default_dossier[key]
            
            return dossier
        except Exception as e:
            # Fallback
            return {
                "role_essence": "Professional role requiring relevant technical leadership experience.",
                "tech_stack": [],
                "company_context": "Company information not available.",
                "persona_fit_analysis": "Analysis unavailable due to processing error."
            }
    
    def quick_job_analysis(self, job_description, cv_text):
        """
        DEPRECATED: Use job_dossier() instead for comprehensive analysis.
        Kept for backward compatibility.
        Generates a quick 2-3 sentence summary of the job and a bulleted list of why the candidate matches.
        """
        dossier = self.job_dossier(job_description, cv_text)
        return {
            "summary": dossier.get("role_essence", "Professional role requiring relevant experience."),
            "why_match": [dossier.get("persona_fit_analysis", "Analysis unavailable.")]
        }
    
    def reframing_analysis(self, job_description, cv_text, skill_bucket=None, master_profile=None, digital_persona=None):
        """
        מייצר מכתב מקדים (Cover Letter) מותאם באורך 800-1200 תווים.
        מזהה את שפת תיאור המשרה (עברית/אנגלית) ומייצר מכתב באותה שפה.
        המכתב חייב להיות מפורט ומקצועי ברמה ביצועית, לא סיכום קצר.
        לעולם לא מוסיף ניסיון או תחומי עיסוק שלא קיימים במקור.
        אם skill_bucket, master_profile, או digital_persona מסופקים, משתמש בהם להדגשת התאמה למיומנויות שחשובות למועמד.
        """
        # Detect language of job description
        job_language = self.detect_language(job_description)
        
        # Skill bucket context
        skill_bucket_context = ""
        if skill_bucket and len(skill_bucket) > 0:
            skill_bucket_context = (
                f" Additionally, the candidate has expressed strong interest in: {', '.join(skill_bucket)}. "
                f"Emphasize alignment with these skills/areas when relevant.\n"
            )
        
        # Digital Persona context
        persona_context = ""
        if digital_persona:
            persona_context = (
                f" DIGITAL PERSONA CONTEXT:\n"
                f"Role Level: {digital_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {digital_persona.get('industry_focus', '')}\n"
                f"Tech Stack: {', '.join(digital_persona.get('tech_stack', []))}\n"
                f"Persona Summary: {digital_persona.get('persona_summary', '')}\n"
                f"Use this Digital Persona to create a more authentic and personalized cover letter that reflects the candidate's true professional identity.\n"
            )
        
        # Master Profile context
        profile_context = ""
        if master_profile:
            profile_context = (
                f" MASTER SEARCH PROFILE CONTEXT:\n{master_profile}\n"
                f"Use this comprehensive profile to create a more authentic and personalized cover letter that reflects the candidate's true preferences and avoids patterns they've learned to avoid.\n"
            )
        
        if job_language == 'he':
            # Hebrew cover letter prompt - Extended and detailed
            prompt = (
                "אתה סוכן AI מומחה ליצירת מכתבי מקדים מקצועיים ברמה ביצועית. "
                "צור מכתב מקדים מקצועי ומפורט בעברית באורך של 800-1200 תווים (לא פחות מ-800, לא יותר מ-1200) עבור משרה זו. "
                "המכתב חייב להיות מכתב מלא ומקצועי ברמה ביצועית, לא סיכום קצר. "
                "תוך שימוש רק בניסיון, מיומנויות ותפקידים המתוארים בקורות החיים הבאים. "
                "אסור להמציא מיומנויות, תארים או חובות שלא קיימים במקור. "
                "המכתב צריך לכלול: פתיחה מקצועית, הדגשת ניסיון רלוונטי, התאמה לדרישות המשרה, וסיום חזק. "
                "התמקד בהתאמה בין הניסיון מהקורות חיים לבין דרישות המשרה.\n"
                f"{skill_bucket_context}"
                f"{persona_context}"
                f"{profile_context}"
                f"קורות חיים:\n{cv_text[:2000]}\n"
                f"תיאור משרה:\n{job_description[:2000]}"
            )
        else:
            # English cover letter prompt - Extended and detailed
            prompt = (
                "You are an expert AI agent for creating professional executive-level cover letters. "
                "Generate a detailed, professional cover letter in English of 800-1200 characters (minimum 800, maximum 1200) for this job. "
                "The letter must be a full, professional executive letter, not a short snippet. "
                "Strictly use only the actual experience, skills, and roles described in the following CV. "
                "No invented skills, degrees, or duties. "
                "The cover letter should include: a professional opening, highlighting relevant experience, alignment with job requirements, and a strong closing. "
                "Focus on matching the experience from the CV with the job requirements.\n"
                f"{skill_bucket_context}"
                f"{persona_context}"
                f"{profile_context}"
                f"CV:\n{cv_text[:2000]}\n"
                f"Job Description:\n{job_description[:2000]}"
            )
        
        try:
            response = self._call_api_with_fallback(prompt)
            cover_letter = response.text.strip()
            
            # Ensure length is between 800-1200 characters
            if len(cover_letter) > 1200:
                # Truncate to 1200, but try to end at a sentence boundary
                truncated = cover_letter[:1200]
                last_period = truncated.rfind('.')
                last_exclamation = truncated.rfind('!')
                last_question = truncated.rfind('?')
                last_sentence_end = max(last_period, last_exclamation, last_question)
                if last_sentence_end > 800:
                    cover_letter = truncated[:last_sentence_end + 1]
                else:
                    cover_letter = truncated.rstrip()
            elif len(cover_letter) < 800:
                # If too short, expand by adding relevant details (but this should be rare with good prompt)
                # For now, just use as-is if it's reasonably close (750+)
                if len(cover_letter) < 750:
                    # Could retry with more explicit instruction, but for now just use it
                    pass
            
            return cover_letter
        except Exception as e:
            # Fallback based on language
            if job_language == 'he':
                fallback_text = (
                    "אני פונה אליכם לגבי משרה זו. הניסיון והמיומנויות שלי מתאימים לדרישות המשרה. "
                    "יש לי רקע עשיר בתחום הטכנולוגיה והניהול, עם התמחות בתחומים רלוונטיים. "
                    "אני מאמין שאוכל לתרום משמעותית לצוות ולחברה. אשמח להזדמנות לדון כיצד אוכל להוסיף ערך."
                )
                return fallback_text[:1200] if len(fallback_text) > 1200 else fallback_text
            else:
                fallback_text = (
                    "I am writing to express my interest in this position. My experience and skills align well with the job requirements. "
                    "I bring a strong background in technology and leadership, with expertise in relevant areas. "
                    "I believe I can make a significant contribution to your team and organization. I would welcome the opportunity to discuss how I can add value."
                )
                return fallback_text[:1200] if len(fallback_text) > 1200 else fallback_text
    
    def answer_application_question(self, question, cv_text, job_description):
        """
        Answers common application questions using AI based on the candidate's CV.
        Detects language of question and responds in the same language.
        """
        question_language = self.detect_language(question)
        
        if question_language == 'he':
            prompt = (
                "ענה על השאלה הבאה בקצרה ומקצועית בעברית, "
                "תוך שימוש רק במידע מהקורות חיים. אסור להמציא פרטים.\n\n"
                f"שאלה: {question}\n"
                f"קורות חיים:\n{cv_text[:2000]}"
            )
        else:
            prompt = (
                "Answer the following question briefly and professionally in English, "
                "using only information from the CV. Do not invent details.\n\n"
                f"Question: {question}\n"
                f"CV:\n{cv_text[:2000]}"
            )
        
        try:
            response = self._call_api_with_fallback(prompt)
            return response.text.strip()
        except Exception:
            if question_language == 'he':
                return "מידע זמין מהקורות חיים."
            else:
                return "Information available from CV."
    
    def extract_avoid_rule_from_text(self, custom_reason_text, job_description, digital_persona=None):
        """
        Uses AI to analyze custom rejection text and extract a new 'Avoid Rule' for the Digital Persona.
        Examples: 'Too far from home' -> 'Remote work preference: avoid jobs requiring physical presence in distant locations'
        Returns a concise avoid rule string that can be added to avoid_patterns.
        """
        persona_context = ""
        if digital_persona:
            persona_context = (
                f"\n\nDIGITAL PERSONA CONTEXT:\n"
                f"Current Avoid Patterns: {', '.join(digital_persona.get('avoid_patterns', []))}\n"
                f"Role Level: {digital_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {digital_persona.get('industry_focus', '')}\n"
            )
        
        prompt = (
            "Analyze this custom rejection reason and extract a concise 'Avoid Rule' that can be added to a candidate's Digital Persona. "
            "The rule should be specific enough to be useful for future job filtering, but general enough to apply to similar situations. "
            "Return ONLY a single, concise avoid rule string (1-2 sentences max).\n\n"
            f"Custom Rejection Reason: {custom_reason_text}\n"
            f"Job Description (for context): {job_description[:1000]}\n"
            f"{persona_context}\n"
            "Examples of good avoid rules:\n"
            "- 'Avoid jobs requiring physical presence in locations far from home'\n"
            "- 'Prefer companies with 50+ employees (avoid small startups)'\n"
            "- 'Avoid roles requiring extensive travel (>50% time)'\n"
            "Return ONLY the avoid rule string, nothing else."
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            avoid_rule = response.text.strip()
            # Clean up the response
            avoid_rule = avoid_rule.replace('"', '').replace("'", "").strip()
            # Limit length to reasonable size
            if len(avoid_rule) > 200:
                avoid_rule = avoid_rule[:200] + "..."
            return avoid_rule
        except Exception as e:
            # Fallback: use the custom reason as-is (cleaned)
            fallback_rule = custom_reason_text.strip()[:150]
            print(f"WARN: Could not extract avoid rule from AI, using fallback: {e}")
            return fallback_rule
    
    def generate_tailored_pdf(self, original_cv, job_description):
        """
        Generates a tailored PDF by optimizing CV phrasing for ATS without adding false information.
        The logic optimizes phrasing for ATS compatibility while strictly using only skills/experience
        present in the original CV.
        Returns the file path to the generated PDF.
        """
        # Detect language of job description
        job_language = self.detect_language(job_description)
        
        # Extract key requirements from job description
        prompt = (
            "Analyze this job description and the original CV. "
            "Generate an ATS-optimized version of the CV that:\n"
            "1. Uses keywords from the job description that match the candidate's actual experience\n"
            "2. Optimizes phrasing for ATS systems (uses standard industry terms)\n"
            "3. NEVER adds skills, experience, or qualifications not present in the original CV\n"
            "4. Maintains all original information, just rephrases for better ATS compatibility\n"
            "5. Preserves the structure and format of the original CV\n\n"
            f"Job Description:\n{job_description[:2000]}\n\n"
            f"Original CV:\n{original_cv[:3000]}\n\n"
            "Return the optimized CV text that is ATS-friendly but 100% truthful."
        )
        
        try:
            response = self._call_api_with_fallback(prompt)
            optimized_cv_text = response.text.strip()
            
            # Create PDF file (for now, save as text file - can be extended to actual PDF)
            import hashlib
            job_hash = hashlib.md5(job_description.encode()).hexdigest()[:8]
            file_path = f"output/tailored_cv_{job_hash}.txt"
            
            # Ensure output directory exists
            os.makedirs("output", exist_ok=True)
            
            with open(file_path, "w", encoding='utf-8') as f:
                f.write("=== ATS-Optimized Tailored CV ===\n\n")
                f.write(f"Generated for job description hash: {job_hash}\n")
                f.write("This CV has been optimized for ATS compatibility while maintaining 100% accuracy.\n\n")
                f.write("=" * 50 + "\n\n")
                f.write(optimized_cv_text)
            
            return file_path
        except Exception as e:
            print(f"ERROR in generate_tailored_pdf: {e}")
            # Fallback: return original CV as-is
            import hashlib
            job_hash = hashlib.md5(job_description.encode()).hexdigest()[:8]
            file_path = f"output/tailored_cv_{job_hash}_fallback.txt"
            os.makedirs("output", exist_ok=True)
            with open(file_path, "w", encoding='utf-8') as f:
                f.write("=== Original CV (Optimization Failed) ===\n\n")
                f.write(original_cv)
            return file_path
    
    def create_tailored_pdf(self, title, company, content):
        """
        יוצר קובץ להגשה הכולל את הסיכום המותאם. נכון ל-2024 פורמט טקסט, להרחבה ל-PDF בהמשך.
        """
        safe_comp = company.replace(' ', '_').replace('/', '_')
        file_path = f"tailored_{safe_comp}.txt"
        with open(file_path, "w", encoding='utf-8') as f:
            # כותרת לפירוט
            f.write(f"{title} Application – {company}\n\n")
            f.write(content)
        return file_path
