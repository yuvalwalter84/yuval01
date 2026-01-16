"""
Core AI Engine for Vision Stack 2026.
Contains all AI logic, Digital Persona building, and search strategy generation.
"""
import json
import re
import datetime
import os
import math
import requests
from utils import APIClient, detect_language, load_preferences, parse_json_safely, load_feedback_log, save_feedback_log

JOB_ANALYSIS_CACHE_FILE = "job_analysis_cache.json"
PERSONA_CACHE_FILE = "persona_cache.json"  # Will be resolved via get_user_file_path

def load_persona_cache(user_id=None):
    """
    File-Based Cache for Persona: load persona from user-specific persona_cache.json if present.
    Returns dict or None. Never raises.
    
    Args:
        user_id: Optional user_id. If not provided, uses get_user_id() from utils
    """
    try:
        from utils import get_user_file_path, get_user_id
        if user_id is None:
            user_id = get_user_id()
        persona_file = get_user_file_path(PERSONA_CACHE_FILE, user_id)
        if not os.path.exists(persona_file):
            return None
        with open(persona_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and len(data) > 0 else None
    except Exception:
        return None

def save_persona_cache(persona: dict, user_id=None) -> bool:
    """
    File-Based Cache for Persona: atomic write of user-specific persona_cache.json.
    Returns True on success, False otherwise. Never raises.
    
    Args:
        persona: Persona dict to save
        user_id: Optional user_id. If not provided, uses get_user_id() from utils
    """
    try:
        from utils import get_user_file_path, get_user_id
        if not isinstance(persona, dict) or not persona:
            return False
        if user_id is None:
            user_id = get_user_id()
        persona_file = get_user_file_path(PERSONA_CACHE_FILE, user_id)
        tmp_path = persona_file + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(persona, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, persona_file)
        return True
    except Exception:
        try:
            if os.path.exists(persona_file + ".tmp"):
                os.remove(persona_file + ".tmp")
        except Exception:
            pass
        return False

class CoreEngine:
    """
    Core AI engine that handles all AI-powered analysis and generation.
    Uses APIClient from utils for API calls.
    """
    def __init__(self):
        self.api_client = APIClient()
        # Track active model - expose model_id for compatibility
        self.model_id = self.api_client.model_id

    # -------------------------------
    # Personal DNA: Hard Constraints (pre-filter) + Career Horizon (additive)
    # -------------------------------
    def _get_personal_dna_config(self, prefs: dict | None = None) -> dict:
        """
        Get personal DNA config from Supabase (primary) or local preferences (fallback).
        Stateless Engine: Pulls User DNA from DB at runtime.
        """
        try:
            # Try Supabase first (cloud-native)
            from utils import get_supabase_manager, use_supabase
            if use_supabase():
                supabase = get_supabase_manager()
                if supabase:
                    cloud_prefs = supabase.get_preferences()
                    if cloud_prefs:
                        return {
                            "personal_dna": cloud_prefs.get("personal_dna", {}) or {},
                            "career_horizon": cloud_prefs.get("career_horizon", {}) or {}
                        }
            
            # Fallback to local preferences
            prefs = prefs if isinstance(prefs, dict) else load_preferences()
            return {
                "personal_dna": prefs.get("personal_dna", {}) or {},
                "career_horizon": prefs.get("career_horizon", {}) or {}
            }
        except Exception:
            return {"personal_dna": {}, "career_horizon": {}}

    def _hard_constraints_fail(self, job: dict, prefs: dict | None = None) -> tuple[bool, str]:
        """
        Returns (failed, reason). Hard constraints are 'discard immediately' rules.
        Only fails when the job text explicitly contradicts constraints (to avoid false negatives).
        """
        cfg = self._get_personal_dna_config(prefs=prefs)
        hc = (cfg.get("personal_dna", {}) or {}).get("hard_constraints", {}) or {}

        title = str(job.get("title", "") or job.get("role", "") or "").strip()
        company = str(job.get("company", "") or "").strip()
        desc = str(job.get("description", "") or job.get("job_description", "") or "").strip()
        text = f"{title}\n{company}\n{desc}".lower()

        # Work model constraints
        work_model = hc.get("work_model", {}) or {}
        remote_only = bool(work_model.get("remote_only", False))
        hybrid_allowed = bool(work_model.get("hybrid_allowed", True))
        min_home_days = int(work_model.get("min_home_days", 0) or 0)

        # Detect explicit on-site requirements
        onsite_patterns = [
            r"\bfully on[- ]site\b",
            r"\b100% on[- ]site\b",
            r"\bin[- ]office\b",
            r"\bon[- ]site\b",
            r"\b5 days (a|per) week\b",
            r"\bfive days (a|per) week\b",
            r"\bwork from the office\b",
            r"\bmust be in office\b",
            r"\bmust be on site\b"
        ]
        is_explicit_onsite = any(re.search(p, text) for p in onsite_patterns)

        # Detect explicit remote
        remote_patterns = [r"\bremote\b", r"\bwork from home\b", r"\bwfh\b"]
        is_explicit_remote = any(re.search(p, text) for p in remote_patterns)

        if remote_only and is_explicit_onsite and not is_explicit_remote:
            return True, "Hard constraint failed: remote_only but job is explicitly on-site."

        # Hybrid min home days: only fail if job explicitly says on-site daily / 5 days
        if hybrid_allowed and min_home_days >= 2 and is_explicit_onsite and ("5 days" in text or "five days" in text or "fully on-site" in text):
            return True, f"Hard constraint failed: requires at least {min_home_days} WFH days but job is explicitly full on-site."

        # Travel limits
        travel_limits = hc.get("travel_limits", {}) or {}
        overseas_travel = str(travel_limits.get("overseas_travel", "none") or "none").strip().lower()
        if overseas_travel == "none":
            overseas_patterns = [
                r"\binternational travel\b",
                r"\boverseas travel\b",
                r"\btravel abroad\b",
                r"\bglobal travel\b",
                r"\btravel\s+\d{1,3}%\b",
                r"\bfrequent travel\b",
                r"\bextensive travel\b"
            ]
            if any(re.search(p, text) for p in overseas_patterns):
                return True, "Hard constraint failed: overseas_travel=none but job requires international/overseas travel."

        # Location flexibility
        loc = hc.get("location_flexibility", {}) or {}
        allowed_cities = [str(c) for c in (loc.get("allowed_cities", []) or [])]
        israel_only = bool(loc.get("israel_only", True))
        allow_relocation = bool(loc.get("allow_relocation", False))

        if not allow_relocation:
            relocation_patterns = [
                r"\brelocation\b",
                r"\bmust relocate\b",
                r"\brequires relocation\b"
            ]
            if any(re.search(p, text) for p in relocation_patterns):
                return True, "Hard constraint failed: allow_relocation=false but job requires relocation."

        if israel_only:
            non_israel_patterns = [
                r"\busa\b", r"\bunited states\b", r"\bcanada\b", r"\buk\b", r"\bunited kingdom\b",
                r"\beurope\b", r"\bgermany\b", r"\bberlin\b", r"\blondon\b", r"\bnew york\b",
                r"\bparis\b", r"\bamsterdam\b", r"\bsingapore\b", r"\bdubai\b"
            ]
            if any(re.search(p, text) for p in non_israel_patterns) and ("israel" not in text):
                return True, "Hard constraint failed: israel_only=true but job explicitly indicates non-Israel location."

        # Allowed cities: only enforce if an explicit city is mentioned AND job is not remote
        if allowed_cities and (not is_explicit_remote):
            allowed_lower = [c.lower() for c in allowed_cities]
            # detect a city mention among a broader Israeli city set
            # City Alias Map (Hebrew -> English) to prevent false negatives
            city_alias_map = {
                'ת"א': "tel aviv",
                "ת״א": "tel aviv",
                "ת'א": "tel aviv",
                "תא": "tel aviv",
                "תל-אביב": "tel aviv",
                "תל אביב-יפו": "tel aviv",
                "פ'ת": "petah tikva",
                "פתח-תקווה": "petah tikva",
                "פתח תקוה": "petah tikva",
                "תל אביב": "tel aviv",
                "כפר סבא": "kfar saba",
                "פתח תקווה": "petah tikva",
                "פ״ת": "petah tikva",
                "רעננה": "raanana",
                "הרצליה": "herzliya",
                "חיפה": "haifa",
                "ירושלים": "jerusalem",
                "נתניה": "netanya",
                "באר שבע": "beer sheva",
                "מודיעין": "modiin"
            }

            known_il_cities = ["tel aviv", "kfar saba", "petah tikva", "jerusalem", "haifa", "herzliya", "raanana", "netanya", "beer sheva", "modiin"]
            mentioned = None

            # Check Hebrew mentions first
            for he, en in city_alias_map.items():
                if he in (title + "\n" + company + "\n" + desc):
                    mentioned = en
                    break
            # Then English mentions
            if not mentioned:
                for c in known_il_cities:
                    if c in text:
                        mentioned = c
                        break
            if mentioned and mentioned not in allowed_lower:
                return True, f"Hard constraint failed: job mentions city '{mentioned}' not in allowed_cities."

        # Family obligations are highly contextual; do not hard-fail unless explicitly incompatible
        # (We intentionally avoid false negatives here.)
        return False, ""

    def pre_filter_jobs(self, job_text_or_jobs, prefs: dict | None = None) -> tuple[list, list]:
        """
        Hard constraints pre-filter. Must run BEFORE any LLM/AI processing.
        Returns (kept_jobs, dropped_jobs) where dropped jobs include a 'discard_reason'.
        """
        # Support both: a list of job dicts OR a single job text (string) + prefs
        jobs_list = []
        if isinstance(job_text_or_jobs, str):
            jobs_list = [{"title": "", "company": "", "job_url": "", "description": job_text_or_jobs}]
        else:
            jobs_list = list(job_text_or_jobs or [])

        kept = []
        dropped = []
        for j in jobs_list:
            job = j.to_dict() if hasattr(j, "to_dict") else (dict(j) if isinstance(j, dict) else {})
            failed, reason = self._hard_constraints_fail(job, prefs=prefs)
            if failed:
                job["discarded"] = True
                job["discard_reason"] = reason
                dropped.append(job)
            else:
                kept.append(job)
        return kept, dropped

    def _career_horizon_score(self, job_title: str, job_description: str, prefs: dict | None = None) -> float:
        """
        Career Horizon: 0.0..1.0 score based on alignment with target roles (additive only).
        """
        cfg = self._get_personal_dna_config(prefs=prefs)
        ch = cfg.get("career_horizon", {}) or {}
        targets = [str(t).lower() for t in (ch.get("target_roles", []) or [])]
        text = f"{job_title}\n{job_description}".lower()
        if not targets:
            return 0.0
        # exact target role mention
        if any(t in text for t in targets):
            return 1.0
        # partial strategic roles (transferable)
        partial = ["cto office", "principal", "staff", "architect", "head of", "director", "vp"]
        if any(p in text for p in partial):
            return 0.6
        return 0.0

    def _career_horizon_bonus_points(self, job_title: str, job_description: str, prefs: dict | None = None) -> int:
        cfg = self._get_personal_dna_config(prefs=prefs)
        ch = cfg.get("career_horizon", {}) or {}
        weight = float(ch.get("additive_weight", 0.0) or 0.0)
        weight = max(0.0, min(weight, 1.0))
        s = self._career_horizon_score(job_title, job_description, prefs=prefs)
        bonus = int(round(100.0 * s * weight))
        return max(0, min(bonus, 30))  # cap bonus to avoid overriding base score

    # -------------------------------
    # Strict Caching (Never analyze same job twice)
    # -------------------------------
    def _load_job_analysis_cache(self) -> dict:
        try:
            if not os.path.exists(JOB_ANALYSIS_CACHE_FILE):
                return {}
            with open(JOB_ANALYSIS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_job_analysis_cache(self, cache: dict) -> None:
        try:
            if not isinstance(cache, dict):
                return
            tmp_path = JOB_ANALYSIS_CACHE_FILE + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, JOB_ANALYSIS_CACHE_FILE)
        except Exception:
            # Never crash due to cache write
            try:
                if os.path.exists(JOB_ANALYSIS_CACHE_FILE + ".tmp"):
                    os.remove(JOB_ANALYSIS_CACHE_FILE + ".tmp")
            except Exception:
                pass

    def _get_cached_job_analysis(self, job_url: str):
        if not job_url:
            return None
        cache = self._load_job_analysis_cache()
        return cache.get(str(job_url).strip())

    def _set_cached_job_analysis(self, job_url: str, analysis: dict) -> None:
        if not job_url or not isinstance(analysis, dict):
            return
        key = str(job_url).strip()
        cache = self._load_job_analysis_cache()
        # NEVER analyze same job twice: once present, do not overwrite
        if key in cache:
            return
        cache[key] = analysis
        self._save_job_analysis_cache(cache)
    
    def merge_cv_data(self, cv_texts_list):
        """
        Multi-CV Management: Merges text from multiple uploaded CVs into a single comprehensive 'Master Profile'.
        
        Args:
            cv_texts_list: List of CV text strings from multiple uploaded PDFs
        
        Returns:
            str: Merged comprehensive Master Profile text
        """
        # Validation: Add safety check to return empty string if cv_texts_list is empty or None
        if not cv_texts_list or len(cv_texts_list) == 0:
            return ""
        
        if len(cv_texts_list) == 1:
            return cv_texts_list[0]
        
        # Merge multiple CVs with clear separation
        merged_text = "=== MULTI-CV MASTER PROFILE ===\n\n"
        for i, cv_text in enumerate(cv_texts_list, 1):
            merged_text += f"--- CV {i} ---\n\n{cv_text}\n\n"
        
        merged_text += "=== END MULTI-CV MASTER PROFILE ===\n\n"
        merged_text += "NOTE: This profile combines experience from multiple CVs. All skills, roles, and experiences from all CVs should be considered when matching jobs."
        
        return merged_text
    
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

    def extract_professional_dna_from_cv(self, cv_text: str) -> dict:
        """
        Persona Re-Validation: deterministically extract "Professional DNA" from the CV text
        to give the system more structured signal (without inventing anything).
        Returns dict: {target_industries: [...], custom_skills: "..."}
        """
        try:
            text = (cv_text or "")
            tl = text.lower()

            # Industries: only mark if the keyword appears in the CV
            industries_map = {
                "E-commerce": ["e-commerce", "ecommerce", "shopify", "magento", "woocommerce", "online retail", "retail tech"],
                "Retail": ["retail", "retail tech", "commerce"],
                "Fintech": ["fintech", "payments", "bank", "banking", "credit", "lending"],
                "SaaS": ["saas", "b2b", "subscription"],
                "Cyber": ["cyber", "security", "infosec", "soc", "siem"],
                "Healthcare Tech": ["healthcare", "health tech", "medtech", "hospital"],
                "EdTech": ["edtech", "education"],
                "PropTech": ["proptech", "real estate"],
                "Gaming": ["gaming", "game"],
                "Media Tech": ["media", "adtech", "martech"]
            }
            target_industries = []
            for name, kws in industries_map.items():
                if any(k in tl for k in kws):
                    target_industries.append(name)

            # Skills/keywords: only include if literally present (case-insensitive)
            skill_terms = [
                "shopify","magento","woocommerce","e-commerce","ecommerce","retail tech",
                "aws","gcp","azure","kubernetes","docker","terraform","ci/cd","microservices",
                "python","java","javascript","typescript","node","react","sql","postgres","mysql",
                "redis","kafka","spark","etl","ml","ai","genai","llm",
                "architecture","scalability","distributed systems","leadership","cto","vp","director","head of"
            ]
            found = []
            for term in skill_terms:
                if term in tl:
                    found.append(term)
            # de-dup while keeping order
            seen = set()
            uniq = []
            for x in found:
                if x not in seen:
                    uniq.append(x)
                    seen.add(x)

            return {
                "target_industries": target_industries,
                "custom_skills": ", ".join(uniq[:40])
            }
        except Exception:
            return {"target_industries": [], "custom_skills": ""}
    
    def deep_profile_analysis(self, cv_text, skill_bucket=None, rejection_learnings=None, existing_persona=None):
        """
        Performs a multi-layered AI analysis to create a high-fidelity 'Digital Persona'.
        Analyzes CV, Skill Bucket, and past rejections to build a comprehensive candidate profile.
        Enhanced Persona Memory: If existing_persona is provided, expands it additively instead of overwriting.
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
        
        # Enhanced Persona Memory: If existing_persona exists, expand it additively
        existing_context = ""
        if existing_persona:
            existing_context = (
                f"\n\nEXISTING DIGITAL PERSONA (Expand additively, do not overwrite):\n"
                f"Role Level: {existing_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {existing_persona.get('industry_focus', 'Technology')}\n"
                f"Tech Stack: {', '.join(existing_persona.get('tech_stack', []))}\n"
                f"Preferences: {', '.join(existing_persona.get('preferences', []))}\n"
                f"Persona Summary: {existing_persona.get('persona_summary', '')}\n"
                f"IMPORTANT: Expand this persona with new information from the CV. Merge tech stacks, combine preferences, "
                f"and enhance the summary. Do NOT overwrite - ADD to existing knowledge."
            )
        
        prompt = (
            "CRITICAL: You MUST return ONLY valid JSON. No markdown, no code blocks, no explanations outside the JSON.\n\n"
            "Perform a deep, multi-layered analysis of this candidate to create a high-fidelity 'Digital Persona'. "
            "Analyze the CV, skill preferences, and rejection patterns to build a comprehensive profile. "
            f"{'EXPAND the existing persona additively' if existing_persona else 'Create a new persona'}. "
            "\n\n"
            "DYNAMIC DOMAIN EXTRACTION: FIRST identify the candidate's PRIMARY DOMAIN from the CV:\n"
            "- If the CV shows Marketing/Digital Marketing/MarTech experience, primary_domain = 'Marketing'\n"
            "- If the CV shows Sales/Revenue/BD experience, primary_domain = 'Sales'\n"
            "- If the CV shows Engineering/Software/Technology experience, primary_domain = 'Engineering'\n"
            "- If the CV shows Product/Product Management experience, primary_domain = 'Product'\n"
            "- If the CV shows Operations/Operations Management, primary_domain = 'Operations'\n"
            "- Extract the ACTUAL domain from the CV content, NOT from assumptions\n\n"
            "Return ONLY a valid JSON object with these exact keys (no additional text, no markdown formatting):\n"
            '{\n'
            '  "primary_domain": "Marketing/Sales/Engineering/Product/Operations/etc" (extract from CV),\n'
            '  "role_level": "CTO/VP/Senior/Executive/Mid-level" (extract from CV),\n'
            '  "industry_focus": "Specific industry based on primary_domain" (e.g., "Digital Marketing" for Marketing, "Software Engineering" for Engineering),\n'
            '  "tech_stack": ["technology1", "technology2", "technology3"] (actual tech from CV),\n'
            '  "leadership_style": "brief description of leadership approach",\n'
            '  "preferences": ["preference1", "preference2"],\n'
            '  "avoid_patterns": ["pattern1", "pattern2"],\n'
            '  "persona_summary": "2-3 sentence comprehensive summary of the Digital Persona",\n'
            '  "latent_capabilities": ["capability1", "capability2", "capability3", "capability4", "capability5"] (3-5 transferable skills NOT explicitly named in the CV but inferable from experience. Extract ONLY from current CV text, do NOT use old cached data)\n'
            '}\n\n'
            "STRICT JSON FORMAT REQUIREMENTS:\n"
            "- Return ONLY the JSON object, nothing else\n"
            "- Do NOT wrap in markdown code blocks (```json or ```)\n"
            "- Do NOT add explanatory text before or after the JSON\n"
            "- Ensure all string values are properly quoted\n"
            "- Ensure all arrays are properly formatted\n"
            "- The response must be parseable by json.loads() directly\n\n"
            "CRITICAL: Extract the ACTUAL domain from the CV - do NOT default to 'Technology' or 'Engineering'.\n"
            "If the CV shows Marketing experience, primary_domain MUST be 'Marketing' and industry_focus MUST reflect Marketing.\n"
            "If the CV shows Sales experience, primary_domain MUST be 'Sales' and industry_focus MUST reflect Sales.\n\n"
            f"CV Text:\n{cv_text[:3000]}\n"
            f"{skill_bucket_text}\n"
            f"{rejection_text}\n"
            f"{existing_context}\n"
            "Be specific and detailed. Extract actual domain, technologies, industries, and patterns from the CV.\n\n"
            "REMEMBER: Return ONLY the JSON object, no markdown, no code blocks, no additional text."
        )
        
        try:
            response = self.api_client.call_api_with_fallback(prompt)
            # Assertive API Path: Use parse_json_safely to clean triple backticks and retry
            persona = parse_json_safely(response.text) or {}
            
            # Ensure all required keys exist
            # Dynamic Domain Extraction: Extract primary_domain from CV if not present
            default_persona = {
                "primary_domain": "Engineering",  # Default fallback, but should be extracted from CV
                "role_level": "Senior",
                "industry_focus": "Technology Leadership / General Tech",  # Will be updated based on primary_domain
                "tech_stack": [],
                "leadership_style": "Technical Leadership",
                "preferences": [],
                "avoid_patterns": [],
                "persona_summary": "Senior professional with relevant experience.",
                "latent_capabilities": []  # Will be populated by AI analysis
            }
            
            # If primary_domain was extracted, use it to set appropriate industry_focus
            if 'primary_domain' not in persona or not persona.get('primary_domain'):
                # Try to infer from industry_focus or persona_summary
                extracted_domain = None
                industry = persona.get('industry_focus', '').lower()
                summary = persona.get('persona_summary', '').lower()
                
                if 'marketing' in industry or 'marketing' in summary or 'martech' in summary:
                    extracted_domain = 'Marketing'
                elif 'sales' in industry or 'sales' in summary or 'revenue' in summary:
                    extracted_domain = 'Sales'
                elif 'product' in industry or 'product' in summary:
                    extracted_domain = 'Product'
                elif 'operations' in industry or 'operations' in summary:
                    extracted_domain = 'Operations'
                elif 'engineering' in industry or 'engineering' in summary or 'software' in summary:
                    extracted_domain = 'Engineering'
                
                if extracted_domain:
                    persona['primary_domain'] = extracted_domain
                    # Update industry_focus based on primary_domain if it's generic
                    if persona.get('industry_focus', '').lower() in ['technology leadership / general tech', 'technology', 'tech']:
                        if extracted_domain == 'Marketing':
                            persona['industry_focus'] = 'Digital Marketing / MarTech'
                        elif extracted_domain == 'Sales':
                            persona['industry_focus'] = 'Sales / Revenue Operations'
                        elif extracted_domain == 'Product':
                            persona['industry_focus'] = 'Product Management / Product Leadership'
                        elif extracted_domain == 'Operations':
                            persona['industry_focus'] = 'Operations Management'
            
            # Ensure primary_domain is set (use extracted or default)
            if 'primary_domain' not in persona or not persona.get('primary_domain'):
                persona['primary_domain'] = default_persona['primary_domain']
            for key in default_persona:
                if key not in persona:
                    persona[key] = default_persona[key]
            
            # Ensure latent_capabilities exists and is a list
            if 'latent_capabilities' not in persona or not isinstance(persona.get('latent_capabilities'), list):
                persona['latent_capabilities'] = []
            
            # If latent_capabilities is empty, generate them separately
            # Versatility Check: Extract ONLY from current CV text and current user ambitions
            if not persona.get('latent_capabilities'):
                try:
                    # Get current user ambitions (not cached)
                    current_ambitions = None
                    try:
                        from utils import load_preferences, get_user_id
                        user_id = get_user_id()
                        preferences = load_preferences(user_id)
                        current_ambitions = preferences.get('user_identity', {}).get('user_ambitions', '')
                    except:
                        pass
                    
                    # Extract latent capabilities ONLY from current CV and current ambitions
                    latent_capabilities = self.identify_latent_capabilities(
                        cv_text, 
                        digital_persona=persona, 
                        user_ambitions=current_ambitions
                    )
                    persona['latent_capabilities'] = latent_capabilities
                    print(f"✅ Extracted {len(latent_capabilities)} latent capabilities from current CV only")
                except Exception as latent_error:
                    print(f"⚠️ Error identifying latent capabilities: {latent_error}")
                    persona['latent_capabilities'] = []
            
            # Save persona to database (primary) for persistence
            try:
                from utils import get_db_manager, get_user_id
                db = get_db_manager()
                user_id = get_user_id()
                
                # Get user ambitions from preferences
                preferences = None
                try:
                    from utils import load_preferences
                    preferences = load_preferences(user_id)
                except:
                    pass
                
                ambitions = None
                if preferences:
                    ambitions = preferences.get('user_identity', {}).get('user_ambitions', '')
                
                db.save_persona(
                    user_id=user_id,
                    profile_summary=persona.get('persona_summary', ''),
                    latent_capabilities=persona.get('latent_capabilities', []),
                    ambitions=ambitions,
                    digital_persona=persona
                )
                print(f"✅ Saved persona to database")
            except Exception as db_error:
                print(f"⚠️ Failed to save persona to database: {db_error}")
            
            # Identity Reset: Only merge if existing_persona is provided (not None)
            # When existing_persona=None, we're doing a fresh analysis - NO merging to prevent data leakage
            if existing_persona is not None:
                # Smart Merge: When AI generates a new persona summary, merge it with the old one instead of replacing
                if existing_persona.get('persona_summary'):
                    old_summary = existing_persona.get('persona_summary', '')
                    new_summary = persona.get('persona_summary', '')
                    
                    # Merge summaries: Combine old context with new insights
                    if old_summary and new_summary and old_summary != new_summary:
                        # Smart Merge: Combine both summaries intelligently
                        merged_summary = f"{old_summary} {new_summary}"
                        # Limit length to avoid excessive text (max 500 chars for summary)
                        if len(merged_summary) > 500:
                            # Keep first part of old summary and new summary
                            old_part = old_summary[:250] if len(old_summary) > 250 else old_summary
                            new_part = new_summary[:250] if len(new_summary) > 250 else new_summary
                            merged_summary = f"{old_part} {new_part}"
                        persona['persona_summary'] = merged_summary
                        print(f"✅ Smart Merge: Combined persona summaries (old: {len(old_summary)} chars, new: {len(new_summary)} chars, merged: {len(merged_summary)} chars)")
                    elif old_summary and not new_summary:
                        # If new summary is empty, keep old one
                        persona['persona_summary'] = old_summary
                        print("✅ Smart Merge: Preserved old persona summary (new summary was empty)")
                
                # Smart Merge: Merge tech_stack, preferences, and avoid_patterns additively
                # Merge tech_stack (combine without duplicates)
                if existing_persona.get('tech_stack'):
                    existing_tech = set(existing_persona.get('tech_stack', []))
                    new_tech = set(persona.get('tech_stack', []))
                    persona['tech_stack'] = list(existing_tech.union(new_tech))
                
                # Merge preferences (combine without duplicates)
                if existing_persona.get('preferences'):
                    existing_prefs = set(existing_persona.get('preferences', []))
                    new_prefs = set(persona.get('preferences', []))
                    persona['preferences'] = list(existing_prefs.union(new_prefs))
                
                # Merge avoid_patterns (combine without duplicates)
                if existing_persona.get('avoid_patterns'):
                    existing_avoid = set(existing_persona.get('avoid_patterns', []))
                    new_avoid = set(persona.get('avoid_patterns', []))
                    persona['avoid_patterns'] = list(existing_avoid.union(new_avoid))
            else:
                # Fresh analysis: No merging - persona is built ONLY from current CV
                print("✅ Fresh persona analysis - no merging with old data (existing_persona=None)")
            
            # Force reset: If industry_focus is a specialized niche and user hasn't explicitly set it, reset to default
            # Check if user has explicitly set industry in preferences
            try:
                preferences = load_preferences()
                professional_dna = preferences.get('professional_dna', {})
                target_industries = professional_dna.get('target_industries', [])
                
                # If user hasn't set target industries, force default to 'Technology Leadership / General Tech'
                if not target_industries or len(target_industries) == 0:
                    specialized_niches = ['e-commerce', 'fintech', 'retail tech', 'saas', 'cyber', 'healthcare tech', 'edtech', 'proptech', 'gaming', 'media tech']
                    current_industry = persona.get('industry_focus', '').lower()
                    
                    # If current industry is a specialized niche, reset to default
                    if any(niche in current_industry for niche in specialized_niches):
                        persona['industry_focus'] = "Technology Leadership / General Tech"
                        print(f"DEBUG: Reset industry_focus from '{persona.get('industry_focus')}' to 'Technology Leadership / General Tech' (user hasn't explicitly set target industries)")
            except Exception as e:
                print(f"WARN: Could not check preferences for industry reset: {e}")
                # Default to general tech if check fails
                persona['industry_focus'] = "Technology Leadership / General Tech"
            
            # File-Based Cache: persist persona for recovery across Streamlit refreshes
            try:
                save_persona_cache(persona)
            except Exception:
                pass

            # Persona Re-Validation: if persona_summary is too short, expand it deterministically
            # to ensure there is enough "meat" for downstream prompts (without inventing facts).
            try:
                ps = str(persona.get("persona_summary", "") or "").strip()
                if len(ps) < 200:
                    tech = persona.get("tech_stack", []) or []
                    prefs = persona.get("preferences", []) or []
                    avoids = persona.get("avoid_patterns", []) or []
                    leadership = str(persona.get("leadership_style", "") or "").strip()
                    role_level = str(persona.get("role_level", "") or "").strip()
                    industry = str(persona.get("industry_focus", "") or "").strip()
                    cv_hint = (cv_text or "")[:400].replace("\n", " ").strip()
                    persona["persona_summary"] = (
                        f"{role_level} technology leader. Focus: {industry}. "
                        f"Leadership: {leadership}. "
                        f"Key tech/themes observed in CV: {', '.join(tech[:10]) if tech else 'N/A'}. "
                        f"Preferences: {', '.join(prefs[:8]) if prefs else 'N/A'}. "
                        f"Avoid: {', '.join(avoids[:6]) if avoids else 'N/A'}. "
                        f"CV excerpt: {cv_hint}"
                    )
                    # re-save cache with enriched summary
                    save_persona_cache(persona)
            except Exception:
                pass

            return persona
        except Exception as e:
            # Fallback persona - Reset Industry Focus: Default to 'Technology Leadership / General Tech'
            cv_ecommerce_keywords = self._detect_ecommerce_keywords(cv_text)
            has_ecommerce = len(cv_ecommerce_keywords) > 0
            fallback_persona = {
                "role_level": "CTO" if "cto" in cv_text.lower() or "chief" in cv_text.lower() else "Senior",
                "industry_focus": "Technology Leadership / General Tech",  # Default to general tech, not specialized
                "tech_stack": cv_ecommerce_keywords if has_ecommerce else [],
                "leadership_style": "Technical Leadership",
                "preferences": skill_bucket if skill_bucket else [],
                "avoid_patterns": [],
                "persona_summary": f"Senior technical leader with technology experience."
            }
            try:
                save_persona_cache(fallback_persona)
            except Exception:
                pass
            return fallback_persona
    
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
            response = self.api_client.call_api_with_fallback(prompt)
            # Bulletproof JSON: Use parse_json_safely for ALL AI outputs
            result = parse_json_safely(response.text) if response and hasattr(response, 'text') and response.text else None
            
            # No Empty Responses: If result is empty or None, return default reasons
            if not result or (isinstance(result, list) and len(result) == 0):
                return ["Level mismatch with Digital Persona", "Industry/tech stack mismatch", "Specific requirements not met"]
            
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
            "CRITICAL: Every query MUST include mandatory tech context (e.g., 'Software', 'Tech', 'Digital', 'Technology', 'Engineering') to filter out non-tech roles like VP Sales in traditional factories. "
            "Examples: 'Head of E-commerce Technology', 'VP Digital Transformation', 'CTO E-commerce Software', 'VP Product Technology', 'Head of Retail Tech'. "
            "Return ONLY a valid JSON array of exactly 5 search query strings:\n"
            '["query1", "query2", "query3", "query4", "query5"]\n\n'
            f"{persona_context}"
            f"{skill_context}"
            f"{cv_context}"
            "Generate strategic, specific queries that will find the most relevant jobs for this candidate profile."
        )
        
        try:
            response = self.api_client.call_api_with_fallback(prompt)
            # Safe JSON Parsing: Use parse_json_safely to extract JSON between { and } and remove triple backticks
            queries = parse_json_safely(response.text) or []
            
            if isinstance(queries, list) and len(queries) >= 5:
                # Search Refinement: Append mandatory context to each query
                refined_queries = []
                for query in queries[:5]:
                    query_lower = query.lower()
                    mandatory_contexts = ['software', 'tech', 'digital', 'technology', 'engineering', 'it', 'ict']
                    has_tech_context = any(ctx in query_lower for ctx in mandatory_contexts)
                    
                    if not has_tech_context:
                        # Append most appropriate context
                        if 'cto' in query_lower or 'chief' in query_lower:
                            query = f"{query} Technology"
                        elif 'vp' in query_lower or 'vice president' in query_lower:
                            query = f"{query} Tech"
                        elif 'head' in query_lower or 'director' in query_lower:
                            query = f"{query} Software"
                        else:
                            query = f"{query} Digital"
                    refined_queries.append(query)
                return refined_queries
            elif isinstance(queries, list):
                # Pad with generic queries if less than 5 (with mandatory context)
                while len(queries) < 5:
                    queries.append(f"Senior Tech Leader Software {len(queries) + 1}")
                # Apply mandatory context to all queries
                refined_queries = []
                for query in queries[:5]:
                    query_lower = query.lower()
                    mandatory_contexts = ['software', 'tech', 'digital', 'technology', 'engineering', 'it', 'ict']
                    has_tech_context = any(ctx in query_lower for ctx in mandatory_contexts)
                    if not has_tech_context:
                        query = f"{query} Technology"
                    refined_queries.append(query)
                return refined_queries
            else:
                # Fallback: return default queries (with mandatory context)
                return ['CTO Technology', 'VP Product Tech', 'Head of Technology Software', 'VP E-commerce Digital', 'Chief Technology Officer Software']
        except Exception as e:
            print(f"WARN: Search strategy generation failed: {e}")
            # Fallback: return default queries based on persona if available (with mandatory context)
            if digital_persona:
                role_level = digital_persona.get('role_level', 'Senior')
                industry = digital_persona.get('industry_focus', '')
                if 'e-commerce' in industry.lower() or 'ecommerce' in industry.lower():
                    return ['CTO E-commerce Technology', 'VP E-commerce Software', 'Head of E-commerce Digital', 'VP Digital Transformation Tech', 'Ecommerce Architect Software']
                elif role_level.lower() in ['cto', 'vp', 'executive']:
                    return ['CTO Technology', 'VP Product Tech', 'VP R&D Software', 'Head of Technology Digital', 'Chief Technology Officer Software']
            return ['CTO Technology', 'VP Product Tech', 'Head of Technology Software', 'VP E-commerce Digital', 'Chief Technology Officer Software']
    
    def identify_potential_roles(self, cv_text, digital_persona=None, skill_bucket=None):
        """
        Identifies 5-10 strategic job titles/roles based on CV analysis.
        Uses Digital Persona and Skill Bucket to generate targeted role titles.
        Returns a list of 5-10 strategic role titles (e.g., 'CTO E-commerce', 'VP Product', 'Head of Digital Transformation').
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
        
        # Dynamic Domain Extraction: Use primary_domain to limit roles strictly to that domain
        primary_domain = "Engineering"  # Default fallback
        if digital_persona:
            primary_domain = digital_persona.get('primary_domain', 'Engineering')
            industry_focus = digital_persona.get('industry_focus', '')
        
        # Build domain-specific examples based on primary_domain
        domain_examples = {
            'Marketing': ['VP Marketing', 'Head of Digital Marketing', 'CMO', 'VP Growth', 'Head of MarTech', 'Director of Marketing'],
            'Sales': ['VP Sales', 'Head of Revenue', 'CRO', 'VP Business Development', 'Head of Sales', 'Director of Sales'],
            'Product': ['VP Product', 'Head of Product', 'CPO', 'VP Product Management', 'Head of Product Strategy', 'Director of Product'],
            'Engineering': ['CTO', 'VP Engineering', 'Head of Engineering', 'Chief Technology Officer', 'VP Technology', 'Director of Engineering'],
            'Operations': ['VP Operations', 'Head of Operations', 'COO', 'VP Operations Management', 'Head of Business Operations', 'Director of Operations']
        }
        
        examples = domain_examples.get(primary_domain, domain_examples['Engineering'])
        
        prompt = (
            f"Analyze the candidate's CV to identify 5-10 strategic job titles/roles that best match their experience and expertise. "
            f"CRITICAL: The candidate's PRIMARY DOMAIN is '{primary_domain}'. ALL roles MUST be strictly limited to this domain. "
            f"For example, if primary_domain is 'Marketing', return only Marketing roles (VP Marketing, Head of Digital Marketing, CMO, etc.). "
            f"If primary_domain is 'Sales', return only Sales roles (VP Sales, Head of Revenue, CRO, etc.). "
            f"DO NOT suggest Engineering/CTO roles if the domain is Marketing or Sales.\n\n"
            f"Focus on senior/executive level roles (VP, Head of, Director, Chief, C-level) that align with the candidate's {primary_domain} background. "
            f"Return ONLY a valid JSON array of 5-10 strategic role titles:\n"
            '["Role Title 1", "Role Title 2", "Role Title 3", ...]\n\n'
            f"Examples for {primary_domain} domain: {', '.join(examples)}\n"
            f"{persona_context}"
            f"{skill_context}"
            f"CV Summary (first 1000 chars): {cv_text[:1000]}\n"
            f"Generate strategic, specific {primary_domain} role titles that accurately reflect the candidate's experience and expertise level."
        )
        
        try:
            response = self.api_client.call_api_with_fallback(prompt)
            # Assertive API Path: Use parse_json_safely to clean triple backticks and retry
            roles = parse_json_safely(response.text) or []
            
            if isinstance(roles, list):
                # Ensure we have 5-10 roles
                if len(roles) > 10:
                    roles = roles[:10]
                elif len(roles) < 5:
                    # Pad with domain-specific default roles if less than 5
                    primary_domain = digital_persona.get('primary_domain', 'Engineering') if digital_persona else 'Engineering'
                    domain_defaults = {
                        'Marketing': ['VP Marketing', 'Head of Digital Marketing', 'CMO', 'VP Growth', 'Head of MarTech'],
                        'Sales': ['VP Sales', 'Head of Revenue', 'CRO', 'VP Business Development', 'Head of Sales'],
                        'Product': ['VP Product', 'Head of Product', 'CPO', 'VP Product Management', 'Head of Product Strategy'],
                        'Engineering': ['CTO', 'VP Engineering', 'Head of Engineering', 'Chief Technology Officer', 'VP Technology'],
                        'Operations': ['VP Operations', 'Head of Operations', 'COO', 'VP Operations Management', 'Head of Business Operations']
                    }
                    default_roles = domain_defaults.get(primary_domain, domain_defaults['Engineering'])
                    for default_role in default_roles:
                        if default_role not in roles and len(roles) < 10:
                            roles.append(default_role)
                return roles[:10]
            else:
                # Fallback: return domain-specific default roles
                primary_domain = digital_persona.get('primary_domain', 'Engineering') if digital_persona else 'Engineering'
                domain_defaults = {
                    'Marketing': ['VP Marketing', 'Head of Digital Marketing', 'CMO', 'VP Growth', 'Head of MarTech'],
                    'Sales': ['VP Sales', 'Head of Revenue', 'CRO', 'VP Business Development', 'Head of Sales'],
                    'Product': ['VP Product', 'Head of Product', 'CPO', 'VP Product Management', 'Head of Product Strategy'],
                    'Engineering': ['CTO', 'VP Engineering', 'Head of Engineering', 'Chief Technology Officer', 'VP Technology'],
                    'Operations': ['VP Operations', 'Head of Operations', 'COO', 'VP Operations Management', 'Head of Business Operations']
                }
                return domain_defaults.get(primary_domain, domain_defaults['Engineering'])
        except Exception as e:
            print(f"⚠️ Error identifying potential roles: {e}")
            # Fallback: return domain-specific default roles
            primary_domain = digital_persona.get('primary_domain', 'Engineering') if digital_persona else 'Engineering'
            domain_defaults = {
                'Marketing': ['VP Marketing', 'Head of Digital Marketing', 'CMO', 'VP Growth', 'Head of MarTech'],
                'Sales': ['VP Sales', 'Head of Revenue', 'CRO', 'VP Business Development', 'Head of Sales'],
                'Product': ['VP Product', 'Head of Product', 'CPO', 'VP Product Management', 'Head of Product Strategy'],
                'Engineering': ['CTO', 'VP Engineering', 'Head of Engineering', 'Chief Technology Officer', 'VP Technology'],
                'Operations': ['VP Operations', 'Head of Operations', 'COO', 'VP Operations Management', 'Head of Business Operations']
            }
            return domain_defaults.get(primary_domain, domain_defaults['Engineering'])
    
    def identify_latent_capabilities(self, cv_text, digital_persona=None, user_ambitions=None):
        """
        Versatility Check: Identify latent capabilities ONLY from current CV text and current user ambitions.
        Do NOT use old cached data.
        
        Args:
            cv_text: Current CV text (ONLY source for extraction)
            digital_persona: Current digital persona (optional, for context only)
            user_ambitions: Current user ambitions (optional, for context only)
        
        Returns:
            List of 3-5 latent capability strings extracted from current CV only
        """
        persona_context = ""
        if digital_persona:
            persona_context = (
                f"\n\nDIGITAL PERSONA (for context only - extract capabilities from CV, not persona):\n"
                f"Primary Domain: {digital_persona.get('primary_domain', 'Unknown')}\n"
                f"Role Level: {digital_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {digital_persona.get('industry_focus', '')}\n"
                f"Tech Stack (explicit): {', '.join(digital_persona.get('tech_stack', []))}\n"
                f"Persona Summary: {digital_persona.get('persona_summary', '')}\n"
            )
        
        ambitions_context = ""
        if user_ambitions and user_ambitions.strip():
            ambitions_context = f"\n\nUSER AMBITIONS (current, not cached):\n{user_ambitions.strip()}\n"
            ambitions_context += "Use these ambitions to guide capability extraction, but base capabilities on CV experience.\n"
        
        prompt = (
            "VERSATILITY CHECK: Analyze the candidate's CV to identify 3-5 'Latent Capabilities' - transferable skills "
            "that are NOT explicitly named in the CV but can be inferred from their experience, responsibilities, and achievements.\n\n"
            "CRITICAL REQUIREMENTS:\n"
            "- Extract capabilities ONLY from the current CV text provided above\n"
            "- Do NOT use any old cached data or previous persona information\n"
            "- These should be SKILLS/ABILITIES, not job titles or technologies\n"
            "- They must be transferable across industries or roles\n"
            "- They must be inferable from the CV content (responsibilities, achievements, context)\n"
            "- Examples: 'Cross-functional collaboration', 'Stakeholder management', 'Data-driven decision making', "
            "'Process optimization', 'Team building', 'Budget management', 'Strategic planning'\n"
            "- DO NOT list technologies that are already in the tech_stack\n"
            "- DO NOT list job titles\n"
            "- Focus on leadership, management, and strategic skills\n"
            "- Base capabilities on actual work experience, projects, and achievements mentioned in the CV\n\n"
            f"{persona_context}"
            f"{ambitions_context}"
            f"CV Summary (first 2000 chars): {cv_text[:2000]}\n\n"
            "Return ONLY a valid JSON array of 3-5 capability strings:\n"
            '["Capability 1", "Capability 2", "Capability 3", ...]\n'
            "Be specific and infer from the actual CV content only."
        )
        
        try:
            response = self.api_client.call_api_with_fallback(prompt)
            capabilities = parse_json_safely(response.text) or []
            
            if isinstance(capabilities, list):
                # Ensure 3-5 capabilities
                if len(capabilities) > 5:
                    capabilities = capabilities[:5]
                elif len(capabilities) < 3:
                    # Pad with generic transferable capabilities if less than 3
                    generic_capabilities = [
                        "Strategic thinking",
                        "Cross-functional leadership",
                        "Stakeholder management",
                        "Data-driven decision making",
                        "Process optimization"
                    ]
                    for gen_cap in generic_capabilities:
                        if gen_cap not in capabilities and len(capabilities) < 5:
                            capabilities.append(gen_cap)
                return capabilities[:5]
            else:
                # Fallback: return generic transferable capabilities
                return ["Strategic thinking", "Cross-functional leadership", "Stakeholder management", "Data-driven decision making", "Process optimization"]
        except Exception as e:
            print(f"⚠️ Error identifying latent capabilities: {e}")
            # Fallback: return generic transferable capabilities
            return ["Strategic thinking", "Cross-functional leadership", "Stakeholder management"]
    
    def generate_horizon_roles(self, cv_text, digital_persona=None, skill_bucket=None, user_ambitions=None):
        """
        Generates 5 'Horizon Roles' - strategic positions that are a natural next step or strategic pivot
        based on the user's DNA. For each role, includes gap analysis (what's missing to reach it).
        
        Args:
            cv_text: Full CV text
            digital_persona: Digital persona dict (optional)
            skill_bucket: List of skills from skill bucket (optional)
            user_ambitions: User's written ambitions text (optional)
        
        Returns:
            List of dicts, each with: {"role": "Role Title", "gap_analysis": "What's missing to reach this role", "rationale": "Why this is a good fit"}
        """
        persona_context = ""
        if digital_persona:
            persona_context = (
                f"\n\nDIGITAL PERSONA:\n"
                f"Primary Domain: {digital_persona.get('primary_domain', 'Unknown')}\n"
                f"Role Level: {digital_persona.get('role_level', 'Senior')}\n"
                f"Industry Focus: {digital_persona.get('industry_focus', '')}\n"
                f"Latent Capabilities: {', '.join(digital_persona.get('latent_capabilities', []))}\n"
                f"Persona Summary: {digital_persona.get('persona_summary', '')}\n"
            )
        
        skill_context = ""
        if skill_bucket and len(skill_bucket) > 0:
            skill_context = f"\n\nPRIORITY SKILLS (Skill Bucket): {', '.join(skill_bucket)}\n"
        
        ambitions_context = ""
        if user_ambitions and user_ambitions.strip():
            ambitions_context = f"\n\nUSER AMBITIONS:\n{user_ambitions.strip()}\n"
            ambitions_context += "IMPORTANT: Use the user's stated ambitions to guide role suggestions. "
            ambitions_context += "If they mention wanting to pivot to a new domain or move to executive level, prioritize those types of roles.\n"
        
        primary_domain = "Engineering"  # Default
        if digital_persona:
            primary_domain = digital_persona.get('primary_domain', 'Engineering')
        
        # Build domain-specific strategic pivot examples
        pivot_examples = {
            'Marketing': {
                'natural_next': ['VP Marketing', 'CMO', 'VP Growth'],
                'strategic_pivot': ['VP Operations (if operational strength)', 'COO (if cross-functional leadership)', 'VP Product (if product experience)']
            },
            'Sales': {
                'natural_next': ['VP Sales', 'CRO', 'Head of Revenue'],
                'strategic_pivot': ['VP Marketing (if customer insight)', 'COO (if operational strength)', 'VP Operations (if process expertise)']
            },
            'Product': {
                'natural_next': ['VP Product', 'CPO', 'Head of Product'],
                'strategic_pivot': ['CTO (if technical background)', 'VP Engineering (if technical strength)', 'VP Operations (if operational focus)']
            },
            'Engineering': {
                'natural_next': ['CTO', 'VP Engineering', 'Chief Technology Officer'],
                'strategic_pivot': ['VP Product (if product sense)', 'COO (if operational strength)', 'VP Operations (if process expertise)']
            },
            'Operations': {
                'natural_next': ['VP Operations', 'COO', 'Head of Operations'],
                'strategic_pivot': ['VP Product (if product experience)', 'VP Engineering (if technical background)', 'CTO (if technology focus)']
            }
        }
        
        examples = pivot_examples.get(primary_domain, pivot_examples['Engineering'])
        
        prompt = (
            f"Analyze the candidate's CV and profile to generate 5 'Horizon Roles' - strategic positions that are "
            f"either a natural next step in their career OR a strategic pivot based on their transferable skills.\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"- Primary Domain: {primary_domain}\n"
            f"- Generate 5 roles total: Mix of 'natural next step' roles (2-3) and 'strategic pivot' roles (2-3)\n"
            f"- For 'natural next step': Suggest roles that are the logical progression (e.g., if Director Marketing → VP Marketing → CMO)\n"
            f"- For 'strategic pivot': Suggest roles in adjacent domains where their transferable skills apply (e.g., Marketing Director → VP Product if product experience exists)\n"
            f"- Examples for {primary_domain} domain:\n"
            f"  * Natural Next: {', '.join(examples.get('natural_next', []))}\n"
            f"  * Strategic Pivot: {', '.join(examples.get('strategic_pivot', []))}\n"
            f"- For EACH role, provide:\n"
            f"  * GAP ANALYSIS: What specific skills, experience, or credentials are currently missing in the CV to reach this role\n"
            f"  * RATIONALE: Why this role is a good strategic fit based on their DNA and transferable skills\n\n"
            f"{persona_context}"
            f"{skill_context}"
            f"{ambitions_context}"
            f"CV Summary (first 2000 chars): {cv_text[:2000]}\n\n"
            "VERSATILITY CHECK:\n"
            "- Generate horizon roles based ONLY on the current CV text provided above\n"
            "- Use current user ambitions if provided, but do NOT use old cached data\n"
            "- Extract latent capabilities and transferable skills from the current CV only\n"
            "- Ensure roles are based on the current persona (built from current CV), not old data\n\n"
            "Return ONLY a valid JSON array of 5 role objects:\n"
            '[\n'
            '  {\n'
            '    "role": "Role Title",\n'
            '    "gap_analysis": "Specific skills/experience missing to reach this role",\n'
            '    "rationale": "Why this is a good strategic fit"\n'
            '  },\n'
            '  ...\n'
            ']\n'
            "Be specific in gap analysis and rationale. Use the user's ambitions if provided."
        )
        
        try:
            response = self.api_client.call_api_with_fallback(prompt)
            horizon_roles = parse_json_safely(response.text) or []
            
            if isinstance(horizon_roles, list):
                # Ensure 5 roles
                if len(horizon_roles) > 5:
                    horizon_roles = horizon_roles[:5]
                elif len(horizon_roles) < 5:
                    # Pad with domain-specific default roles if less than 5
                    default_roles = examples.get('natural_next', [])[:5]
                    for default_role in default_roles:
                        if len(horizon_roles) < 5:
                            # Check if default_role already exists
                            exists = any(hr.get('role', '') == default_role for hr in horizon_roles if isinstance(hr, dict))
                            if not exists:
                                horizon_roles.append({
                                    "role": default_role,
                                    "gap_analysis": "Analyze specific gaps based on CV",
                                    "rationale": "Natural progression based on current role level"
                                })
                return horizon_roles[:5]
            else:
                # Fallback: return domain-specific default roles
                default_roles_list = examples.get('natural_next', [])[:5]
                return [{"role": role, "gap_analysis": "Analyze specific gaps based on CV", "rationale": "Natural progression based on current role level"} for role in default_roles_list]
        except Exception as e:
            print(f"⚠️ Error generating horizon roles: {e}")
            # Fallback: return domain-specific default roles
            examples = pivot_examples.get(primary_domain, pivot_examples['Engineering'])
            default_roles_list = examples.get('natural_next', [])[:5]
            return [{"role": role, "gap_analysis": "Analyze specific gaps based on CV", "rationale": "Natural progression based on current role level"} for role in default_roles_list]
    
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
            response = self.api_client.call_api_with_fallback(prompt)
            query = response.text.strip().replace('"', '')
            # מנקה תווים חריגים
            query = query.replace("\n", " ").replace("\r", " ")
            
            # Search Refinement: Append mandatory context to filter out non-tech roles
            # Goal: Filter out non-tech roles (like VP Sales in traditional factories) at the source
            query_lower = query.lower()
            mandatory_contexts = ['software', 'tech', 'digital', 'technology', 'engineering', 'it', 'ict']
            has_tech_context = any(ctx in query_lower for ctx in mandatory_contexts)
            
            if not has_tech_context:
                # Append most appropriate context based on query
                if 'cto' in query_lower or 'chief' in query_lower:
                    query = f"{query} Technology"
                elif 'vp' in query_lower or 'vice president' in query_lower:
                    query = f"{query} Tech"
                elif 'head' in query_lower or 'director' in query_lower:
                    query = f"{query} Software"
                else:
                    query = f"{query} Digital"  # Default fallback
            
            return query
        except Exception:
            # Fallback: if E-commerce keywords found, use E-commerce focused query
            if has_ecommerce_focus:
                return "CTO E-commerce Technology"  # Added mandatory context
            return "Chief Technology Officer Software"  # Added mandatory context
    
    def extract_top_skills(self, job_description, cv_text=None, digital_persona=None):
        """
        Extracts the 3 most critical SPECIFIC technical or business skills mentioned ONLY in that specific job description.
        NO generic placeholders. Must extract actual skills from the job text.
        If the job is irrelevant (like Security Guard), returns ['Irrelevant Role'].
        """
        # Check if job is relevant to senior tech leadership (no hardcoded industry)
        # Get persona from parameter (passed from analyze_match) - no hardcoded E-commerce
        persona = digital_persona or {}
        role_level = persona.get('role_level', 'Senior')
        industry_focus = persona.get('industry_focus', 'Technology Leadership / General Tech')
        
        # Adaptive Scoring: Use industry_focus from persona, not hardcoded 'Tech'
        primary_domain = persona.get('primary_domain', 'Engineering')
        
        # Build domain-specific role examples based on primary_domain
        domain_role_examples = {
            'Marketing': 'VP Marketing, Head of Digital Marketing, CMO, VP Growth, Head of MarTech',
            'Sales': 'VP Sales, Head of Revenue, CRO, VP Business Development, Head of Sales',
            'Product': 'VP Product, Head of Product, CPO, VP Product Management, Head of Product Strategy',
            'Engineering': 'CTO, VP Engineering, Head of Engineering, Chief Technology Officer, VP Technology',
            'Operations': 'VP Operations, Head of Operations, COO, VP Operations Management, Head of Business Operations'
        }
        role_examples = domain_role_examples.get(primary_domain, domain_role_examples['Engineering'])
        
        relevance_check_prompt = (
            f"Analyze this job description and determine if it's relevant for a {role_level} {primary_domain} candidate. "
            f"The candidate's PRIMARY DOMAIN is: {primary_domain}. "
            f"The candidate's industry focus is: {industry_focus}. "
            f"The candidate is looking for {primary_domain} leadership roles: {role_examples}. "
            "Return ONLY a JSON object:\n"
            '{"is_relevant": true/false, "reason": "brief reason", "seniority_level": "entry/junior/mid/senior/executive"}\n\n'
            f"Job Description:\n{job_description[:2000]}\n\n"
            f"CRITICAL: If the job is NOT in the {primary_domain} domain (e.g., if candidate is Marketing but job is Engineering), set is_relevant to false. "
            "Also set is_relevant to false if the job is Entry Level, Security Guard, Retail Worker, or any non-leadership role."
        )
        
        try:
            response = self.api_client.call_api_with_fallback(relevance_check_prompt)
            # Safe JSON Parsing: Use parse_json_safely to extract JSON between { and } and remove triple backticks
            relevance_result = parse_json_safely(response.text) or {}
            
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
            
            response = self.api_client.call_api_with_fallback(prompt)
            # Safe JSON Parsing: Use parse_json_safely to extract JSON between { and } and remove triple backticks
            result = parse_json_safely(response.text) or []
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
    
    def get_unified_profile(self, cv_text, skill_bucket=None, digital_persona=None):
        """
        Reconstructs a Unified Profile that combines:
        (a) CV text
        (b) Key skills identified by AI
        (c) Patterns from feedback_log.json (what user liked/disliked)
        (d) Custom preferences from preferences.json
        
        This Unified Profile serves as the core identity for job matching.
        The Digital Persona remains the sole source of truth and is not overwritten.
        
        Returns:
            dict: Unified profile with all components merged
        """
        # (a) CV Text - base component
        unified = {
            'cv_text': cv_text[:2000],  # First 2000 chars for context
            'cv_summary': cv_text[:500]  # Summary for quick reference
        }
        
        # (b) Key skills identified by AI
        # Extract key skills from CV using AI
        try:
            # Use extract_top_skills to identify key skills from CV
            # We'll extract skills by analyzing the CV itself
            skills_prompt = (
                "Extract the top 10 most important technical and business skills from this CV. "
                "Return ONLY a JSON array of skill strings: [\"skill1\", \"skill2\", ...]\n\n"
                f"CV:\n{cv_text[:2000]}"
            )
            response = self.api_client.call_api_with_fallback(skills_prompt)
            key_skills = parse_json_safely(response.text) or []
            if not isinstance(key_skills, list):
                key_skills = []
            unified['key_skills'] = key_skills[:10]  # Limit to top 10
        except Exception as e:
            print(f"WARN: Could not extract key skills from CV: {e}")
            unified['key_skills'] = []
        
        # Add skill bucket if provided
        if skill_bucket and len(skill_bucket) > 0:
            unified['skill_bucket'] = skill_bucket
            # Merge skill bucket with key skills (avoid duplicates)
            all_skills = list(set(unified.get('key_skills', []) + skill_bucket))
            unified['key_skills'] = all_skills[:15]  # Limit to top 15 total
        
        # (c) Patterns from feedback_log.json (what user liked/disliked)
        feedback_log = load_feedback_log()
        if feedback_log:
            # Extract rejection reasons and their frequencies
            rejection_reasons = [entry.get('reason', '') for entry in feedback_log if entry.get('reason')]
            reason_counts = {}
            for reason in rejection_reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            
            # Build patterns from feedback
            unified['feedback_patterns'] = {
                'rejected_reasons': reason_counts,
                'total_rejections': len(feedback_log),
                'most_common_rejection': max(reason_counts.items(), key=lambda x: x[1])[0] if reason_counts else None
            }
        else:
            unified['feedback_patterns'] = {
                'rejected_reasons': {},
                'total_rejections': 0,
                'most_common_rejection': None
            }
        
        # (d) Custom preferences from preferences.json
        try:
            preferences = load_preferences()
            user_identity = preferences.get('user_identity', {})
            scoring_weights = preferences.get('scoring_weights', {})
            
            unified['custom_preferences'] = {
                'preferred_roles': user_identity.get('preferred_roles', []),
                'added_skills': user_identity.get('added_skills', []),
                'scoring_weights': scoring_weights
            }
        except Exception as e:
            print(f"WARN: Could not load preferences: {e}")
            unified['custom_preferences'] = {
                'preferred_roles': [],
                'added_skills': [],
                'scoring_weights': {}
            }
        
        # (e) Digital Persona - Reference only, do not overwrite
        # The Digital Persona remains the sole source of truth
        if digital_persona:
            unified['digital_persona_reference'] = {
                'role_level': digital_persona.get('role_level', 'Senior'),
                'industry_focus': digital_persona.get('industry_focus', ''),
                'tech_stack': digital_persona.get('tech_stack', []),
                'persona_summary': digital_persona.get('persona_summary', '')
            }
        else:
            unified['digital_persona_reference'] = None
        
        return unified
    
    def store_user_feedback(self, job_id, reason):
        """
        Store user feedback for a job rejection to feedback_log.json.
        This feedback is used as negative constraints in future job matching.
        
        Args:
            job_id: Unique identifier for the job (e.g., company_title_url hash)
            reason: Reason for rejection (e.g., 'Wrong Role', 'Salary too low', 'Location', etc.)
        
        Returns:
            bool: True if feedback was stored successfully
        """
        try:
            feedback_log = load_feedback_log()
            
            feedback_entry = {
                'timestamp': datetime.datetime.now().isoformat(),
                'job_id': job_id,
                'reason': reason
            }
            
            # Check if feedback for this job_id already exists
            existing_indices = [i for i, entry in enumerate(feedback_log) if entry.get('job_id') == job_id]
            if existing_indices:
                # Update existing entry
                feedback_log[existing_indices[0]] = feedback_entry
            else:
                # Add new entry
                feedback_log.append(feedback_entry)
            
            save_feedback_log(feedback_log)
            print(f"✅ Feedback stored: {reason} for job_id: {job_id}")
            return True
        except Exception as e:
            print(f"❌ Error storing feedback: {e}")
            import traceback
            print(traceback.format_exc())
            return False
    
    # ========================================================================
    # AI-ORCHESTRATION: Vector Embedding & Similarity Search (Cost Optimization)
    # ========================================================================
    
    def _get_embedding_api_key(self):
        """Get OpenAI API key for embeddings (separate from OpenRouter)."""
        try:
            import streamlit as st
            try:
                api_key = st.secrets.get("OPENAI_API_KEY", None)
                if api_key:
                    return api_key
            except (AttributeError, KeyError, Exception):
                pass
        except Exception:
            pass
        
        # Fallback to .env
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️ OPENAI_API_KEY not found. Vector similarity search will be disabled.")
        return api_key
    
    def generate_embedding(self, text: str) -> list:
        """
        Generate vector embedding for text using OpenAI's text-embedding-3-small model.
        This is a low-cost embedding model ($0.02 per 1M tokens.
        
        Args:
            text: Text to embed (CV, job description, etc.)
        
        Returns:
            List of floats representing the embedding vector, or None on error
        """
        if not text or not isinstance(text, str) or len(text.strip()) == 0:
            return None
        
        api_key = self._get_embedding_api_key()
        if not api_key:
            return None
        
        try:
            # Use OpenAI's embedding API (not OpenRouter)
            response = requests.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "text-embedding-3-small",
                    "input": text[:8000]  # Limit to 8000 chars (model max)
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                return data['data'][0]['embedding']
        except Exception as e:
            print(f"⚠️ Error generating embedding: {e}")
            return None
        
        return None
    
    def generate_dna_signature(self, cv_text: str, digital_persona: dict = None, 
                              questionnaire_answers: dict = None, ambitions: str = None) -> list:
        """
        Generate Personal DNA Signature (vector embedding) from CV + questionnaire + ambitions.
        This signature is used for low-cost vector similarity filtering before AI calls.
        
        Args:
            cv_text: User's CV text
            digital_persona: Digital persona dict (optional)
            questionnaire_answers: Questionnaire answers dict (optional)
            ambitions: User's written ambitions (optional)
        
        Returns:
            List of floats representing the DNA signature embedding, or None on error
        """
        # Build comprehensive DNA text from all sources
        dna_parts = []
        
        # 1. CV text (first 2000 chars for efficiency)
        if cv_text:
            dna_parts.append(f"CV Experience: {cv_text[:2000]}")
        
        # 2. Digital Persona summary
        if digital_persona:
            persona_summary = digital_persona.get('persona_summary', '')
            role_level = digital_persona.get('role_level', '')
            industry_focus = digital_persona.get('industry_focus', '')
            tech_stack = digital_persona.get('tech_stack', [])
            latent_capabilities = digital_persona.get('latent_capabilities', [])
            
            if persona_summary:
                dna_parts.append(f"Persona: {persona_summary}")
            if role_level:
                dna_parts.append(f"Role Level: {role_level}")
            if industry_focus:
                dna_parts.append(f"Industry Focus: {industry_focus}")
            if tech_stack:
                dna_parts.append(f"Tech Stack: {', '.join(tech_stack[:20])}")  # Limit to top 20
            if latent_capabilities:
                dna_parts.append(f"Latent Capabilities: {', '.join(latent_capabilities)}")
        
        # 3. Questionnaire answers
        if questionnaire_answers and isinstance(questionnaire_answers, dict):
            qa_text = " ".join([f"{k}: {v}" for k, v in list(questionnaire_answers.items())[:10]])  # Limit to first 10
            if qa_text:
                dna_parts.append(f"Questionnaire: {qa_text}")
        
        # 4. Ambitions
        if ambitions:
            dna_parts.append(f"Career Ambitions: {ambitions[:500]}")
        
        # Combine all parts
        dna_text = "\n".join(dna_parts)
        
        if not dna_text or len(dna_text.strip()) == 0:
            print("⚠️ No DNA content to embed. Returning None.")
            return None
        
        # Generate embedding
        return self.generate_embedding(dna_text)
    
    def cosine_similarity(self, vec1: list, vec2: list) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First vector (list of floats)
            vec2: Second vector (list of floats)
        
        Returns:
            Cosine similarity score (0.0 to 1.0), or 0.0 on error
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        try:
            # Calculate dot product
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            
            # Calculate magnitudes
            magnitude1 = math.sqrt(sum(a * a for a in vec1))
            magnitude2 = math.sqrt(sum(a * a for a in vec2))
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
            
            # Cosine similarity
            similarity = dot_product / (magnitude1 * magnitude2)
            return max(0.0, min(1.0, similarity))  # Clamp to [0, 1]
        except Exception as e:
            print(f"⚠️ Error calculating cosine similarity: {e}")
            return 0.0
    
    def filter_job_by_vector_similarity(self, job_description: str, dna_embedding: list, 
                                        similarity_threshold: float = 0.75) -> tuple[bool, float]:
        """
        Filter job by vector similarity before AI analysis.
        This is a low-cost pre-filter that saves AI API calls.
        
        Args:
            job_description: Job description text
            dna_embedding: User's DNA signature embedding (list of floats)
            similarity_threshold: Minimum similarity score to pass (default 0.75)
        
        Returns:
            Tuple of (passes_filter: bool, similarity_score: float)
        """
        if not dna_embedding or not job_description:
            # If no DNA embedding, allow through (fallback to AI analysis)
            return True, 0.0
        
        # Generate embedding for job description
        job_embedding = self.generate_embedding(job_description)
        if not job_embedding:
            # If embedding generation fails, allow through (fallback to AI analysis)
            return True, 0.0
        
        # Calculate similarity
        similarity = self.cosine_similarity(dna_embedding, job_embedding)
        
        # Pass if similarity >= threshold
        passes = similarity >= similarity_threshold
        
        return passes, similarity
    
    def analyze_match(self, job_description, cv_text, skill_bucket=None, master_profile=None, digital_persona=None, strict_industry_match=True, job_title=None, job_url=None, dna_embedding=None):
        """
        מנתח את מידת ההתאמה בין תיאור משרה לקורות חיים.
        אם יש Digital Persona, משתמש בו לבדיקת Level Mismatch.
        אם יש ניסיון E-commerce ב-CV, נותן משקל גבוה יותר למשרות E-commerce.
        תמיד כולל נימוק כן, ציון (0-100), ומחזיר רשימה אמיתית של פערי מיומנויות שזוהו.
        אין לאפשר המצאת ניסיון או 'סימון וי' גורף.
        
        IMPROVED: Now includes feedback-driven filtering and profile-centric scoring.
        
        Args:
            strict_industry_match (bool): If True, aggressive industry filtering. If False, flexible matching prioritizes leadership skills.
            job_title (str, optional): Job title for hard override logic. If not provided, will be extracted from job_description.
            job_url (str, optional): Stable identifier for strict caching. If provided, analysis is cached in job_analysis_cache.json.
        """
        # Hard Constraints Pre-Filter (Personal DNA): discard immediately before ANY AI spend.
        try:
            job_for_filter = {
                "title": job_title or "",
                "company": "",
                "job_url": job_url or "",
                "description": job_description or ""
            }
            failed, reason = self._hard_constraints_fail(job_for_filter)
            if failed:
                discard = {
                    "score": 0,
                    "match_score": 0,
                    "base_match_score": 0,
                    "career_horizon_bonus_points": 0,
                    "career_horizon_score": 0.0,
                    "discarded": True,
                    "discard_reason": reason,
                    "reasoning": f"Discarded by Hard Constraints: {reason}",
                    "explanation": f"Discarded by Hard Constraints: {reason}",
                    "gaps": ["Hard Constraints"]
                }
                # Cache discard result so we never spend on it later
                if job_url:
                    self._set_cached_job_analysis(job_url, discard)
                return discard
        except Exception:
            # Never block analysis if pre-filter fails unexpectedly
            pass

        # AI-ORCHESTRATION: Vector Similarity Pre-Filter (Low-Cost Screening)
        # Filter jobs with similarity < 0.75 before ANY AI calls to save costs
        if dna_embedding:
            passes_vector_filter, vector_similarity = self.filter_job_by_vector_similarity(
                job_description, dna_embedding, similarity_threshold=0.75
            )
            if not passes_vector_filter:
                # Job failed vector similarity - discard without AI call
                discard = {
                    "score": 0,
                    "match_score": 0,
                    "base_match_score": 0,
                    "career_horizon_bonus_points": 0,
                    "career_horizon_score": 0.0,
                    "discarded": True,
                    "discard_reason": f"Vector similarity {vector_similarity:.2f} below threshold 0.75",
                    "reasoning": f"Filtered by Vector Similarity: {vector_similarity:.2f} < 0.75 (Cost: $0)",
                    "explanation": f"Job description does not match Personal DNA Signature. Similarity: {vector_similarity:.2f}",
                    "gaps": ["Vector Similarity Filter"],
                    "vector_similarity": vector_similarity
                }
                # Cache discard result so we never spend on it later
                if job_url:
                    self._set_cached_job_analysis(job_url, discard)
                return discard

        # Cost Control: Summary-first approach - If job description is long, send only first 1000 chars for initial score
        # This saves tokens while still providing enough context for accurate scoring
        job_description_for_ai = (job_description or "")[:1000]
        cv_text_for_ai = (cv_text or "")[:1000]
        
        # Check if pivot_mode is enabled (search by skills, not just titles)
        try:
            preferences = load_preferences()
            pivot_mode = preferences.get('user_identity', {}).get('pivot_mode', False)
        except Exception:
            pivot_mode = False
        
        # Structural Skill Alignment: Analyze if job matches user's core competencies even in different industry
        structural_alignment = self._analyze_structural_skill_alignment(
            job_description_for_ai, cv_text_for_ai, digital_persona, pivot_mode
        )

        # Strict Caching: If we already analyzed this job_url, never analyze again
        cached = self._get_cached_job_analysis(job_url)
        if cached and isinstance(cached, dict):
            cached_copy = dict(cached)
            cached_copy["cached"] = True
            cached_copy.setdefault("job_url", job_url)
            return cached_copy
        # Hard-Override Logic: Move leadership safety check to the VERY TOP
        # Scoring Sensitivity: Reduce the default executive hard-override score from 85 to 60
        # so more jobs are visible without being marked as "perfect match".
        # If title contains 'CTO', 'VP', 'Chief', 'Director', 'Head of', or 'Founding', return 60 immediately and skip AI call.
        # Fix Hebrew Parsing: Handle Hebrew characters and ensure 'CTO' is recognized even when surrounded by Hebrew text
        if not job_title:
            # Try to extract title from job_description (look for common patterns)
            first_lines = job_description[:200].split('\n') if job_description else []
            if first_lines:
                potential_title = first_lines[0].strip()
                if len(potential_title) < 100 and not potential_title.endswith(('.', '!', '?')):
                    job_title = potential_title
                else:
                    job_title = job_description[:100] if job_description else "Unknown"
            else:
                job_title = job_description[:100] if job_description else "Unknown"
        
        # Fix Hebrew Parsing: Use case-insensitive matching and handle Hebrew characters
        # Convert to uppercase for case-insensitive matching, preserving Hebrew characters
        job_title_upper = job_title.upper() if job_title else ""
        job_title_lower = job_title.lower() if job_title else ""
        
        # Executive keywords - case-insensitive, works with Hebrew text
        executive_keywords = ['CTO', 'VP', 'CHIEF', 'DIRECTOR', 'HEAD OF', 'FOUNDING', 'VICE PRESIDENT']
        # Check if any executive keyword appears in the title (case-insensitive, handles Hebrew)
        is_executive_role = any(kw in job_title_upper for kw in executive_keywords)
        
        # Hard-Override: If executive role detected, return 60% immediately and skip AI call
        if is_executive_role:
            print(f"🔧 HARD-OVERRIDE: Executive role detected in '{job_title}'. Returning 60% immediately (skipping AI call).")
            hard_override_result = {
                "score": 60,
                "match_score": 60,
                "reasoning": f"🔧 Hard-Override: Job title '{job_title}' contains executive keywords (CTO, VP, Chief, Director, Head of, or Founding). Automatically scored 60% without AI analysis.",
                "explanation": f"🔧 **Hard-Override Applied:** This role was automatically recognized as an executive-level position based on the job title. Score set to 60% without AI analysis.",
                "gaps": [],
                "why_matches": f"Executive role detected: {job_title}. This position matches your senior leadership profile.",
                "why_doesnt_match": "",
                "hard_override": True,
                "job_url": job_url
            }
            # Cache even hard-override results so we never touch this job again
            self._set_cached_job_analysis(job_url, hard_override_result)
            return hard_override_result
        
        # Print AI Input: Add debug line to see exactly what text the AI is judging (only if not hard-override)
        print(f"DEBUG: Sending to AI -> Job: {job_title if job_title else 'No title provided'}")
        print(f"DEBUG: Job Description (first 200 chars): {job_description_for_ai[:200] if job_description_for_ai else 'No description'}")
        # Pre-Flight Persona Check: If digital_persona is outdated or missing key leadership terms, force a 'light refresh'
        if digital_persona:
            persona_summary = digital_persona.get('persona_summary', '').lower()
            key_leadership_terms = ['cto', 'vp', 'executive', 'leadership', 'senior', 'director', 'chief', 'head of']
            has_leadership_terms = any(term in persona_summary for term in key_leadership_terms)
            
            # Check if persona is missing key leadership context
            if not has_leadership_terms or len(persona_summary) < 50:
                print(f"⚠️ Pre-Flight Persona Check: Persona is outdated or missing key leadership terms. Summary length: {len(persona_summary)}, Has leadership terms: {has_leadership_terms}")
                print("🔄 Forcing light refresh of persona before job analysis...")
                
                # Light Refresh: Quick update of persona_summary with leadership context
                try:
                    # Extract key info from CV for quick refresh
                    cv_lower = cv_text.lower()
                    has_cto = 'cto' in cv_lower or 'chief technology officer' in cv_lower
                    has_vp = 'vp' in cv_lower or 'vice president' in cv_lower
                    has_director = 'director' in cv_lower
                    has_head = 'head of' in cv_lower
                    
                    # Build enhanced summary with leadership context
                    leadership_context = []
                    if has_cto:
                        leadership_context.append("CTO")
                    if has_vp:
                        leadership_context.append("VP")
                    if has_director:
                        leadership_context.append("Director")
                    if has_head:
                        leadership_context.append("Head of")
                    
                    if leadership_context:
                        enhanced_summary = f"TOP-TIER EXECUTIVE ({', '.join(leadership_context)}). " + (persona_summary if persona_summary else "Senior technology leader with extensive experience.")
                        digital_persona['persona_summary'] = enhanced_summary
                        print(f"✅ Light Refresh: Enhanced persona summary with leadership context: {enhanced_summary[:100]}...")
                except Exception as refresh_error:
                    print(f"⚠️ Error during light refresh: {refresh_error}. Continuing with existing persona.")
        
        # Profile-Centric Scoring: Check if profile is missing
        if not cv_text or len(cv_text.strip()) < 50:
            print("WARN: Profile Missing - cv_text is empty or too short. Returning 0% match.")
            return {
                "score": 0,
                "match_score": 0,
                "reasoning": "Profile Missing: CV text is empty or too short. Please upload a valid CV.",
                "explanation": "Profile Missing: CV text is empty or too short. Please upload a valid CV.",
                "gaps": ["Profile Missing"],
                "why_matches": "",
                "why_doesnt_match": "Cannot analyze match without a valid CV profile."
            }
        
        # Extract job_title from job_description if not provided
        if not job_title:
            # Try to extract title from job_description (look for common patterns)
            # First 200 chars often contain the title
            first_lines = job_description[:200].split('\n')
            if first_lines:
                potential_title = first_lines[0].strip()
                # If it looks like a title (short, capitalized, no punctuation at end), use it
                if len(potential_title) < 100 and not potential_title.endswith(('.', '!', '?')):
                    job_title = potential_title
                else:
                    job_title = job_description[:100]  # Fallback: use first 100 chars
            else:
                job_title = job_description[:100]  # Fallback: use first 100 chars
        
        # Feedback-Driven Filtering: Load feedback_log.json before scoring
        feedback_log = load_feedback_log()
        job_lower = job_description.lower()  # Define job_lower early for use in filtering
        job_title_lower = job_title.lower() if job_title else job_lower  # Extract title for override logic
        rejection_patterns = {}  # Initialize rejection_patterns dict
        
        if feedback_log:
            # Check if this job matches a previously rejected pattern
            # Extract rejection patterns from feedback
            for entry in feedback_log:
                reason = entry.get('reason', '')
                if reason:
                    # Build pattern matching based on rejection reason
                    if 'Wrong Role' in reason or 'wrong role' in reason.lower():
                        # Check if job title/description matches rejected role patterns
                        rejected_job_id = entry.get('job_id', '')
                        if rejected_job_id:
                            # Extract title/company from job_id if possible
                            # For now, use reason-based matching
                            rejection_patterns['wrong_role'] = rejection_patterns.get('wrong_role', 0) + 1
                    
                    if 'Salary too low' in reason or 'salary' in reason.lower():
                        # Check for low salary indicators
                        low_salary_keywords = ['entry level', 'junior', 'intern', 'starting salary', 'competitive salary']
                        if any(kw in job_lower for kw in low_salary_keywords):
                            rejection_patterns['low_salary'] = rejection_patterns.get('low_salary', 0) + 1
                    
                    if 'Location' in reason:
                        rejection_patterns['location'] = rejection_patterns.get('location', 0) + 1
                    
                    if 'Company reputation' in reason:
                        rejection_patterns['company_reputation'] = rejection_patterns.get('company_reputation', 0) + 1
        
        # Dynamic Seniority Check: If user rejected 'Executive' roles, penalize VP/Director/Chief roles
        executive_rejections = []
        if feedback_log:
            executive_rejections = [e for e in feedback_log if 'Executive' in str(e.get('reason', '')) or 'executive' in str(e.get('reason', '')).lower()]
        
        # CRITICAL FIX: Removed aggressive seniority blockade and level mismatch check
        # Instead of blocking, we'll let the AI calculate a score based on seniority match
        job_lower = job_description.lower()
        # Broadened title recognition: CTO, VP, Director, Head of, Principal, Architect, Staff Engineer, CTO Office, Founding roles
        senior_leadership_keywords = [
            'vp', 'vice president', 'director', 'chief', 'cto', 'cfo', 'cmo', 
            'head of', 'senior director', 'executive', 'leadership',
            'principal', 'principal engineer', 'principal architect',
            'architect', 'chief architect', 'senior architect',
            'staff engineer', 'staff', 'cto office', 'office of the cto',
            'distinguished engineer', 'fellow', 'senior fellow',
            'founding', 'founding engineer', 'founding cto', 'founder', 'co-founder'
        ]
        has_senior_role = any(kw in job_lower for kw in senior_leadership_keywords)
        
        # Fix 0% for Founding CTO: Recognize 'Founding Engineer / CTO' as high-potential role
        is_founding_role = any(kw in job_lower for kw in ['founding', 'founding engineer', 'founding cto', 'founder', 'co-founder'])
        
        # Check industry match if Digital Persona is available
        industry_match = True  # Default to True if no Digital Persona
        industry_focus = ''
        if digital_persona:
            industry_focus = digital_persona.get('industry_focus', '').lower()
            if industry_focus:
                # Check if job description mentions the industry or related keywords
                industry_keywords = [industry_focus]
                # Add common variations
                if 'e-commerce' in industry_focus or 'ecommerce' in industry_focus:
                    industry_keywords.extend(['e-commerce', 'ecommerce', 'shopify', 'magento', 'retail tech', 'online retail'])
                if 'fintech' in industry_focus:
                    industry_keywords.extend(['fintech', 'financial technology', 'banking', 'payments'])
                if 'retail' in industry_focus:
                    industry_keywords.extend(['retail', 'retail tech', 'consumer'])
                
                # Check if any industry keyword appears in job description
                industry_match = any(kw in job_lower for kw in industry_keywords)
        
        # Debug Visibility: Print industry focus
        print(f"DEBUG: Industry Focus: {industry_focus if industry_focus else 'Not specified (defaulting to match)'}")
        
        # ERADICATE 'Aggressive Filter': Deleted the entire IF/ELSE block that returned 0% for non-senior roles
        # All jobs now proceed to AI analysis, which will calculate a score based on transferable skills
        
        # Check if job is irrelevant (if skills extraction indicates so)
        try:
            top_skills = self.extract_top_skills(job_description, cv_text, digital_persona=digital_persona)
            if top_skills == ['Irrelevant Role']:
                # Get persona context dynamically (no hardcoded industry)
                persona_context = "senior technology leadership"
                if digital_persona:
                    role_level = digital_persona.get('role_level', 'Senior')
                    industry_focus = digital_persona.get('industry_focus', 'Technology Leadership')
                    persona_context = f"{role_level} {industry_focus}"
                
                return {
                    "score": 0,
                    "match_score": 0,
                    "reasoning": f"This role is not relevant for a {persona_context} candidate (Entry Level, non-tech role, or wrong seniority).",
                    "explanation": f"This role is not relevant for a {persona_context} candidate (Entry Level, non-tech role, or wrong seniority).",
                    "gaps": ["Irrelevant Role Type"],
                    "why_matches": "",
                    "why_doesnt_match": f"Role type is not relevant for {persona_context} positions."
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
        
        # Smart Filtering: Add past user feedback as negative constraints
        feedback_log = load_feedback_log()
        if feedback_log:
            # Extract common rejection reasons from feedback
            rejection_reasons = [entry.get('reason', '') for entry in feedback_log if entry.get('reason')]
            
            # Build negative constraints prompt
            if rejection_reasons:
                # Count frequency of each reason
                reason_counts = {}
                for reason in rejection_reasons:
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                
                # Create constraints text
                constraints_text = "NEGATIVE CONSTRAINTS (User Feedback - Learn from Past Rejections):\n"
                constraints_text += "The candidate has previously rejected jobs for these reasons:\n"
                for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
                    constraints_text += f"- {reason} (rejected {count} time(s))\n"
                constraints_text += (
                    "IMPORTANT: If this job matches any of these rejection patterns, "
                    "you MUST significantly lower the match score (by 20-40 points) or return 0% if it's a clear mismatch.\n"
                    "For example:\n"
                    "- If reason was 'Salary too low' and this job mentions low salary indicators, lower the score.\n"
                    "- If reason was 'Wrong Role' and this role doesn't match the candidate's level/type, return 0%.\n"
                    "- If reason was 'Location' and this job is in the same problematic location, lower the score.\n"
                    "- If reason was 'Company reputation' and this job is from a similar company type, be cautious.\n"
                )
                base_prompt += constraints_text
        
        # Improve Match Accuracy: Updated rules - prioritize scoring over blocking
        # Force Positive Scoring: Forbid 0% based on title alone
        strictness_instruction = (
            "\nSCORING RULES (Prioritize Scoring over Blocking - FORCE POSITIVE SCORING):\n"
            "- You are FORBIDDEN from giving a 0% score based on job title alone, unless it is a junior/entry-level/unskilled role.\n"
            "- Even if the industry is wrong (e.g., Food vs Tech), calculate a score based on the transferable leadership skills.\n"
            "- ALWAYS calculate a score. Do NOT return 0% unless the job is clearly entry-level or junior (intern, assistant, trainee, unskilled).\n"
            "- If the match is clearly below 30%, return a low score (20-30%) but NOT 0% unless it's entry-level.\n"
            "- Do NOT inflate scores. Be honest and strict. If there are major gaps, reflect that in the score.\n"
            "- If the job is entry-level or junior when the candidate is senior/executive, return 0% immediately.\n"
            "- If the job is in a completely different industry with no transferable skills, return a low score (20-40%) but NOT 0%.\n"
            "- For roles like 'CTO Office', 'Principal Engineer', 'Staff Engineer', 'Distinguished Engineer', score 70%+ as they are high-level strategic roles.\n"
            "- Focus on transferable skills: leadership, management, technical strategy, architecture - these apply across industries.\n"
        )
        base_prompt += strictness_instruction
        
        # Profile-Centric Scoring: Load added_skills from preferences
        try:
            preferences = load_preferences()
            user_identity = preferences.get('user_identity', {})
            added_skills = user_identity.get('added_skills', [])
        except Exception as e:
            print(f"WARN: Could not load preferences for added_skills: {e}")
            added_skills = []
        
        # Combine skill_bucket with added_skills from profile
        all_user_skills = list(set((skill_bucket or []) + added_skills))
        
        # Reconstruct Unified Profile for core identity comparison
        unified_profile = self.get_unified_profile(
            cv_text,
            skill_bucket=all_user_skills,  # Use combined skills
            digital_persona=digital_persona
        )
        
        # Enhanced Context: Generate 'Strategic Summary' based on primary_domain from persona
        primary_domain = digital_persona.get('primary_domain', 'Engineering') if digital_persona else 'Engineering'
        industry_focus = digital_persona.get('industry_focus', '') if digital_persona else ''
        
        # Build domain-specific strategic summary
        domain_summaries = {
            'Marketing': "The candidate is at a career stage where they can lead ANY Marketing department. Focus on campaign management, brand strategy, customer acquisition, and marketing analytics. Their core skills in digital marketing, MarTech, leadership, team management, and marketing strategy apply to ANY marketing-driven industry.",
            'Sales': "The candidate is at a career stage where they can lead ANY Sales department. Focus on revenue generation, pipeline management, customer relationships, and sales strategy. Their core skills in sales leadership, CRM, revenue operations, team management, and sales strategy apply to ANY sales-driven industry.",
            'Product': "The candidate is at a career stage where they can lead ANY Product department. Focus on product strategy, roadmap planning, user experience, and product analytics. Their core skills in product management, user research, leadership, team management, and product strategy apply to ANY product-driven industry.",
            'Engineering': "The candidate is at a career stage where they can lead ANY technology department. Focus on organizational impact, budget management, and technical vision. Their core skills in scalability, architecture, leadership, team management, and technical strategy apply to ANY tech-driven industry.",
            'Operations': "The candidate is at a career stage where they can lead ANY Operations department. Focus on operational efficiency, process optimization, business operations, and operational analytics. Their core skills in operations management, process improvement, leadership, team management, and operations strategy apply to ANY operations-driven industry."
        }
        
        strategic_summary_base = domain_summaries.get(primary_domain, domain_summaries['Engineering'])
        strategic_summary = (
            f"STRATEGIC CANDIDATE SUMMARY:\n"
            f"{strategic_summary_base} "
            f"Leadership scale and organizational impact are the primary matching factors, "
            f"not just industry-specific keywords. The candidate's domain is {primary_domain} with industry focus: {industry_focus}.\n"
        )
        
        # Multi-CV Fusion: If multiple CVs were merged, instruct AI to look at all as a single 'Super-Persona'
        multi_cv_note = ""
        if "=== MULTI-CV MASTER PROFILE ===" in cv_text:
            multi_cv_note = (
                "\nMULTI-CV FUSION INSTRUCTION:\n"
                "The CV text above contains multiple CVs merged into a single 'Super-Persona'. "
                "You MUST look at ALL uploaded CVs as a single comprehensive profile to find the broadest possible skill set. "
                "Extract skills, experiences, and leadership patterns from ALL CVs, not just one. "
                "This Super-Persona represents the candidate's complete professional identity across all their roles and experiences.\n"
            )
        
        # CV Pre-Parsing: Extract persona_summary and put it at the VERY TOP of the prompt
        persona_summary_text = ""
        if digital_persona:
            persona_summary_text = digital_persona.get('persona_summary', '')
            # Debug Persona: Print what persona_summary is being sent
            print(f"DEBUG: Persona Summary being sent to AI: '{persona_summary_text}'")
            if not persona_summary_text or len(persona_summary_text.strip()) == 0:
                print("WARN: Persona Summary is EMPTY! This may cause the AI to miss the candidate's high-level identity.")
        else:
            print("WARN: Digital Persona is None! No persona_summary available.")
        
        # Build Unified Profile context for the prompt
        # CV Pre-Parsing: Put persona_summary at the VERY TOP
        unified_context = "=== CANDIDATE IDENTITY (READ THIS FIRST) ===\n"
        if persona_summary_text:
            unified_context += f"PERSONA SUMMARY (HIGH-LEVEL IDENTITY): {persona_summary_text}\n\n"
        else:
            # Dynamic fallback based on primary_domain
            domain_fallbacks = {
                'Marketing': 'TOP-TIER EXECUTIVE (VP/Head of Marketing) with senior marketing leadership experience',
                'Sales': 'TOP-TIER EXECUTIVE (VP/Head of Sales) with senior sales leadership experience',
                'Product': 'TOP-TIER EXECUTIVE (VP/Head of Product) with senior product leadership experience',
                'Engineering': 'TOP-TIER EXECUTIVE (CTO/VP Engineering) with senior technology leadership experience',
                'Operations': 'TOP-TIER EXECUTIVE (VP/Head of Operations) with senior operations leadership experience'
            }
            fallback_text = domain_fallbacks.get(primary_domain, domain_fallbacks['Engineering'])
            unified_context += f"PERSONA SUMMARY: Not available. Candidate is a {fallback_text}.\n\n"
        
        unified_context += "UNIFIED CANDIDATE PROFILE (Core Identity):\n"
        unified_context += f"{strategic_summary}\n"
        unified_context += f"CV Summary: {unified_profile['cv_summary']}\n"
        unified_context += f"Master CV Text (first 1500 chars): {cv_text[:1500]}\n"  # Include full CV context
        unified_context += f"{multi_cv_note}\n"
        
        if unified_profile.get('key_skills'):
            unified_context += f"Key Skills (from CV): {', '.join(unified_profile['key_skills'][:10])}\n"
        
        if all_user_skills:
            unified_context += f"Added Skills (from user profile - ABSOLUTE PRECEDENCE): {', '.join(all_user_skills[:10])}\n"
            unified_context += "CRITICAL - PREFERENCE PRIORITY: These manually added skills take ABSOLUTE PRECEDENCE over any skills extracted from the CV text.\n"
            unified_context += "If a job requires these skills, they should be weighted 3x MORE than CV-extracted skills. These are the candidate's explicit priorities.\n"
            unified_context += "IMPORTANT: These added_skills are explicitly important to the candidate. Give significant weight to jobs that require these skills.\n"
        
        if unified_profile.get('feedback_patterns', {}).get('rejected_reasons'):
            unified_context += "Feedback Patterns (What Candidate Avoids):\n"
            for reason, count in list(unified_profile['feedback_patterns']['rejected_reasons'].items())[:5]:
                unified_context += f"- {reason} (rejected {count} time(s))\n"
        
        if unified_profile.get('custom_preferences', {}).get('preferred_roles'):
            unified_context += f"Preferred Roles: {', '.join(unified_profile['custom_preferences']['preferred_roles'][:5])}\n"
        
        # Interactive Learning: Include user ambitions in scoring context
        try:
            from utils import load_preferences, get_user_id
            user_id = get_user_id()
            preferences = load_preferences(user_id)
            user_ambitions = preferences.get('user_identity', {}).get('user_ambitions', '')
            if user_ambitions and user_ambitions.strip():
                unified_context += f"\nUSER AMBITIONS (CRITICAL - Use this to guide scoring):\n{user_ambitions.strip()}\n"
                unified_context += "IMPORTANT: If the job description aligns with the user's stated ambitions (e.g., career pivot, desired transition, strategic goal), "
                unified_context += "increase the match score by 5-10 points. Jobs that help the user achieve their stated career goals should be prioritized.\n"
        except Exception as ambitions_error:
            print(f"⚠️ Error loading user ambitions: {ambitions_error}")
            # Continue without ambitions
        
        if unified_profile.get('digital_persona_reference'):
            dp_ref = unified_profile['digital_persona_reference']
            unified_context += f"Digital Persona: {dp_ref.get('role_level', 'Senior')} in {dp_ref.get('industry_focus', 'Technology')}\n"
            if dp_ref.get('persona_summary'):
                unified_context += f"Persona Summary (Full): {dp_ref.get('persona_summary', '')}\n"
        
        # Update prompt to use Unified Profile with explicit core identity comparison
        # Adaptive Scoring: Use industry_focus and primary_domain from persona, not hardcoded values
        # Strictness Mode: Adjust instructions based on strict_industry_match flag
        if strict_industry_match:
            # Strict Mode: Aggressive industry filtering
            industry_instruction = (
                f"STRICT INDUSTRY MATCH MODE:\n"
                f"- The candidate is a SENIOR {primary_domain.upper()} LEADER with industry focus: {industry_focus}.\n"
                f"- Jobs must match the candidate's specific industry focus and primary domain ({primary_domain}).\n"
                f"- If the industry/domain doesn't match, significantly lower the score (20-40 points) or return 0%.\n"
                f"- Only {primary_domain}-driven industries are acceptable, and they should align with the candidate's industry focus.\n\n"
            )
        else:
            # Flexible Mode: Prioritize leadership skills over industry keywords
            # Flexible Scoring: 90% weight for leadership seniority, 10% for industry
            # Preference Priority: If strict_industry_match is False, IGNORE industry mismatches completely
            # Build domain-specific role examples
            domain_role_examples = {
                'Marketing': 'VP Marketing, Head of Digital Marketing, CMO, VP Growth, Head of MarTech',
                'Sales': 'VP Sales, Head of Revenue, CRO, VP Business Development, Head of Sales',
                'Product': 'VP Product, Head of Product, CPO, VP Product Management, Head of Product Strategy',
                'Engineering': 'CTO, VP Engineering, Head of Engineering, Chief Technology Officer, VP Technology',
                'Operations': 'VP Operations, Head of Operations, COO, VP Operations Management, Head of Business Operations'
            }
            role_examples = domain_role_examples.get(primary_domain, domain_role_examples['Engineering'])
            
            industry_instruction = (
                f"FLEXIBLE INDUSTRY MATCH MODE - FLEXIBLE SCORING:\n"
                f"- The candidate is a SENIOR {primary_domain.upper()} LEADER with roles like: {role_examples}.\n"
                f"- PREFERENCE PRIORITY: Since strict_industry_match is FALSE, you MUST IGNORE industry mismatches completely.\n"
                f"- Focus ONLY on the level of responsibility and leadership skills required, NOT the industry.\n"
                f"- FLEXIBLE SCORING RULE: Prioritize their leadership seniority (90% of weight) over the specific industry (10% of weight).\n"
                f"- Example: A {primary_domain} VP from one industry is an 80% match for a {primary_domain} VP in another industry, because leadership skills (90% weight) are transferable.\n"
                f"- Their core skills in {primary_domain.lower()} leadership, team management, and strategic vision apply to ANY {primary_domain.lower()}-driven industry.\n"
                f"- PRIORITIZE LEADERSHIP SKILLS over industry-specific keywords.\n"
                f"- Do NOT score 0% just because the industry is different (e.g., different {primary_domain} industries).\n"
                f"- IGNORE industry mismatches - they are irrelevant when strict_industry_match is False.\n"
                f"- Only score 0% if the industry/domain is completely different (e.g., {primary_domain} vs a completely unrelated domain).\n"
                f"- For {primary_domain}-driven industries, evaluate based on leadership skills, not industry-specific domain knowledge.\n"
                f"- As a VP/Head/Director in {primary_domain}, the candidate's skills are TRANSFERABLE across different {primary_domain} industries.\n"
                f"- Industry differences are acceptable if the role requires similar leadership and {primary_domain.lower()} skills.\n"
                f"- SCORING FORMULA: Match Score = (Leadership Seniority Match × 0.9) + (Industry Match × 0.1)\n"
                f"- CRITICAL: When strict_industry_match is False, treat industry_match as 100% (ignore industry completely).\n\n"
            )
        
        # Add Structural Skill Alignment context if pivot_mode is enabled
        structural_alignment_text = ""
        if pivot_mode and structural_alignment:
            structural_alignment_text = (
                f"\nSTRUCTURAL SKILL ALIGNMENT ANALYSIS (PIVOT MODE ENABLED):\n"
                f"{structural_alignment.get('analysis', '')}\n"
                f"Core Competencies Match: {structural_alignment.get('core_competencies_match', False)}\n"
                f"Transferable Skills: {', '.join(structural_alignment.get('transferable_skills', []))}\n"
                f"IMPORTANT: In pivot mode, evaluate jobs based on structural skill alignment, not just industry keywords.\n"
                f"If the job requires core competencies that match the candidate's transferable skills, score it higher even if the industry is different.\n\n"
            )
        
        core_identity_instruction = (
            "\nCRITICAL INSTRUCTION: Compare this job's requirements against the candidate's CORE IDENTITY, not just keywords.\n"
            "The Unified Profile above represents the candidate's true professional identity, including:\n"
            "- Their actual experience and skills (from master_cv_text)\n"
            "- Their explicitly added skills (from user profile - these are VERY important)\n"
            "- What they've learned to avoid (from feedback patterns)\n"
            "- Their preferences and priorities (from custom preferences)\n"
            "- Their professional persona (from Digital Persona)\n\n"
            f"{structural_alignment_text}"
            f"{industry_instruction}"
            "REDEFINE 'MATCH' - LEADERSHIP SCALE ALIGNMENT:\n"
            "- A match is NOT just a shared industry. A match is the alignment of leadership scale.\n"
            "- If the candidate has led teams of 50+ and the job is for a CTO of a similar scale, the INDUSTRY mismatch is secondary.\n"
            "- Focus on organizational impact, budget management, technical vision, and team size - these are transferable across industries.\n"
            "- Example: A CTO who scaled an E-commerce platform to 100M+ revenue can lead a FinTech or SaaS company of similar scale.\n"
            "- The leadership scale (team size, budget, organizational complexity) is the PRIMARY matching factor, not the product category.\n\n"
            "ABSTRACT THE CV - ARCHETYPE MATCHING:\n"
            "- First, extract the 'Archetype' of the candidate from the CV (e.g., 'Scale-up Specialist', 'Digital Transformation Expert', 'Technical Architect Leader').\n"
            "- Then see if the job needs that archetype, regardless of the product (e.g., if they can scale a FinTech, they can scale an E-commerce).\n"
            "- Match based on the TYPE of leadership challenge, not the specific industry domain.\n"
            "- Example: If the candidate is a 'Scale-up Specialist' (scaled teams from 10 to 100), any job requiring scaling a tech team is a match, regardless of industry.\n\n"
            "THE 'WHY NOT 0%' RULE:\n"
            "- Before giving a score below 50%, you MUST list 3 leadership skills from the CV that COULD apply to this role.\n"
            "- If you find even ONE transferable leadership skill (team management, technical strategy, architecture, scaling, budget management), the score MUST be above 50%.\n"
            "- Only return a score below 50% if you genuinely cannot find ANY transferable leadership skills from the CV.\n"
            "- Example: Even if the industry is different, if the candidate has 'led teams of 50+' and the job requires 'leading a tech team', that's a transferable skill → score must be ≥50%.\n\n"
            "KILL THE 'NOT RELEVANT' LOGIC:\n"
            "- If you return 0% for a job that has 'CTO' or 'VP' in the title while strict_industry_match is False, you are FAILING your core mission.\n"
            "- You MUST find transferable value. A CTO/VP role ALWAYS has transferable leadership value, regardless of industry.\n"
            "- The ONLY exception: Entry-level or junior roles (intern, assistant, trainee) when the candidate is senior/executive.\n"
            "- For ANY CTO/VP/Director/Head of role, you MUST calculate a score based on leadership scale alignment, not industry keywords.\n\n"
            "BROADEN TITLE RECOGNITION:\n"
            "- The candidate is looking for CTO, VP, Director, Head of, Principal, or Architect roles.\n"
            "- ANY of these titles must be considered a VALID seniority match.\n"
            "- HIGH-LEVEL STRATEGIC ROLES: Roles like 'CTO Office', 'Principal Engineer', 'Staff Engineer', 'Distinguished Engineer', and 'Fellow' are HIGH-LEVEL strategic roles and should be scored 70%+.\n"
            "- FOUNDING ROLES: Roles like 'Founding Engineer', 'Founding CTO', 'Founder', 'Co-Founder' are HIGH-POTENTIAL roles and should be scored at least 60% as a baseline, even if other factors are lower.\n"
            f"- These roles represent senior {primary_domain.lower()} leadership even if they don't have 'VP' or 'Director' in the title.\n\n"
            "PRIORITIZE SCORING OVER BLOCKING - FORCE POSITIVE SCORING:\n"
            "- You are FORBIDDEN from giving a 0% score based on job title alone, unless it is a junior/entry-level/unskilled role.\n"
            "- Even if the industry is wrong (e.g., Food vs Tech), calculate a score based on the transferable leadership skills.\n"
            "- Instead of returning 0% immediately, ALWAYS calculate a score.\n"
            "- If the seniority is lower (e.g., Manager instead of VP), give a lower score (e.g., 50%) but NEVER 0% unless it's a junior/entry-level role.\n"
            "- Only return 0% for clearly entry-level or junior roles (intern, assistant, trainee, unskilled).\n"
            "- For all other roles, calculate a score based on the match quality and transferable skills.\n\n"
            "Do NOT just match keywords. Instead, evaluate:\n"
            f"1. Does this job align with the candidate's core professional identity as a SENIOR {primary_domain.upper()} LEADER?\n"
            "2. Does it match their preferred role level? (Industry can be different if skills are transferable and flexible mode is ON)\n"
            "3. Does it avoid patterns they've rejected in the past?\n"
            "4. Does it leverage their key skills AND their added_skills from the profile?\n"
            "5. Does it require skills that match the master_cv_text experience?\n"
            "6. Does the leadership scale align? (Team size, budget, organizational complexity)\n"
            "7. Does the job need the candidate's 'Archetype' (e.g., Scale-up Specialist, Digital Transformation Expert)?\n\n"
            "PROFILE-CENTRIC SCORING RULES:\n"
            "- If the job requires skills from the 'added_skills' list, this is a STRONG positive signal.\n"
            "- If the job matches patterns the user has rejected, significantly lower the score (20-40 points) or return 0%.\n"
            "- If the job doesn't align with master_cv_text experience, be honest and lower the score.\n"
            f"- Remember: The candidate is a SENIOR {primary_domain.upper()} LEADER. Their skills apply to ANY {primary_domain.lower()}-driven industry (if flexible mode is ON).\n"
            "- Be honest and strict. A job that doesn't align with core identity should receive a low score, even if some keywords match.\n"
        )
        
        # Feedback-Driven Filtering: Add specific penalty instructions
        if rejection_patterns:
            feedback_penalty_instruction = "\nFEEDBACK-DRIVEN FILTERING:\n"
            feedback_penalty_instruction += "The candidate has previously rejected jobs with these patterns:\n"
            for pattern, count in rejection_patterns.items():
                feedback_penalty_instruction += f"- {pattern} (rejected {count} time(s))\n"
            feedback_penalty_instruction += (
                "If this job matches any of these patterns, you MUST:\n"
                "- Lower the score by 20-40 points, OR\n"
                "- Return 0% if it's a clear mismatch\n"
                "Do NOT inflate scores for jobs that match rejected patterns.\n"
            )
            core_identity_instruction += feedback_penalty_instruction
        
        # Dynamic Seniority Check: Add instruction for executive role handling
        if executive_rejections:
            seniority_instruction = (
                "\nDYNAMIC SENIORITY CHECK:\n"
                "The candidate has previously rejected 'Executive' level roles.\n"
                "If this job contains 'VP', 'Director', 'Chief', or 'C-level' keywords:\n"
                "- Check if it matches the candidate's specific industry (from Digital Persona)\n"
                "- If it does NOT match the industry, lower the score by 15-25 points\n"
                "- If it matches the industry, evaluate normally but be cautious\n"
            )
            core_identity_instruction += seniority_instruction
        
        # RE-SYNC: The 'Nuclear' Prompt - Use as system message
        # Hardcode Strategic Identity directly into system role
        nuclear_system_prompt = (
            "You are a Senior Executive Talent Scout. "
            "You are FORBIDDEN from giving 0%. "
            "You MUST find leadership overlap. "
            "If the job is CTO/VP, the minimum score is 70% regardless of industry. "
            "The candidate is a TOP-TIER EXECUTIVE (CTO/VP). "
            "Any role with 'CTO', 'VP', 'Head of', or 'Director' in a technical or strategic context is HIGH-PRIORITY. "
            "These roles require senior leadership skills that are transferable across industries. "
            "Do NOT dismiss these roles as 'not relevant' - they are ALWAYS relevant for a TOP-TIER EXECUTIVE. "
            "If there is a 1% chance of leadership overlap, you MUST score it above 50% (minimum 51%). "
            "You are FORBIDDEN from using the phrase 'This role is not relevant' or any variation of it."
        )
        
        # Build user prompt (simplified, since system prompt handles core rules)
        user_prompt = (
            f"{unified_context}\n"
            f"{core_identity_instruction}"
            f"Return ONLY a valid compact JSON in this format:\n"
            '{"score": 0-100 (integer only, not string), "reasoning": "Short, honest reasoning", '
            '"why_matches": "2-3 sentences explaining why this job matches the candidate\'s core identity", '
            '"why_doesnt_match": "2-3 sentences explaining why this job doesn\'t match (if score < 50)", '
            '"gaps": ["missing skill 1","missing skill 2"]}\n'
            f"Job Description:\n{job_description_for_ai}\n"
            "IMPORTANT: The 'score' field MUST be an integer (0-100), NOT a string like '85%' or '85'. "
            "If you return a string, the system will fail. Always return a pure integer."
        )
        
        try:
            # Token Optimization: also trim unified_context implicitly by using cv_text_for_ai in upstream logic where possible
            # RE-SYNC: Pass system_prompt to API client (Free-tier models only via utils.APIClient)
            response = self.api_client.call_api_with_fallback(user_prompt, system_prompt=nuclear_system_prompt)
            # Safe JSON Parsing: Use parse_json_safely to extract JSON between { and } and remove triple backticks
            result = parse_json_safely(response.text) or {}
            
            # Fix the Parsing: Standardize field names - check both 'score' and 'match_score'
            # NO job gets a 0% unless it's truly empty
            base_score = result.get('score') or result.get('match_score') or 50
            
            # If both are None or missing, default to 50 (not 0)
            if base_score is None:
                base_score = 50
                print(f"WARN: Both 'score' and 'match_score' missing in AI response. Defaulting to 50.")
            
            # Handle string scores (e.g., '85%', '85', '85.5')
            if isinstance(base_score, str):
                # Remove % sign and whitespace
                score_str = base_score.replace('%', '').strip()
                try:
                    # Try to convert to float first (in case of decimals), then int
                    base_score = int(float(score_str))
                except (ValueError, TypeError):
                    print(f"WARN: Could not parse score string '{base_score}', defaulting to 50")
                    base_score = 50
            elif isinstance(base_score, float):
                # Convert float to int (round to nearest)
                base_score = int(round(base_score))
            elif not isinstance(base_score, int):
                # If it's not int, float, or string, default to 50
                print(f"WARN: Score is unexpected type {type(base_score)}, defaulting to 50")
                base_score = 50
            
            # Fix Scoring Logic: If job is 'Executive' or matches 'Industry Focus' (Technology Leadership), give at least 30% base score
            # Check industry focus match BEFORE other adjustments
            industry_focus_match = False
            if digital_persona:
                industry_focus = digital_persona.get('industry_focus', '').lower()
                job_lower_for_industry = job_description.lower()
                # Check if job matches industry focus (e.g., "Technology Leadership")
                if industry_focus and ('technology leadership' in industry_focus or 'general tech' in industry_focus):
                    # Technology Leadership is broad - any tech job should match
                    tech_keywords = ['technology', 'tech', 'software', 'engineering', 'digital', 'it', 'cto', 'vp', 'director']
                    if any(kw in job_lower_for_industry for kw in tech_keywords):
                        industry_focus_match = True
                elif industry_focus and industry_focus in job_lower_for_industry:
                    industry_focus_match = True
            
            # Check if job is executive role
            is_executive_role = False
            if job_title:
                job_title_upper = job_title.upper()
                is_executive_role = ('CTO' in job_title_upper or 'VP' in job_title_upper or 'CHIEF' in job_title_upper or 
                                    'VICE PRESIDENT' in job_title_upper or 'DIRECTOR' in job_title_upper or 
                                    'HEAD OF' in job_title_upper)
            
            # Fix Scoring Logic: Executive jobs or Industry Focus matches get at least 30% base score
            if (is_executive_role or industry_focus_match) and base_score < 30:
                old_score = base_score
                base_score = 30  # Minimum 30% for executive or industry match
                print(f"🔧 Fix Scoring Logic: Job '{job_title if job_title else 'Unknown'}' is Executive or matches Industry Focus. Base score boosted from {old_score} to 30% (minimum).")
                # Update reasoning
                original_reasoning = result.get('reasoning', '')
                min_score_note = f"🔧 Minimum Score Applied: This role is Executive-level or matches your Industry Focus (Technology Leadership). Base score set to 30% minimum."
                if min_score_note not in original_reasoning:
                    result['reasoning'] = f"{original_reasoning}\n\n{min_score_note}" if original_reasoning else min_score_note
                result['score'] = base_score
            
            # Ensure score is in valid range (0-100)
            base_score = max(0, min(100, base_score))
            
            # CRITICAL FIX: Hardcoded Safety in analyze_match - Overpower AI's 0% refusal
            # AFTER the AI returns its JSON, check if this is an executive role with low score
            # This happens BEFORE any other adjustments to ensure executive roles are protected
            if is_executive_role and base_score < 50:
                old_score = base_score
                base_score = 60
                # Reasoning Injection: Update reasoning string
                original_reasoning = result.get('reasoning', '')
                leadership_guardrail_note = "🔧 Leadership Guardrails: AI gave a low score, but this role was recognized as a high-priority executive role (CTO/VP/Chief/Director/Head of). Score boosted to 60%."
                if leadership_guardrail_note not in original_reasoning:
                    result['reasoning'] = f"{original_reasoning}\n\n{leadership_guardrail_note}" if original_reasoning else leadership_guardrail_note
                print(f"🔧 CRITICAL FIX: Hardcoded Safety triggered for '{job_title}'. Score boosted from {old_score} to 60 (executive role detected).")
                # Update result['score'] to reflect the boost
                result['score'] = base_score
            
            # Smart Weighting: Apply scoring_weights from preferences.json
            try:
                # Get user_id from session state if available, otherwise use default
                user_id = None
                try:
                    import streamlit as st
                    user_id = st.session_state.get('user_id', None)
                except Exception:
                    pass
                
                preferences = load_preferences(user_id)
                scoring_weights = preferences.get('scoring_weights', {})
                
                if scoring_weights:
                    # Calculate weighted score based on job content
                    job_text_lower = job_description.lower()
                    cv_text_lower = cv_text.lower()
                    
                    # Calculate average weight multiplier based on relevant skills found
                    weight_multiplier = 1.0
                    matching_weights = []
                    
                    # Check for skills in job description and CV
                    skill_keywords = {
                        'ecommerce': ['e-commerce', 'ecommerce', 'shopify', 'magento', 'retail tech'],
                        'python': ['python'],
                        'javascript': ['javascript', 'js', 'node.js', 'nodejs'],
                        'aws': ['aws', 'amazon web services'],
                        'docker': ['docker'],
                        'kubernetes': ['kubernetes', 'k8s'],
                        'react': ['react', 'reactjs'],
                        'nodejs': ['node.js', 'nodejs'],
                        'shopify': ['shopify'],
                        'magento': ['magento'],
                        'leadership': ['leadership', 'lead', 'manage', 'team'],
                        'technology': ['technology', 'tech', 'engineering'],
                        'management': ['management', 'manager', 'director'],
                        'cto': ['cto', 'chief technology officer'],
                        'vp': ['vp', 'vice president'],
                        'architect': ['architect', 'architecture']
                    }
                    
                    # Find matching skills and collect their weights
                    for skill_key, keywords in skill_keywords.items():
                        if any(keyword in job_text_lower for keyword in keywords):
                            weight = scoring_weights.get(skill_key, 1.0)
                            matching_weights.append(weight)
                    
                    # Calculate average weight (if skills matched) or use 1.0
                    if matching_weights:
                        weight_multiplier = sum(matching_weights) / len(matching_weights)
                    
                    # Apply weight multiplier to base score
                    weighted_score = base_score * weight_multiplier
                    # Cap at 100
                    final_score = min(100, weighted_score)
                    
                    result['score'] = int(final_score)
                    
                    # Add note to reasoning if weighting was applied
                    if weight_multiplier > 1.0:
                        result['reasoning'] = result.get('reasoning', '') + f" (Score adjusted by preferences: {weight_multiplier:.2f}x)"
            except Exception as e:
                # If weighting fails, use base score
                print(f"⚠️ Error applying scoring weights: {e}")
                result['score'] = base_score
            
            # Bonus scoring: If both CV and job have E-commerce focus, add small boost
            if has_cv_ecommerce and has_job_ecommerce:
                original_score = result.get('score', base_score)
                # Ensure original_score is integer
                if isinstance(original_score, str):
                    original_score = int(float(original_score.replace('%', '').strip()))
                elif isinstance(original_score, float):
                    original_score = int(round(original_score))
                
                # Add up to 10 point boost if both are E-commerce focused (cap at 100)
                bonus = min(10, 100 - original_score)
                if bonus > 0:
                    result['score'] = original_score + bonus
                    # Update reasoning to mention E-commerce alignment
                    reasoning = result.get('reasoning', '')
                    if 'e-commerce' not in reasoning.lower() and 'ecommerce' not in reasoning.lower():
                        result['reasoning'] = f"{reasoning} Strong E-commerce experience alignment." if reasoning else "Strong E-commerce experience alignment."
            
            # Extract reasoning transparency fields
            why_matches = result.get('why_matches', '')
            why_doesnt_match = result.get('why_doesnt_match', '')
            reasoning = result.get('reasoning', '')
            
            # Combine reasoning fields for full transparency
            full_reasoning = reasoning
            if why_matches:
                full_reasoning += f"\n\n✅ Why This Matches:\n{why_matches}"
            if why_doesnt_match and base_score < 50:
                full_reasoning += f"\n\n❌ Why This Doesn't Match:\n{why_doesnt_match}"
            
            # Preference Weighting: Apply 3x weight for added_skills and feedback_log
            # Calculate bonus for added_skills match (3x weight)
            added_skills_bonus = 0
            if all_user_skills:
                # Check if job requires any of the added_skills
                job_requires_added_skills = any(skill.lower() in job_lower for skill in all_user_skills)
                if job_requires_added_skills:
                    # 3x weight bonus: boost score by 20-30 points
                    added_skills_bonus = min(30, 100 - final_score)  # Cap at 30 points, don't exceed 100
            
            # Skills Logic: Check for blacklisted/trashed skills and apply significant penalty
            blacklisted_skills_penalty = 0
            try:
                from utils import load_preferences
                preferences = load_preferences()
                blacklisted_skills = preferences.get('user_identity', {}).get('blacklisted_skills', [])
                
                if blacklisted_skills:
                    # Check if job description contains any blacklisted skills
                    job_lower_for_skills = job_description.lower()
                    for skill in blacklisted_skills:
                        if skill.lower() in job_lower_for_skills:
                            # Skills Logic: Significantly lower the match score
                            blacklisted_skills_penalty += 50  # Large penalty per blacklisted skill
                            print(f"🚫 Blacklisted skill '{skill}' found in job. Applying penalty.")
            except Exception as e:
                print(f"WARN: Error checking blacklisted skills: {e}")
            
            # Apply feedback-driven penalties before final score calculation (3x weight)
            penalty = 0
            if rejection_patterns:
                # Apply penalties based on rejection patterns (3x weight - multiply by 3)
                if rejection_patterns.get('wrong_role', 0) > 0:
                    # Check if job matches wrong role pattern
                    job_title_keywords = ['junior', 'entry', 'intern', 'assistant']
                    if any(kw in job_lower for kw in job_title_keywords):
                        penalty += 30 * 3  # 3x weight: 90 point penalty for wrong role level
                
                if rejection_patterns.get('low_salary', 0) > 0:
                    low_salary_keywords = ['entry level', 'junior', 'intern', 'starting salary']
                    if any(kw in job_lower for kw in low_salary_keywords):
                        penalty += 20 * 3  # 3x weight: 60 point penalty for low salary indicators
                
                if rejection_patterns.get('location', 0) > 0:
                    # Location penalty would need specific location matching
                    # For now, apply a smaller penalty (3x weight)
                    penalty += 10 * 3  # 3x weight: 30 point penalty
                
                if rejection_patterns.get('company_reputation', 0) > 0:
                    # Company reputation penalty would need company name matching
                    # For now, apply a smaller penalty (3x weight)
                    penalty += 15 * 3  # 3x weight: 45 point penalty
            
            # Apply dynamic seniority check penalty
            if feedback_log:
                executive_rejections = [e for e in feedback_log if 'Executive' in str(e.get('reason', '')) or 'executive' in str(e.get('reason', '')).lower()]
                if executive_rejections:
                    executive_keywords = ['vp', 'vice president', 'director', 'chief', 'c-level', 'c-suite']
                    job_has_executive = any(kw in job_lower for kw in executive_keywords)
                    
                    if job_has_executive:
                        industry_match_check = False
                        if digital_persona:
                            industry_focus = digital_persona.get('industry_focus', '').lower()
                            if industry_focus and industry_focus in job_lower:
                                industry_match_check = True
                        
                        if not industry_match_check:
                            penalty += 25  # Penalty for executive role not matching industry
            
            # Fix the Parsing: Standardize field names - check both 'score' and 'match_score'
            # Ensure final score is integer (not string)
            # Fix Scoring Logic: Ensure potential_score (base_score) is properly added to final score
            # Start with base_score (the potential score from AI) as the foundation
            potential_score = base_score  # This is the base/potential score from AI
            final_score = result.get('score') or result.get('match_score') or potential_score
            if isinstance(final_score, str):
                final_score = int(float(final_score.replace('%', '').strip()))
            elif isinstance(final_score, float):
                final_score = int(round(final_score))
            elif not isinstance(final_score, int):
                final_score = int(potential_score)  # Use potential_score as fallback
            
            # Fix Scoring Logic: Ensure we start from potential_score (base_score) if final_score is 0
            if final_score == 0 and potential_score > 0:
                final_score = potential_score
                print(f"🔧 Fix Scoring Logic: Using potential_score ({potential_score}) as final_score base.")
            
            # CRITICAL FIX: Apply hardcoded safety check again after all adjustments
            # This ensures executive roles never get below 50% even after penalties
            # This is a FINAL safety net after all bonuses/penalties are applied
            # The 'Executive' Regex: Case-insensitive and handles titles like 'Founding Engineer' or 'Head of' by giving them at least 70% automatically if the CV is a match
            if job_title:
                job_title_upper = job_title.upper()
                job_title_lower_check = job_title.lower()  # Use lowercase for case-insensitive matching
                
                # Case-insensitive executive role detection
                is_executive_role = ('CTO' in job_title_upper or 'VP' in job_title_upper or 'CHIEF' in job_title_upper or 
                                    'VICE PRESIDENT' in job_title_upper or 'DIRECTOR' in job_title_upper or 
                                    'HEAD OF' in job_title_lower_check or 'HEAD OF' in job_title_upper)
                
                # Check for 'Founding Engineer' or similar founding roles (case-insensitive)
                is_founding_engineer = ('FOUNDING' in job_title_upper and 'ENGINEER' in job_title_upper) or \
                                      ('FOUNDING ENGINEER' in job_title_upper) or \
                                      ('FOUNDER' in job_title_upper and 'ENGINEER' in job_title_upper)
                
                # The 'Executive' Regex: Handle 'Founding Engineer' or 'Head of' with at least 70% automatically if the CV is a match
                if is_founding_engineer or ('HEAD OF' in job_title_lower_check or 'HEAD OF' in job_title_upper):
                    # If CV is a match (has any tech/leadership keywords), give at least 70%
                    cv_lower_check = cv_text.lower() if cv_text else ''
                    has_tech_match = any(kw in cv_lower_check for kw in ['cto', 'vp', 'director', 'engineer', 'technology', 'tech', 'leadership', 'senior', 'chief'])
                    if has_tech_match and final_score < 70:
                        old_final_score = final_score
                        final_score = 70
                        # Reasoning Injection: Update reasoning string
                        original_reasoning = result.get('reasoning', '')
                        leadership_guardrail_note = f"🔧 Executive Regex (Founding Engineer/Head of): Role recognized as executive-level. Score boosted from {old_final_score}% to 70% (minimum for executive roles with CV match)."
                        if leadership_guardrail_note not in original_reasoning:
                            result['reasoning'] = f"{original_reasoning}\n\n{leadership_guardrail_note}" if original_reasoning else leadership_guardrail_note
                            # Update full_reasoning if it exists
                            if 'full_reasoning' in locals():
                                full_reasoning = f"{full_reasoning}\n\n{leadership_guardrail_note}"
                        print(f"🔧 Executive Regex: '{job_title}' recognized as Founding Engineer/Head of. Score boosted from {old_final_score} to 70% (CV match detected).")
                
                # Standard executive role boost (CTO, VP, Chief, Director)
                if is_executive_role and final_score < 50:
                    old_final_score = final_score
                    final_score = 60
                    # Reasoning Injection: Update reasoning string
                    original_reasoning = result.get('reasoning', '')
                    leadership_guardrail_note = "🔧 Leadership Guardrails (Final Check): Final score was below 50% after all adjustments, but this role was recognized as a high-priority executive role. Score boosted to 60%."
                    if leadership_guardrail_note not in original_reasoning:
                        result['reasoning'] = f"{original_reasoning}\n\n{leadership_guardrail_note}" if original_reasoning else leadership_guardrail_note
                        # Update full_reasoning if it exists
                        if 'full_reasoning' in locals():
                            full_reasoning = f"{full_reasoning}\n\n{leadership_guardrail_note}"
                    print(f"🔧 CRITICAL FIX: Hardcoded Safety triggered (final check) for '{job_title}'. Score boosted from {old_final_score} to 60 (executive role detected).")
            
            # Preference Priority: Apply added_skills bonus (ABSOLUTE PRECEDENCE - 5x weight)
            added_skills_bonus = 0
            if all_user_skills:
                # Check if job requires any of the manually added skills
                job_requires_added_skills = any(skill.lower() in job_lower for skill in all_user_skills)
                if job_requires_added_skills:
                    # Preference Priority: 5x weight bonus - ABSOLUTE PRECEDENCE
                    # Boost score by 30-50 points (was 20-30) to reflect absolute precedence
                    added_skills_bonus = min(50, 100 - final_score)  # Increased cap (was 30), don't exceed 100
            
            # Fix 0% for Founding CTO: Recognize 'Founding Engineer / CTO' as high-potential role
            founding_bonus = 0
            if is_founding_role:
                # Founding roles get at least 60% as baseline
                if final_score < 60:
                    founding_bonus = 60 - final_score
                    print(f"DEBUG: Founding role detected. Boosting score from {final_score} to at least 60% (baseline for founding roles)")
            
            # Apply penalty and bonuses (including blacklisted skills penalty)
            # Skills Logic: blacklisted_skills_penalty significantly lowers match score for jobs containing blacklisted skills
            # Fix Scoring Logic: Ensure potential_score is properly added - start from base_score if needed
            if final_score == 0 and 'potential_score' in locals() and potential_score > 0:
                final_score = potential_score
            final_score = max(0, final_score - penalty - blacklisted_skills_penalty + added_skills_bonus + founding_bonus)
            
            # Update reasoning if blacklisted skills penalty was applied
            if blacklisted_skills_penalty > 0:
                reasoning = result.get('reasoning', '')
                blacklist_note = f"⚠️ This job contains skills you've blacklisted. Score reduced by {blacklisted_skills_penalty} points."
                result['reasoning'] = f"{reasoning}\n\n{blacklist_note}" if reasoning else blacklist_note
            
            # Ensure score is in valid range (0-100)
            final_score = max(0, min(100, final_score))
            
            # HARD OVERRIDE LOGIC: Title-Based Safety Net and Founding Role Boost
            old_score_before_override = final_score
            override_applied = False
            override_reason = ""
            
            # Title-Based Safety Net: If job title contains CTO/VP Engineering/VP Technology and score < 70, force to 60
            title_override_keywords = ['cto', 'chief technology officer', 'vp engineering', 'vp technology', 'vice president engineering', 'vice president technology']
            if any(kw in job_title_lower for kw in title_override_keywords):
                if final_score < 70:
                    final_score = 60
                    override_applied = True
                    override_reason = f"Title-Based Safety Net: Job title contains CTO/VP Engineering/VP Technology. Score boosted from {old_score_before_override} to 60."
                    print(f"DEBUG: Manual override applied for job '{job_title}'. {override_reason}")
            
            # Founding Role Boost: If title contains 'Founding' or 'Founder' and score < 75, force to 75
            founding_override_keywords = ['founding', 'founder', 'co-founder', 'cofounder']
            if any(kw in job_title_lower for kw in founding_override_keywords):
                if final_score < 75:
                    # Only apply if title-based override didn't already boost it higher
                    if not override_applied or final_score < 75:
                        old_score_for_founding = final_score if not override_applied else old_score_before_override
                        final_score = 75
                        override_applied = True
                        override_reason = f"Founding Role Boost: Job title contains Founding/Founder. Score boosted from {old_score_for_founding} to 75."
                        print(f"DEBUG: Manual override applied for job '{job_title}'. {override_reason}")
            
            # Update reasoning if override was applied
            if override_applied:
                reasoning = result.get('reasoning', '')
                if override_reason not in reasoning:
                    result['reasoning'] = f"{reasoning}\n\n🔧 {override_reason}" if reasoning else override_reason
                    full_reasoning = f"{full_reasoning}\n\n🔧 {override_reason}" if 'full_reasoning' in locals() else override_reason
            
            # Ensure score is still in valid range after override (0-100)
            final_score = max(0, min(100, final_score))

            # Attach job_url (Strict Caching happens at the very end, after Career Horizon is applied)
            result["job_url"] = job_url
            
            # Debug the 0%: Log AI reason for 0% score - FULL reasoning
            if final_score == 0:
                # Debug Reasonings: Keep the print but ensure it logs the FULL reasoning
                full_reasoning_text = full_reasoning if 'full_reasoning' in locals() else (reasoning if 'reasoning' in locals() else 'Reasoning not available')
                print(f"DEBUG: AI Reason for 0% score (FULL REASONING): {full_reasoning_text}")
                print(f"DEBUG: Why doesn't match: {why_doesnt_match if 'why_doesnt_match' in locals() else 'N/A'}")
                print(f"DEBUG: Gaps identified: {result.get('gaps', 'N/A')}")
                print(f"DEBUG: Penalty applied: {penalty}")
                print(f"DEBUG: Added skills bonus: {added_skills_bonus}")
                print(f"DEBUG: Base score before adjustments: {base_score if 'base_score' in locals() else 'N/A'}")
                print(f"DEBUG: Has Senior Role: {has_senior_role if 'has_senior_role' in locals() else 'N/A'}")
                print(f"DEBUG: Is Junior Role: {'N/A'}")
                print(f"DEBUG: Job Title/Description (first 200 chars): {job_description[:200] if 'job_description' in locals() else 'N/A'}")
            
            # Fix the Parsing: Ensure both 'score' and 'match_score' are set to the same value
            # Standardize so NO job gets a 0% unless it's truly empty
            if final_score == 0:
                # Emergency fallback: If score is 0, check if it's truly empty or if we should default to 50
                if job_title and len(job_title.strip()) > 0:
                    # Job has a title, so it's not truly empty - default to 50 instead of 0
                    print(f"⚠️ WARN: Score is 0 but job has title '{job_title}'. Defaulting to 50 to prevent false negatives.")
                    final_score = 50

            # Career Horizon (Additive Layer): compute bonus points and add without overriding base score.
            base_match_score = int(final_score) if isinstance(final_score, int) else int(float(final_score))
            career_horizon_score = 0.0
            career_horizon_bonus_points = 0
            try:
                career_horizon_score = float(self._career_horizon_score(job_title or "", job_description or ""))
                career_horizon_bonus_points = int(self._career_horizon_bonus_points(job_title or "", job_description or ""))
            except Exception:
                career_horizon_score = 0.0
                career_horizon_bonus_points = 0
            if career_horizon_bonus_points > 0:
                final_score = min(100, base_match_score + career_horizon_bonus_points)
                # Add explanation note (additive only)
                try:
                    full_reasoning = (full_reasoning if 'full_reasoning' in locals() else reasoning) or ""
                    full_reasoning = full_reasoning + f"\n\n🌱 Career Horizon Bonus: +{career_horizon_bonus_points} points (score={career_horizon_score:.2f}, weight additive)."
                except Exception:
                    pass
            else:
                final_score = base_match_score
            
            # Return final analysis with both old and new formats for compatibility
            # Ensure all scores are integers (not strings) and both field names are set
            response_payload = {
                "score": int(final_score),  # Old format (integer)
                "match_score": int(final_score),  # New format (integer) - standardized
                "base_match_score": int(base_match_score),
                "career_horizon_score": float(career_horizon_score),
                "career_horizon_bonus_points": int(career_horizon_bonus_points),
                "reasoning": full_reasoning if full_reasoning else reasoning,  # Old format with transparency
                "explanation": full_reasoning if full_reasoning else reasoning,  # New format with transparency
                "gaps": result.get('gaps', []),
                "why_matches": why_matches,  # Transparency field
                "why_doesnt_match": why_doesnt_match  # Transparency field
            }

            # Persist to strict cache (no redundant spending)
            try:
                if job_url:
                    self._set_cached_job_analysis(job_url, dict(response_payload))
            except Exception:
                pass

            return response_payload
        except Exception as e:
            import traceback
            print(f"ERROR in analyze_match: {e}\n{traceback.format_exc()}")
            # Fallback: return default analysis with integer score
            return {
                "score": 0,  # Integer, not string
                "match_score": 0,  # Integer, not string
                "reasoning": f"Analysis failed: {str(e)[:200]}",
                "explanation": f"Analysis failed: {str(e)[:200]}",
                "gaps": ["Analysis Error"],
                "why_matches": "",
                "why_doesnt_match": "Analysis could not be completed due to an error."
            }
    
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
            response = self.api_client.call_api_with_fallback(prompt)
            # Safe JSON Parsing: Use parse_json_safely to extract JSON between { and } and remove triple backticks
            dossier = parse_json_safely(response.text) or {}
            
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
        job_language = detect_language(job_description)
        
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
            # Hebrew cover letter prompt - Extended and detailed (High-Impact, Value-Driven Language)
            prompt = (
                "אתה סוכן AI מומחה ליצירת מכתבי מקדים מקצועיים ברמה ביצועית עם שפה אסרטיבית וממוקדת ערך. "
                "צור מכתב מקדים מקצועי ומפורט בעברית באורך של 800-1200 תווים (לא פחות מ-800, לא יותר מ-1200) עבור משרה זו. "
                "המכתב חייב להיות מכתב מלא ומקצועי ברמה ביצועית עם שפה אסרטיבית וממוקדת ערך, לא סיכום קצר. "
                "השתמש בשפה אסרטיבית ובטוחה המדגישה ערך מוחשי, השפעה מדידה, ומנהיגות אסטרטגית. "
                "תוך שימוש רק בניסיון, מיומנויות ותפקידים המתוארים בקורות החיים הבאים. "
                "אסור להמציא מיומנויות, תארים או חובות שלא קיימים במקור. "
                "המכתב צריך לכלול: פתיחה חזקה ואסרטיבית המתקשרת ערך מיידי, הדגשת ניסיון רלוונטי עם הישגים קונקרטיים, התאמה אגרסיבית לדרישות המשרה המדגישה התאמה אסטרטגית, וסיום חזק שיוצר דחיפות. "
                "התמקד בהתאמה בין הניסיון מהקורות חיים לבין דרישות המשרה תוך שימוש בשפה אסרטיבית וממוקדת ערך המדגימה ביטחון ומנהיגות.\n"
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
            response = self.api_client.call_api_with_fallback(prompt)
            # Cover Letter Guard: Validate response and response.text before accessing
            if response and hasattr(response, 'text') and response.text:
                cover_letter = response.text.strip()
            else:
                # Response is invalid - use fallback
                raise ValueError("Invalid API response: response.text is missing or empty")
            
            # Ensure cover_letter is not empty or None
            if not cover_letter or len(cover_letter) == 0:
                raise ValueError("Cover letter text is empty")
            
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
            
            # Validation: Ensure we never return None
            if cover_letter is None or len(cover_letter) == 0:
                raise ValueError("Cover letter is None or empty after processing")
            
            return cover_letter
        except Exception as e:
            print(f"WARN: Cover letter generation failed: {e}. Using fallback.")
            # Fallback Content: Generate basic cover letter using job_description and cv_text
            return self._generate_fallback_cover_letter(job_description, cv_text, job_language)
    
    def _generate_fallback_cover_letter(self, job_description, cv_text, job_language):
        """
        Fallback Content: Generates a basic cover letter using just job_description and cv_text directly.
        This function is called when AI generation fails to ensure we never return None.
        Returns a string with a basic template (minimum 800 characters).
        """
        # Generate fallback based on language
        if job_language == 'he':
            fallback_text = (
                "אני פונה אליכם לגבי משרה זו. הניסיון והמיומנויות שלי מתאימים לדרישות המשרה. "
                "יש לי רקע עשיר בתחום הטכנולוגיה והניהול, עם התמחות בתחומים רלוונטיים. "
                "תבסס על הניסיון המפורט בקורות החיים שלי, אני מאמין שאוכל לתרום משמעותית לצוות ולחברה. "
                "אשמח להזדמנות לדון כיצד אוכל להוסיף ערך לתפקיד זה ולחברה שלכם."
            )
        else:
            fallback_text = (
                "I am writing to express my interest in this position. My experience and skills align well with the job requirements. "
                "I bring a strong background in technology and leadership, with expertise in relevant areas. "
                "Based on my detailed experience outlined in my CV, I believe I can make a significant contribution to your team and organization. "
                "I would welcome the opportunity to discuss how I can add value to this role and your company."
            )
        
        # Ensure minimum 800 characters (pad if needed)
        if len(fallback_text) < 800:
            padding = " " * (800 - len(fallback_text))
            fallback_text = fallback_text + padding
        
        # Ensure maximum 1200 characters
        return fallback_text[:1200] if len(fallback_text) > 1200 else fallback_text
    
    def answer_application_question(self, question, cv_text, job_description):
        """
        Answers common application questions using AI based on the candidate's CV.
        Detects language of question and responds in the same language.
        """
        question_language = detect_language(question)
        
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
            response = self.api_client.call_api_with_fallback(prompt)
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
            response = self.api_client.call_api_with_fallback(prompt)
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
    
    def analyze_multi_role_match(self, job_description, cv_text, skill_bucket=None, master_profile=None, digital_persona=None, job_url=None, job_title=None):
        """
        Multi-Role Analysis: Analyzes the CV for multiple possible roles (CTO, VP, Architect).
        Returns the best fit among these roles with a match_score.
        
        Args:
            job_description: The job description text
            cv_text: The CV text
            skill_bucket: Optional skill bucket list
            master_profile: Optional master search profile
            digital_persona: Optional digital persona dict
        
        Returns:
            dict with:
            - 'best_role': str (CTO/VP/Architect/Other)
            - 'match_score': int (0-100) - best match score among roles
            - 'role_analyses': dict with scores for each role
            - 'reasoning': str - explanation of best fit
        """
        # Stop Credit Leak + Strict Caching: analyze each job_url ONLY ONCE.
        # Instead of 3 AI calls (CTO/VP/Architect), do a single cached analyze_match and infer best_role heuristically.
        if job_url:
            analysis = self.analyze_match(
                job_description,
                cv_text,
                skill_bucket=skill_bucket,
                master_profile=master_profile,
                digital_persona=digital_persona,
                job_title=job_title,
                job_url=job_url
            )
            score_val = analysis.get('match_score', analysis.get('score', 0)) or 0
            # Heuristic best-role inference from title (no extra AI calls)
            title_text = (job_title or "") + " " + (job_description[:200] if job_description else "")
            t = title_text.lower()
            if "cto" in t or "chief technology officer" in t:
                best_role = "CTO"
            elif "vp" in t or "vice president" in t:
                best_role = "VP"
            elif "architect" in t:
                best_role = "Architect"
            else:
                best_role = "Other"

            role_analyses = {
                best_role: {
                    "score": int(score_val) if isinstance(score_val, int) else 0,
                    "reasoning": analysis.get("reasoning", analysis.get("explanation", ""))
                }
            }
            best_score = int(score_val) if isinstance(score_val, int) else 0
            best_reasoning = analysis.get("reasoning", analysis.get("explanation", ""))
        else:
            # Fallback legacy behavior (no stable URL to cache against)
            target_roles = ['CTO', 'VP', 'Architect']
            role_analyses = {}
            for role in target_roles:
                try:
                    role_context = f"This position is for a {role} role. "
                    enhanced_job_description = role_context + (job_description or "")
                    analysis = self.analyze_match(
                        enhanced_job_description,
                        cv_text,
                        skill_bucket=skill_bucket,
                        master_profile=master_profile,
                        digital_persona=digital_persona,
                        job_title=job_title,
                        job_url=None
                    )
                    role_analyses[role] = {
                        'score': analysis.get('score', 0),
                        'reasoning': analysis.get('reasoning', 'No reasoning available')
                    }
                except Exception as e:
                    print(f"WARN: Failed to analyze role {role}: {e}")
                    role_analyses[role] = {'score': 0, 'reasoning': f'Analysis failed: {str(e)[:100]}'}

            best_role = None
            best_score = 0
            best_reasoning = ""
            for role, ra in role_analyses.items():
                s = ra.get('score', 0)
                if s > best_score:
                    best_score = s
                    best_role = role
                    best_reasoning = ra.get('reasoning', '')
        
        # If all scores are 0 or very low, classify as 'Other'
        if best_score < 30:
            best_role = 'Other'
            best_reasoning = "The CV does not show a strong match for CTO, VP, or Architect roles. This may be a different type of position."
        
        return {
            'best_role': best_role,
            'match_score': best_score,
            'role_analyses': role_analyses,
            'reasoning': best_reasoning
        }
    
    def generate_persona_questions(self, cv_text, digital_persona=None):
        """
        Context-Aware Persona Questionnaire: Generate 5 strategic multiple-choice questions
        based on gaps in the CV and the candidate's specific industry/domain.
        
        Args:
            cv_text: The CV text to analyze
            digital_persona: Optional digital persona to extract domain/industry context
        
        Returns:
            list: List of question dictionaries, each with:
                - 'question': str - The question text
                - 'options': list - List of answer options
                - 'category': str - Category (e.g., 'tech_stack', 'leadership_style', 'industry_preference')
        """
        try:
            # Context-Aware Questions: Extract domain/industry from persona
            primary_domain = "Engineering"  # Default fallback
            industry_focus = ""
            if digital_persona:
                primary_domain = digital_persona.get('primary_domain', 'Engineering')
                industry_focus = digital_persona.get('industry_focus', '')
            
            # Build domain-specific question examples
            domain_question_context = {
                'Marketing': "Focus on Marketing-specific questions:\n"
                            "- MarTech stack preferences (e.g., 'What MarTech stack do you prefer for customer acquisition?')\n"
                            "- Marketing leadership style (e.g., 'How do you manage Marketing teams across channels?')\n"
                            "- Digital Marketing preferences (e.g., 'Which digital marketing channel excites you most?')\n"
                            "- Campaign management (e.g., 'How do you approach multi-channel campaign management?')\n"
                            "- Marketing analytics (e.g., 'What analytics approach do you prefer for measuring ROI?')\n",
                'Sales': "Focus on Sales-specific questions:\n"
                        "- Sales methodology (e.g., 'What sales methodology do you prefer for scaling revenue?')\n"
                        "- Sales leadership style (e.g., 'How do you coach and develop sales teams?')\n"
                        "- Revenue operations (e.g., 'How do you manage revenue operations and forecasting?')\n"
                        "- CRM and tools (e.g., 'What CRM/tools do you prefer for sales management?')\n"
                        "- Sales strategy (e.g., 'What's your approach to building sales pipelines?')\n",
                'Product': "Focus on Product-specific questions:\n"
                          "- Product strategy (e.g., 'What's your approach to product roadmap planning?')\n"
                          "- Product leadership style (e.g., 'How do you align Product with Engineering and Design?')\n"
                          "- Product metrics (e.g., 'What product metrics do you prioritize for success?')\n"
                          "- User research (e.g., 'How do you approach user research and validation?')\n"
                          "- Product vision (e.g., 'What's your approach to defining product vision?')\n",
                'Engineering': "Focus on Engineering-specific questions:\n"
                              "- Tech stack preferences (e.g., 'What tech stack do you prefer for Scale?')\n"
                              "- Engineering leadership style (e.g., 'How do you prefer to lead engineering teams?')\n"
                              "- Architecture approach (e.g., 'What's your approach to system architecture?')\n"
                              "- Development methodology (e.g., 'What development methodology do you prefer?')\n"
                              "- Technical challenges (e.g., 'What technical challenges excite you most?')\n",
                'Operations': "Focus on Operations-specific questions:\n"
                            "- Operations strategy (e.g., 'What's your approach to optimizing business operations?')\n"
                            "- Process improvement (e.g., 'How do you identify and improve operational processes?')\n"
                            "- Operations leadership (e.g., 'How do you manage cross-functional operations teams?')\n"
                            "- Efficiency metrics (e.g., 'What operations metrics do you prioritize?')\n"
                            "- Business operations (e.g., 'What's your approach to scaling business operations?')\n"
            }
            
            question_context = domain_question_context.get(primary_domain, domain_question_context['Engineering'])
            
            prompt = (
                f"Based on this CV, generate exactly 5 strategic multiple-choice questions "
                f"to understand the candidate's preferences and fill gaps in their profile. "
                f"CRITICAL: The candidate's PRIMARY DOMAIN is '{primary_domain}' with industry focus '{industry_focus}'. "
                f"ALL questions MUST be context-aware and specific to this domain.\n\n"
                f"{question_context}"
                "Return ONLY a JSON array with this exact structure:\n"
                "[\n"
                "  {\"question\": \"Question text\", \"options\": [\"Option 1\", \"Option 2\", \"Option 3\", \"Option 4\"], \"category\": \"domain_specific\"},\n"
                "  ...\n"
                "]\n\n"
                f"CV Text (first 2000 chars):\n{cv_text[:2000]}"
            )
            
            response = self.api_client.call_api_with_fallback(prompt)
            questions = parse_json_safely(response.text)
            
            if isinstance(questions, list) and len(questions) > 0:
                # Ensure we have exactly 5 questions
                return questions[:5]
            else:
                # Fallback questions if AI fails
                return [
                    {
                        "question": "What tech stack do you prefer for scaling applications?",
                        "options": ["Python/Node.js", "Java/Spring", "Go/Rust", "Microservices (any language)"],
                        "category": "tech_stack"
                    },
                    {
                        "question": "How do you prefer to lead engineering teams?",
                        "options": ["Hands-on coding", "Strategic planning", "Mentoring & coaching", "Hybrid approach"],
                        "category": "leadership_style"
                    },
                    {
                        "question": "Which industry excites you most?",
                        "options": ["E-commerce/Retail", "Fintech", "SaaS/B2B", "Healthcare Tech"],
                        "category": "industry_preference"
                    },
                    {
                        "question": "What work environment do you thrive in?",
                        "options": ["Startup (fast-paced)", "Scale-up (growth phase)", "Enterprise (established)", "Remote-first"],
                        "category": "work_environment"
                    },
                    {
                        "question": "What's your primary career focus right now?",
                        "options": ["Technical excellence", "Team building", "Product innovation", "Business impact"],
                        "category": "career_goals"
                    }
                ]
        except Exception as e:
            print(f"WARN: Failed to generate persona questions: {e}")
            # Return fallback questions
            return [
                {
                    "question": "What tech stack do you prefer for scaling applications?",
                    "options": ["Python/Node.js", "Java/Spring", "Go/Rust", "Microservices (any language)"],
                    "category": "tech_stack"
                },
                {
                    "question": "How do you prefer to lead engineering teams?",
                    "options": ["Hands-on coding", "Strategic planning", "Mentoring & coaching", "Hybrid approach"],
                    "category": "leadership_style"
                },
                {
                    "question": "Which industry excites you most?",
                    "options": ["E-commerce/Retail", "Fintech", "SaaS/B2B", "Healthcare Tech"],
                    "category": "industry_preference"
                },
                {
                    "question": "What work environment do you thrive in?",
                    "options": ["Startup (fast-paced)", "Scale-up (growth phase)", "Enterprise (established)", "Remote-first"],
                    "category": "work_environment"
                },
                {
                    "question": "What's your primary career focus right now?",
                    "options": ["Technical excellence", "Team building", "Product innovation", "Business impact"],
                    "category": "career_goals"
                }
            ]
    
    def refine_persona_with_answers(self, answers, digital_persona=None):
        """
        Refine Persona with Answers: Update the Digital Persona weights based on questionnaire answers.
        
        Args:
            answers: Dictionary mapping question categories to selected answers
                Example: {'tech_stack': 'Python/Node.js', 'leadership_style': 'Hybrid approach', ...}
            digital_persona: Optional existing digital persona to refine
        
        Returns:
            dict: Updated digital persona with refined weights and preferences
        """
        try:
            if digital_persona is None:
                digital_persona = {}
            
            # Build answer summary for AI
            answer_summary = "\n".join([f"{cat}: {ans}" for cat, ans in answers.items()])
            
            prompt = (
                "Based on these questionnaire answers, update the Digital Persona:\n\n"
                f"{answer_summary}\n\n"
                "Current Persona Summary:\n"
                f"{digital_persona.get('persona_summary', 'No existing persona')}\n\n"
                "Update the persona to reflect these preferences. Return ONLY a JSON object with:\n"
                "{\n"
                "  \"persona_summary\": \"Updated summary\",\n"
                "  \"tech_stack\": [\"tech1\", \"tech2\", ...],\n"
                "  \"preferences\": [\"pref1\", \"pref2\", ...],\n"
                "  \"industry_focus\": \"Updated industry focus\",\n"
                "  \"leadership_style\": \"Updated leadership style\"\n"
                "}\n"
            )
            
            response = self.api_client.call_api_with_fallback(prompt)
            updates = parse_json_safely(response.text)
            
            if isinstance(updates, dict):
                # Merge updates into existing persona
                digital_persona.update(updates)
                print(f"✅ Persona refined with questionnaire answers")
            else:
                print(f"WARN: Invalid persona updates format from AI")
            
            return digital_persona
        except Exception as e:
            print(f"WARN: Failed to refine persona with answers: {e}")
            return digital_persona if digital_persona else {}
    
    def universal_scraper(self, company_career_urls: list, digital_persona: dict = None, dna_embedding: list = None, min_match_score: float = 0.7) -> dict:
        """
        Universal Scraper: Scrape multiple company career pages and filter jobs using Persona DNA.
        
        This is a placeholder for the Universal Scraper capability. It's designed to:
        1. Take a list of company career URLs
        2. Scrape job listings from each URL (using utils.py scrapers with Anti-Blocking standards)
        3. Filter jobs using Persona DNA Signature (vector similarity) before expensive AI analysis
        4. Return filtered, scored job matches
        
        Args:
            company_career_urls: List of company career page URLs to scrape
                Example: ["https://company.com/careers", "https://another.com/jobs"]
            digital_persona: Digital Persona dict (optional, falls back to session state)
            dna_embedding: Personal DNA Signature embedding for vector filtering (optional)
            min_match_score: Minimum match score threshold (0.0-1.0, default 0.7)
        
        Returns:
            dict: {
                "total_found": int,
                "filtered_count": int,
                "matches": [
                    {
                        "title": str,
                        "company": str,
                        "job_url": str,
                        "description": str,
                        "match_score": float,
                        "vector_score": float,
                        "filter_reason": str
                    }
                ],
                "errors": [str],
                "scraping_stats": [
                    {
                        "url": str,
                        "jobs_found": int,
                        "status": str
                    }
                ]
            }
        
        TODO: Implementation steps:
        1. Use utils.py scrapers (scrape_jobs_with_timeout) for each URL
        2. Apply Anti-Blocking standards (random waits, 429 handling, User-Agent rotation)
        3. Use DNA embedding for vector similarity pre-filtering (if available)
        4. Pass filtered jobs to analyze_match() for AI scoring
        5. Return structured results with match scores
        """
        # Placeholder implementation - returns structure for future development
        print("🔧 Universal Scraper: Placeholder method called")
        print(f"   Input: {len(company_career_urls)} company URLs")
        
        # Use session state persona if not provided
        if digital_persona is None:
            try:
                import streamlit as st
                digital_persona = st.session_state.get('digital_persona', {})
            except Exception:
                digital_persona = {}
        
        # Validate inputs
        if not isinstance(company_career_urls, list) or len(company_career_urls) == 0:
            return {
                "total_found": 0,
                "filtered_count": 0,
                "matches": [],
                "errors": ["Invalid company_career_urls: must be non-empty list"],
                "scraping_stats": []
            }
        
        result = {
            "total_found": 0,
            "filtered_count": 0,
            "matches": [],
            "errors": [],
            "scraping_stats": []
        }
        
        # TODO: Implementation placeholder
        # Step 1: Scrape each URL using utils.py scrapers (with Anti-Blocking standards)
        # Step 2: Pre-filter using DNA embedding vector similarity (low-cost filtering)
        # Step 3: AI analysis for filtered jobs using analyze_match() (high-cost, precise)
        # Step 4: Return structured results
        
        print("⚠️ Universal Scraper: Not yet implemented - returning placeholder structure")
        result["errors"].append("Universal Scraper not yet implemented - this is a placeholder")
        
        return result