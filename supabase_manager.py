"""
Supabase Database Manager for Vision Stack 2026 - Cloud-Native Multi-tenant Architecture.
Handles all Supabase database operations with strict tenant isolation.
"""
import os
import json
from typing import Optional, Dict, List, Any
from datetime import datetime
import streamlit as st
from supabase import create_client, Client

class SupabaseDatabaseManager:
    """
    Manages Supabase database operations with strict tenant isolation.
    All queries enforce tenant_id filtering to ensure data privacy.
    """
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """
        Initialize SupabaseDatabaseManager with credentials.
        
        Args:
            supabase_url: Supabase project URL (defaults to st.secrets or .env)
            supabase_key: Supabase anon key (defaults to st.secrets or .env)
        """
        # Get credentials from st.secrets (Streamlit Cloud) or .env (local)
        try:
            if supabase_url is None:
                supabase_url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
            if supabase_key is None:
                supabase_key = st.secrets.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY")
        except Exception:
            # Fallback to environment variables if st.secrets not available
            supabase_url = supabase_url or os.getenv("SUPABASE_URL")
            supabase_key = supabase_key or os.getenv("SUPABASE_ANON_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase credentials not found. Set SUPABASE_URL and SUPABASE_ANON_KEY in st.secrets or .env")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.url = supabase_url
    
    def _get_tenant_id(self, user_id: Optional[str] = None) -> str:
        """
        Get tenant_id from user_id (sanitized for database).
        
        Args:
            user_id: User identifier (email or username)
        
        Returns:
            str: Sanitized tenant_id
        """
        if user_id is None:
            try:
                import streamlit as st
                user_id = st.session_state.get('user_id', 'default_user')
            except Exception:
                user_id = os.getenv('USER_ID', 'default_user')
        
        # Sanitize user_id for database (same logic as utils.get_user_id)
        user_id = str(user_id)
        if '@' in user_id:
            user_id = user_id.replace('@', '_at_').replace('.', '_dot_')
        import re
        user_id = re.sub(r'[^a-zA-Z0-9_-]', '', user_id)[:100]
        return user_id or 'default_user'
    
    # ============================================================================
    # PROFILES TABLE OPERATIONS
    # ============================================================================
    
    def get_profile(self, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get user profile (persona_dna, career_horizon, hard_constraints).
        
        Args:
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            dict: Profile data or None if not found
        """
        tenant_id = self._get_tenant_id(tenant_id)
        try:
            response = self.supabase.table("profiles").select("*").eq("tenant_id", tenant_id).execute()
            if response.data and len(response.data) > 0:
                profile = response.data[0]
                # Parse JSON fields
                if isinstance(profile.get('persona_dna'), str):
                    profile['persona_dna'] = json.loads(profile['persona_dna'])
                if isinstance(profile.get('career_horizon'), str):
                    profile['career_horizon'] = json.loads(profile['career_horizon'])
                if isinstance(profile.get('hard_constraints'), str):
                    profile['hard_constraints'] = json.loads(profile['hard_constraints'])
                return profile
            return None
        except Exception as e:
            print(f"⚠️ Error getting profile from Supabase: {e}")
            return None
    
    def save_profile(self, persona_dna: Dict[str, Any], career_horizon: Dict[str, Any], 
                     hard_constraints: Dict[str, Any], tenant_id: Optional[str] = None) -> bool:
        """
        Save or update user profile.
        
        Args:
            persona_dna: Personal DNA data
            career_horizon: Career horizon data
            hard_constraints: Hard constraints data
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            bool: True if successful, False otherwise
        """
        tenant_id = self._get_tenant_id(tenant_id)
        try:
            # Check if profile exists
            existing = self.get_profile(tenant_id)
            
            profile_data = {
                "tenant_id": tenant_id,
                "persona_dna": json.dumps(persona_dna) if not isinstance(persona_dna, str) else persona_dna,
                "career_horizon": json.dumps(career_horizon) if not isinstance(career_horizon, str) else career_horizon,
                "hard_constraints": json.dumps(hard_constraints) if not isinstance(hard_constraints, str) else hard_constraints,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if existing:
                # Update existing profile
                self.supabase.table("profiles").update(profile_data).eq("tenant_id", tenant_id).execute()
            else:
                # Insert new profile
                profile_data["created_at"] = datetime.utcnow().isoformat()
                self.supabase.table("profiles").insert(profile_data).execute()
            
            return True
        except Exception as e:
            print(f"⚠️ Error saving profile to Supabase: {e}")
            return False
    
    def get_dna_embedding(self, tenant_id: Optional[str] = None) -> Optional[List[float]]:
        """
        Get DNA embedding vector for vector similarity search.
        
        Args:
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            list: DNA embedding vector or None if not found
        """
        profile = self.get_profile(tenant_id)
        if profile and profile.get('persona_dna'):
            persona_dna = profile['persona_dna']
            if isinstance(persona_dna, dict):
                return persona_dna.get('dna_embedding')
        return None
    
    # ============================================================================
    # JOBS TABLE OPERATIONS
    # ============================================================================
    
    def save_job(self, job_data: Dict[str, Any], match_score: float, status: str, 
                 hook: Optional[str] = None, tenant_id: Optional[str] = None) -> Optional[int]:
        """
        Save or update job with match score, status, and hook.
        
        Args:
            job_data: Job details (title, company, description, url, etc.)
            match_score: Match score (0-100)
            status: Job status (e.g., 'pending', 'applied', 'rejected')
            hook: Strategic hook for cover letter
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            int: Job ID if successful, None otherwise
        """
        tenant_id = self._get_tenant_id(tenant_id)
        try:
            job_url = job_data.get('job_url') or job_data.get('url') or ''
            
            # Check if job already exists for this tenant
            existing = self.get_job_by_url(job_url, tenant_id)
            
            job_record = {
                "tenant_id": tenant_id,
                "title": job_data.get('title') or job_data.get('role', ''),
                "company": job_data.get('company', ''),
                "description": job_data.get('description') or job_data.get('job_description', ''),
                "job_url": job_url,
                "match_score": match_score,
                "status": status,
                "hook": hook or '',
                "job_data_json": json.dumps(job_data),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if existing:
                # Update existing job
                self.supabase.table("jobs").update(job_record).eq("id", existing['id']).execute()
                return existing['id']
            else:
                # Insert new job
                job_record["created_at"] = datetime.utcnow().isoformat()
                response = self.supabase.table("jobs").insert(job_record).execute()
                if response.data and len(response.data) > 0:
                    return response.data[0].get('id')
            
            return None
        except Exception as e:
            print(f"⚠️ Error saving job to Supabase: {e}")
            return None
    
    def get_job_by_url(self, job_url: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get job by URL for current tenant.
        
        Args:
            job_url: Job URL
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            dict: Job data or None if not found
        """
        tenant_id = self._get_tenant_id(tenant_id)
        try:
            response = self.supabase.table("jobs").select("*").eq("tenant_id", tenant_id).eq("job_url", job_url).execute()
            if response.data and len(response.data) > 0:
                job = response.data[0]
                # Parse JSON fields
                if isinstance(job.get('job_data_json'), str):
                    job['job_data'] = json.loads(job['job_data_json'])
                return job
            return None
        except Exception as e:
            print(f"⚠️ Error getting job from Supabase: {e}")
            return None
    
    def get_jobs(self, status: Optional[str] = None, min_score: Optional[float] = None,
                 tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get jobs for current tenant with optional filters.
        
        Args:
            status: Filter by status (optional)
            min_score: Filter by minimum match score (optional)
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            list: List of job records
        """
        tenant_id = self._get_tenant_id(tenant_id)
        try:
            query = self.supabase.table("jobs").select("*").eq("tenant_id", tenant_id)
            
            if status:
                query = query.eq("status", status)
            if min_score is not None:
                query = query.gte("match_score", min_score)
            
            response = query.order("match_score", desc=True).execute()
            
            jobs = []
            for job in response.data or []:
                # Parse JSON fields
                if isinstance(job.get('job_data_json'), str):
                    job['job_data'] = json.loads(job['job_data_json'])
                jobs.append(job)
            
            return jobs
        except Exception as e:
            print(f"⚠️ Error getting jobs from Supabase: {e}")
            return []
    
    def update_job_status(self, job_id: int, status: str, tenant_id: Optional[str] = None) -> bool:
        """
        Update job status.
        
        Args:
            job_id: Job ID
            status: New status
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            bool: True if successful, False otherwise
        """
        tenant_id = self._get_tenant_id(tenant_id)
        try:
            self.supabase.table("jobs").update({
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", job_id).eq("tenant_id", tenant_id).execute()
            return True
        except Exception as e:
            print(f"⚠️ Error updating job status in Supabase: {e}")
            return False
    
    # ============================================================================
    # PREFERENCES MIGRATION SUPPORT
    # ============================================================================
    
    def save_preferences(self, preferences: Dict[str, Any], tenant_id: Optional[str] = None) -> bool:
        """
        Save user preferences to profiles table (merged with persona_dna).
        
        Args:
            preferences: Preferences dictionary
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            bool: True if successful, False otherwise
        """
        tenant_id = self._get_tenant_id(tenant_id)
        try:
            # Get existing profile
            profile = self.get_profile(tenant_id) or {}
            
            # Merge preferences into persona_dna
            persona_dna = profile.get('persona_dna', {}) or {}
            if isinstance(persona_dna, str):
                persona_dna = json.loads(persona_dna)
            
            # Update persona_dna with preferences
            persona_dna.update(preferences.get('personal_dna', {}))
            
            career_horizon = preferences.get('career_horizon', {}) or {}
            hard_constraints = preferences.get('personal_dna', {}).get('hard_constraints', {}) or {}
            
            return self.save_profile(persona_dna, career_horizon, hard_constraints, tenant_id)
        except Exception as e:
            print(f"⚠️ Error saving preferences to Supabase: {e}")
            return False
    
    def get_preferences(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get user preferences from profiles table.
        
        Args:
            tenant_id: Optional tenant_id. If not provided, uses current user.
        
        Returns:
            dict: Preferences dictionary
        """
        profile = self.get_profile(tenant_id)
        if not profile:
            return {}
        
        persona_dna = profile.get('persona_dna', {}) or {}
        if isinstance(persona_dna, str):
            persona_dna = json.loads(persona_dna)
        
        career_horizon = profile.get('career_horizon', {}) or {}
        if isinstance(career_horizon, str):
            career_horizon = json.loads(career_horizon)
        
        hard_constraints = profile.get('hard_constraints', {}) or {}
        if isinstance(hard_constraints, str):
            hard_constraints = json.loads(hard_constraints)
        
        return {
            "personal_dna": persona_dna,
            "career_horizon": career_horizon,
            "hard_constraints": hard_constraints
        }
