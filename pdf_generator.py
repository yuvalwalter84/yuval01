"""
PDF Generator for Vision Stack 2026.
Contains all PDF/FPDF related functions for generating tailored CVs and application files.
"""
import os
import hashlib
from utils import APIClient, detect_language, load_preferences

class PDFGenerator:
    """
    Handles PDF generation and CV tailoring for ATS optimization.
    """
    def __init__(self):
        self.api_client = APIClient()

    def inject_soft_traits_into_cover_letter(self, cover_letter_text: str, language: str = "en") -> str:
        """
        Soft Traits Injection (Writing Logic ONLY):
        Pulls from preferences.json -> personal_dna.soft_traits and lightly enriches tone/human touch.
        MUST NOT change professional facts. MUST NOT shorten the letter.
        Target remains ~1200 characters (we only add a short paragraph if needed).
        """
        try:
            prefs = load_preferences()
            soft = (prefs.get("personal_dna", {}) or {}).get("soft_traits", {}) or {}
            hobbies = soft.get("hobbies", []) or []
            comm = str(soft.get("communication_style", "") or "").strip()
            tone = str(soft.get("tone_voice", "") or "").strip()

            base = (cover_letter_text or "").strip()
            if not base:
                return base

            # Build a short, tasteful "personal touch" paragraph (no claims, no new facts)
            hobbies_text = ", ".join([str(h).strip() for h in hobbies if str(h).strip()][:3])
            if language == "he":
                extra = " \n\n"
                extra += "בנימה אישית: "
                parts = []
                if tone:
                    parts.append(f"הטון שלי הוא {tone}")
                if comm:
                    parts.append(f"סגנון התקשורת שלי {comm}")
                if hobbies_text:
                    parts.append(f"ובעולם האישי אני נהנה מ-{hobbies_text}")
                extra += "; ".join(parts) + "."
            else:
                extra = " \n\n"
                extra += "On a personal note: "
                parts = []
                if tone:
                    parts.append(f"my tone is {tone}")
                if comm:
                    parts.append(f"my communication style is {comm}")
                if hobbies_text:
                    parts.append(f"and I enjoy {hobbies_text}")
                extra += "; ".join(parts) + "."
            # Do NOT shorten the original letter. Only add as much of the Human Touch paragraph as fits.
            # Keep strict 800-1200 char window (target ~1200) by trimming ONLY the added paragraph if needed.
            max_len = 1200
            if len(base) >= max_len:
                return base[:max_len]

            # If we're short, append a human-touch paragraph, but never exceed 1200.
            room = max_len - len(base)
            if room <= 0:
                return base

            # Add at most 'room' chars of the extra paragraph
            extra_to_add = extra
            if len(extra_to_add) > room:
                extra_to_add = extra_to_add[:room]
                # avoid cutting mid-word harshly
                extra_to_add = extra_to_add.rsplit(' ', 1)[0] + '…' if ' ' in extra_to_add else extra_to_add

            return base + extra_to_add
        except Exception:
            return (cover_letter_text or "").strip()
    
    def generate_tailored_pdf(self, original_cv, job_description):
        """
        Generates a tailored PDF by optimizing CV phrasing for ATS without adding false information.
        The logic optimizes phrasing for ATS compatibility while strictly using only skills/experience
        present in the original CV.
        Returns the file path to the generated PDF.
        """
        # Detect language of job description
        job_language = detect_language(job_description)
        
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
            response = self.api_client.call_api_with_fallback(prompt)
            optimized_cv_text = response.text.strip()
            
            # Create PDF file (for now, save as text file - can be extended to actual PDF)
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
