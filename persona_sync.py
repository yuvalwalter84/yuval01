"""
Persona Synchronization Module - Re-score jobs when personal_dna changes.
When personal_dna changes, trigger a re-score of all existing jobs in the background.
"""
import json
import os
from datetime import datetime
from utils import get_user_file_path, get_user_id, get_db_manager, load_preferences
from core_engine import CoreEngine

def get_personal_dna_signature(user_id=None):
    """Get a signature of the current personal_dna for change detection."""
    try:
        preferences = load_preferences(user_id)
        personal_dna = preferences.get('personal_dna', {})
        return json.dumps(personal_dna, sort_keys=True) if personal_dna else ""
    except Exception:
        return ""

def save_personal_dna_signature(signature, user_id=None):
    """Save the personal_dna signature for comparison."""
    try:
        from utils import get_user_file_path, get_user_id
        if user_id is None:
            user_id = get_user_id()
        sig_file = get_user_file_path('personal_dna_signature.json', user_id)
        with open(sig_file, 'w', encoding='utf-8') as f:
            json.dump({'signature': signature, 'timestamp': datetime.now().isoformat()}, f)
    except Exception:
        pass

def load_personal_dna_signature(user_id=None):
    """Load the last saved personal_dna signature."""
    try:
        from utils import get_user_file_path, get_user_id
        if user_id is None:
            user_id = get_user_id()
        sig_file = get_user_file_path('personal_dna_signature.json', user_id)
        if os.path.exists(sig_file):
            with open(sig_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('signature', '')
    except Exception:
        pass
    return ""

def trigger_persona_synchronization(user_id=None, force=False):
    """
    Persona Synchronization: When personal_dna changes, trigger re-scoring of all existing jobs.
    
    Args:
        user_id: Optional user_id
        force: If True, force re-scoring even if signature hasn't changed
    
    Returns:
        tuple: (jobs_updated, jobs_skipped)
    """
    try:
        from utils import get_user_id, get_db_manager, load_preferences, load_profile
        if user_id is None:
            user_id = get_user_id()
        
        # Get current personal_dna signature
        current_sig = get_personal_dna_signature(user_id)
        last_sig = load_personal_dna_signature(user_id)
        
        # Check if personal_dna changed
        if not force and current_sig == last_sig:
            return (0, 0)  # No change, skip re-scoring
        
        print(f"🔄 Persona Synchronization: personal_dna changed. Re-scoring existing jobs...")
        
        # Load preferences and profile
        preferences = load_preferences(user_id)
        profile = load_profile(user_id)
        cv_text = profile.get('master_cv_text', '')
        
        if not cv_text:
            print("⚠️ No CV text available for re-scoring")
            return (0, 0)
        
        # Get digital persona
        digital_persona = None
        try:
            db = get_db_manager()
            persona_data = db.get_persona(user_id)
            if persona_data:
                digital_persona = persona_data.get('digital_persona', {})
        except Exception:
            pass
        
        # Get all jobs from database
        db = get_db_manager()
        all_jobs = db.get_jobs(user_id, limit=1000)  # Get up to 1000 jobs
        
        if not all_jobs:
            print("ℹ️ No jobs to re-score")
            return (0, 0)
        
        # Initialize engine
        engine = CoreEngine()
        
        # Re-score each job
        updated_count = 0
        skipped_count = 0
        
        for job in all_jobs:
            try:
                job_url = job.get('job_url', '')
                if not job_url:
                    skipped_count += 1
                    continue
                
                # Get job description
                job_description = job.get('description', '')
                if not job_description:
                    skipped_count += 1
                    continue
                
                # Cost Control: Use only first 1000 chars for re-scoring
                job_description_trimmed = job_description[:1000]
                
                # Re-analyze match
                analysis = engine.analyze_match(
                    job_description_trimmed,
                    cv_text,
                    skill_bucket=preferences.get('user_identity', {}).get('added_skills', []),
                    digital_persona=digital_persona,
                    strict_industry_match=False,  # Use flexible matching
                    job_title=job.get('title', ''),
                    job_url=job_url
                )
                
                new_score = analysis.get('match_score', 0)
                old_score = job.get('match_score', 0)
                
                # Update job in database
                db.save_job(
                    user_id=user_id,
                    title=job.get('title', ''),
                    company=job.get('company', ''),
                    description=job_description,
                    job_url=job_url,
                    match_score=new_score,
                    status=job.get('status', 'candidate'),
                    analysis=analysis
                )
                
                updated_count += 1
                
                # Log if score changed significantly
                if abs(new_score - old_score) > 10:
                    print(f"  ✅ Re-scored: {job.get('title', 'Unknown')} - {old_score}% → {new_score}%")
                
            except Exception as e:
                print(f"  ⚠️ Error re-scoring job {job.get('title', 'Unknown')}: {e}")
                skipped_count += 1
                continue
        
        # Save new signature
        save_personal_dna_signature(current_sig, user_id)
        
        print(f"✅ Persona Synchronization complete: {updated_count} jobs updated, {skipped_count} skipped")
        return (updated_count, skipped_count)
        
    except Exception as e:
        print(f"❌ Persona Synchronization failed: {e}")
        return (0, 0)
