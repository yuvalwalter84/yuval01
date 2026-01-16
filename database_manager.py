"""
Database Manager for Vision Stack 2026 - SQLite backend for scalable SaaS architecture.
Handles all database operations with strict user isolation.
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any
import threading

class DatabaseManager:
    """
    Manages SQLite database operations with strict user isolation.
    All queries enforce WHERE user_id = ? to ensure data privacy.
    """
    
    def __init__(self, db_path: str = "data/persona_db.sqlite"):
        """
        Initialize DatabaseManager with connection pool.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.local = threading.local()
        self._ensure_db_dir()
        self._initialize_db()
    
    def _ensure_db_dir(self):
        """Ensure the database directory exists."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    def _get_connection(self):
        """Get thread-local database connection."""
        if not hasattr(self.local, 'connection'):
            self.local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self.local.connection.row_factory = sqlite3.Row  # Return rows as dict-like objects
            self.local.connection.execute("PRAGMA foreign_keys = ON")  # Enable foreign key constraints
        return self.local.connection
    
    def _initialize_db(self):
        """Initialize database schema with all required tables."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Table: users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                sanitized_email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table: personas (user profile data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personas (
                user_id TEXT PRIMARY KEY,
                profile_summary TEXT,
                latent_capabilities_json TEXT,
                ambitions TEXT,
                digital_persona_json TEXT,
                dna_embedding_json TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(sanitized_email)
            )
        """)
        
        # Add dna_embedding_json column if it doesn't exist (migration for existing databases)
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM pragma_table_info('personas') WHERE name='dna_embedding_json'
        """)
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute("ALTER TABLE personas ADD COLUMN dna_embedding_json TEXT")
        
        # Table: horizon_roles (strategic career roles with gap analysis)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS horizon_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role_title TEXT NOT NULL,
                gap_analysis TEXT,
                rationale TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(sanitized_email),
                UNIQUE(user_id, role_title)
            )
        """)
        
        # Table: jobs (job postings with match scores)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT,
                company TEXT,
                description TEXT,
                job_url TEXT UNIQUE,
                match_score REAL DEFAULT 0,
                status TEXT DEFAULT 'candidate',
                analysis_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(sanitized_email)
            )
        """)
        
        # Table: preferences (user settings and configuration)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                user_id TEXT PRIMARY KEY,
                settings_json TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(sanitized_email)
            )
        """)
        
        # Table: applications_history (track application submissions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                job_url TEXT NOT NULL,
                company TEXT,
                title TEXT,
                application_text TEXT,
                status TEXT DEFAULT 'draft',
                submitted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(sanitized_email),
                UNIQUE(user_id, job_url)
            )
        """)
        
        # Table: feedback_log (user feedback on jobs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                job_url TEXT,
                job_title TEXT,
                action TEXT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(sanitized_email)
            )
        """)
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_horizon_roles_user_id ON horizon_roles(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications_history(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback_log(user_id)")
        
        conn.commit()
        print(f"✅ Database initialized at {self.db_path}")
    
    # ========================================================================
    # USER MANAGEMENT
    # ========================================================================
    
    def get_or_create_user(self, email: str, sanitized_email: str) -> str:
        """
        Get or create a user by email. Returns sanitized_email.
        
        Args:
            email: User's email address
            sanitized_email: Filesystem-safe sanitized email
        
        Returns:
            sanitized_email (user_id)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Try to get existing user
        cursor.execute("SELECT sanitized_email FROM users WHERE email = ? OR sanitized_email = ?", 
                      (email, sanitized_email))
        row = cursor.fetchone()
        
        if row:
            return row['sanitized_email']
        
        # Create new user
        cursor.execute(
            "INSERT INTO users (email, sanitized_email) VALUES (?, ?)",
            (email, sanitized_email)
        )
        conn.commit()
        return sanitized_email
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by sanitized_email (user_id)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE sanitized_email = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    # ========================================================================
    # PERSONA MANAGEMENT
    # ========================================================================
    
    def save_persona(self, user_id: str, profile_summary: str = None, 
                     latent_capabilities: List[str] = None, ambitions: str = None,
                     digital_persona: Dict = None, dna_embedding: List[float] = None):
        """
        Save or update user persona data.
        
        Args:
            user_id: User's sanitized_email
            profile_summary: Persona summary text
            latent_capabilities: List of latent capabilities
            ambitions: User's written ambitions
            digital_persona: Full digital persona dict
            dna_embedding: Vector embedding for Personal DNA Signature (list of floats)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        latent_capabilities_json = json.dumps(latent_capabilities) if latent_capabilities else None
        digital_persona_json = json.dumps(digital_persona) if digital_persona else None
        dna_embedding_json = json.dumps(dna_embedding) if dna_embedding else None
        
        cursor.execute("""
            INSERT INTO personas (user_id, profile_summary, latent_capabilities_json, 
                                 ambitions, digital_persona_json, dna_embedding_json, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_summary = COALESCE(excluded.profile_summary, profile_summary),
                latent_capabilities_json = COALESCE(excluded.latent_capabilities_json, latent_capabilities_json),
                ambitions = COALESCE(excluded.ambitions, ambitions),
                digital_persona_json = COALESCE(excluded.digital_persona_json, digital_persona_json),
                dna_embedding_json = COALESCE(excluded.dna_embedding_json, dna_embedding_json),
                last_updated = CURRENT_TIMESTAMP
        """, (user_id, profile_summary, latent_capabilities_json, ambitions, digital_persona_json, dna_embedding_json))
        
        conn.commit()
    
    def get_persona(self, user_id: str) -> Optional[Dict]:
        """Get user persona data."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM personas WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        result = dict(row)
        # Parse JSON fields
        if result.get('latent_capabilities_json'):
            result['latent_capabilities'] = json.loads(result['latent_capabilities_json'])
        if result.get('digital_persona_json'):
            result['digital_persona'] = json.loads(result['digital_persona_json'])
        if result.get('dna_embedding_json'):
            result['dna_embedding'] = json.loads(result['dna_embedding_json'])
        return result
    
    def delete_persona(self, user_id: str):
        """
        Delete persona data for a user (used for identity reset).
        
        Args:
            user_id: User's sanitized_email
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM personas WHERE user_id = ?", (user_id,))
        conn.commit()
    
    def delete_horizon_roles(self, user_id: str):
        """
        Delete all horizon roles for a user (used for identity reset).
        
        Args:
            user_id: User's sanitized_email
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM horizon_roles WHERE user_id = ?", (user_id,))
        conn.commit()
    
    # ========================================================================
    # HORIZON ROLES MANAGEMENT
    # ========================================================================
    
    def save_horizon_roles(self, user_id: str, horizon_roles: List[Dict]):
        """
        Save or update horizon roles for a user.
        
        Args:
            user_id: User's sanitized_email
            horizon_roles: List of dicts with 'role', 'gap_analysis', 'rationale'
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Delete existing roles for this user
        cursor.execute("DELETE FROM horizon_roles WHERE user_id = ?", (user_id,))
        
        # Insert new roles
        for role_data in horizon_roles:
            cursor.execute("""
                INSERT INTO horizon_roles (user_id, role_title, gap_analysis, rationale)
                VALUES (?, ?, ?, ?)
            """, (
                user_id,
                role_data.get('role', ''),
                role_data.get('gap_analysis', ''),
                role_data.get('rationale', '')
            ))
        
        conn.commit()
    
    def get_horizon_roles(self, user_id: str) -> List[Dict]:
        """Get all horizon roles for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role_title as role, gap_analysis, rationale, created_at
            FROM horizon_roles 
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    # ========================================================================
    # JOBS MANAGEMENT
    # ========================================================================
    
    def save_job(self, user_id: str, title: str = None, company: str = None,
                 description: str = None, job_url: str = None, match_score: float = 0,
                 status: str = 'candidate', analysis: Dict = None):
        """
        Save or update a job for a user.
        
        Args:
            user_id: User's sanitized_email
            title: Job title
            company: Company name
            description: Job description
            job_url: Unique job URL
            match_score: Match score (0-100)
            status: Job status ('candidate', 'approved', 'rejected', 'applied')
            analysis: Full analysis dict
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        analysis_json = json.dumps(analysis) if analysis else None
        
        cursor.execute("""
            INSERT INTO jobs (user_id, title, company, description, job_url, 
                            match_score, status, analysis_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_url) DO UPDATE SET
                title = COALESCE(excluded.title, title),
                company = COALESCE(excluded.company, company),
                description = COALESCE(excluded.description, description),
                match_score = COALESCE(excluded.match_score, match_score),
                status = COALESCE(excluded.status, status),
                analysis_json = COALESCE(excluded.analysis_json, analysis_json),
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, title, company, description, job_url, match_score, status, analysis_json))
        
        conn.commit()
    
    def get_jobs(self, user_id: str, status: str = None, min_score: float = None,
                 limit: int = None) -> List[Dict]:
        """
        Get jobs for a user with optional filters.
        
        Args:
            user_id: User's sanitized_email
            status: Filter by status (optional)
            min_score: Minimum match score (optional)
            limit: Maximum number of results (optional)
        
        Returns:
            List of job dicts
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM jobs WHERE user_id = ?"
        params = [user_id]
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if min_score is not None:
            query += " AND match_score >= ?"
            params.append(min_score)
        
        query += " ORDER BY match_score DESC, updated_at DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        result = []
        for row in rows:
            job = dict(row)
            # Parse JSON field
            if job.get('analysis_json'):
                job['analysis'] = json.loads(job['analysis_json'])
            result.append(job)
        
        return result
    
    def update_job_status(self, user_id: str, job_url: str, status: str):
        """Update job status."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE jobs 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND job_url = ?
        """, (status, user_id, job_url))
        conn.commit()
    
    # ========================================================================
    # PREFERENCES MANAGEMENT
    # ========================================================================
    
    def save_preferences(self, user_id: str, settings: Dict):
        """
        Save or update user preferences.
        
        Args:
            user_id: User's sanitized_email
            settings: Preferences dict
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        settings_json = json.dumps(settings)
        
        cursor.execute("""
            INSERT INTO preferences (user_id, settings_json, last_updated)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                settings_json = excluded.settings_json,
                last_updated = CURRENT_TIMESTAMP
        """, (user_id, settings_json))
        
        conn.commit()
    
    def get_preferences(self, user_id: str) -> Optional[Dict]:
        """Get user preferences."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT settings_json FROM preferences WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row and row['settings_json']:
            return json.loads(row['settings_json'])
        return None
    
    # ========================================================================
    # APPLICATIONS HISTORY
    # ========================================================================
    
    def log_application(self, user_id: str, job_url: str, company: str = None,
                       title: str = None, application_text: str = None, status: str = 'draft'):
        """Log an application submission."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        submitted_at = datetime.now().isoformat() if status == 'applied' else None
        
        cursor.execute("""
            INSERT INTO applications_history 
            (user_id, job_url, company, title, application_text, status, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, job_url) DO UPDATE SET
                company = COALESCE(excluded.company, company),
                title = COALESCE(excluded.title, title),
                application_text = COALESCE(excluded.application_text, application_text),
                status = excluded.status,
                submitted_at = COALESCE(excluded.submitted_at, submitted_at)
        """, (user_id, job_url, company, title, application_text, status, submitted_at))
        
        conn.commit()
    
    def check_if_applied(self, user_id: str, job_url: str) -> bool:
        """Check if user has already applied to a job."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM applications_history 
            WHERE user_id = ? AND job_url = ? AND status = 'applied'
        """, (user_id, job_url))
        row = cursor.fetchone()
        return row['count'] > 0
    
    # ========================================================================
    # FEEDBACK LOG
    # ========================================================================
    
    def log_feedback(self, user_id: str, job_url: str = None, job_title: str = None,
                    action: str = None, reason: str = None):
        """Log user feedback on a job."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO feedback_log (user_id, job_url, job_title, action, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, job_url, job_title, action, reason))
        
        conn.commit()
    
    def get_feedback_log(self, user_id: str) -> List[Dict]:
        """Get feedback log for a user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM feedback_log 
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 100
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def close(self):
        """Close database connection."""
        if hasattr(self.local, 'connection'):
            self.local.connection.close()
            delattr(self.local, 'connection')
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close()
