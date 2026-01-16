"""
Migration script to import existing JSON/CSV data from data/ folder into SQLite database.
Run this once to migrate all existing user data to the new database architecture.
"""
import os
import json
import csv
import sqlite3
from pathlib import Path
from database_manager import DatabaseManager

def sanitize_email(email):
    """Sanitize email for filesystem safety."""
    if '@' in email:
        return email.replace('@', '_at_').replace('.', '_dot_')
    return email

def migrate_user_data(user_id, db_manager):
    """Migrate all data for a single user from JSON/CSV files to database."""
    user_data_dir = os.path.join('data', user_id)
    
    if not os.path.exists(user_data_dir):
        print(f"⚠️ Skipping {user_id}: directory does not exist")
        return
    
    print(f"\n📦 Migrating user: {user_id}")
    
    # Get or create user in database
    # Try to extract email from user_id (reverse sanitization)
    email = user_id.replace('_at_', '@').replace('_dot_', '.')
    if not '@' in email:
        email = f"{user_id}@migrated.local"  # Fallback email
    
    sanitized = sanitize_email(email)
    db_user_id = db_manager.get_or_create_user(email, sanitized)
    
    # Initialize preferences variable (may be None if file doesn't exist)
    preferences = None
    
    # 1. Migrate preferences.json
    preferences_file = os.path.join(user_data_dir, 'preferences.json')
    if os.path.exists(preferences_file):
        try:
            with open(preferences_file, 'r', encoding='utf-8') as f:
                preferences = json.load(f)
            db_manager.save_preferences(db_user_id, preferences)
            print(f"  ✅ Migrated preferences.json")
        except Exception as e:
            print(f"  ⚠️ Failed to migrate preferences.json: {e}")
            preferences = None
    else:
        print(f"  ℹ️ preferences.json not found (skipping)")
    
    # 2. Migrate profile_data.json (to personas table)
    profile_file = os.path.join(user_data_dir, 'profile_data.json')
    if os.path.exists(profile_file):
        try:
            with open(profile_file, 'r', encoding='utf-8') as f:
                profile = json.load(f)
            
            # Extract persona data
            digital_persona = None
            if 'digital_persona' in profile:
                digital_persona = profile['digital_persona']
            elif 'persona_summary' in profile:
                digital_persona = profile
            
            profile_summary = None
            if digital_persona:
                profile_summary = digital_persona.get('persona_summary', '')
            
            latent_capabilities = None
            if digital_persona and 'latent_capabilities' in digital_persona:
                latent_capabilities = digital_persona['latent_capabilities']
            
            # Get ambitions from preferences (from file or database)
            ambitions = None
            if preferences:
                ambitions = preferences.get('user_identity', {}).get('user_ambitions', '')
            else:
                # Try to get from database if file didn't exist
                try:
                    db_prefs = db_manager.get_preferences(db_user_id)
                    if db_prefs:
                        ambitions = db_prefs.get('user_identity', {}).get('user_ambitions', '')
                except Exception:
                    pass
            
            db_manager.save_persona(
                user_id=db_user_id,
                profile_summary=profile_summary,
                latent_capabilities=latent_capabilities,
                ambitions=ambitions,
                digital_persona=digital_persona
            )
            print(f"  ✅ Migrated profile_data.json to personas table")
        except Exception as e:
            print(f"  ⚠️ Failed to migrate profile_data.json: {e}")
    else:
        print(f"  ℹ️ profile_data.json not found (skipping)")
    
    # 3. Migrate horizon_roles (from session state or preferences)
    if preferences:
        horizon_roles_data = preferences.get('horizon_roles', [])
        if horizon_roles_data:
            try:
                if isinstance(horizon_roles_data, list):
                    db_manager.save_horizon_roles(db_user_id, horizon_roles_data)
                    print(f"  ✅ Migrated {len(horizon_roles_data)} horizon roles")
            except Exception as e:
                print(f"  ⚠️ Failed to migrate horizon roles: {e}")
    else:
        print(f"  ℹ️ No horizon roles found in preferences (skipping)")
    
    # 4. Migrate applications_history.csv
    applications_file = os.path.join(user_data_dir, 'applications_history.csv')
    if os.path.exists(applications_file):
        try:
            count = 0
            with open(applications_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    db_manager.log_application(
                        user_id=db_user_id,
                        job_url=row.get('job_url', ''),
                        company=row.get('company', ''),
                        title=row.get('title', ''),
                        application_text=row.get('application_text', ''),
                        status=row.get('status', 'applied')
                    )
                    count += 1
            print(f"  ✅ Migrated {count} application records")
        except Exception as e:
            print(f"  ⚠️ Failed to migrate applications_history.csv: {e}")
    else:
        print(f"  ℹ️ applications_history.csv not found (skipping)")
    
    # 5. Migrate discovered_jobs.csv (if exists)
    discovered_jobs_file = os.path.join(user_data_dir, 'discovered_jobs.csv')
    if not os.path.exists(discovered_jobs_file):
        discovered_jobs_file = 'discovered_jobs.csv'  # Try root-level file
    
    if os.path.exists(discovered_jobs_file):
        try:
            count = 0
            with open(discovered_jobs_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Only migrate jobs for this user (if user_id column exists)
                    if 'user_id' in row and row.get('user_id') != user_id:
                        continue
                    
                    try:
                        match_score = float(row.get('match_score', 0))
                    except (ValueError, TypeError):
                        match_score = 0
                    
                    status = row.get('status', 'candidate')
                    
                    # Parse analysis_json if present
                    analysis = None
                    if 'analysis' in row:
                        try:
                            analysis = json.loads(row['analysis'])
                        except:
                            pass
                    
                    db_manager.save_job(
                        user_id=db_user_id,
                        title=row.get('title', ''),
                        company=row.get('company', ''),
                        description=row.get('description', ''),
                        job_url=row.get('job_url', ''),
                        match_score=match_score,
                        status=status,
                        analysis=analysis
                    )
                    count += 1
            if count > 0:
                print(f"  ✅ Migrated {count} job records")
        except Exception as e:
            print(f"  ⚠️ Failed to migrate discovered_jobs.csv: {e}")
    else:
        print(f"  ℹ️ discovered_jobs.csv not found (skipping)")
    
    # 6. Migrate feedback_log.json (if exists)
    feedback_file = os.path.join(user_data_dir, 'feedback_log.json')
    if os.path.exists(feedback_file):
        try:
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedback_log = json.load(f)
            
            count = 0
            if isinstance(feedback_log, list):
                for entry in feedback_log:
                    db_manager.log_feedback(
                        user_id=db_user_id,
                        job_url=entry.get('job_url', ''),
                        job_title=entry.get('job_title', ''),
                        action=entry.get('action', ''),
                        reason=entry.get('reason', '')
                    )
                    count += 1
            print(f"  ✅ Migrated {count} feedback records")
        except Exception as e:
            print(f"  ⚠️ Failed to migrate feedback_log.json: {e}")
    else:
        print(f"  ℹ️ feedback_log.json not found (skipping)")

def consolidate_user_folders(data_dir):
    """
    Consolidate duplicate user folders (e.g., yuval8083gmailcom -> yuval8083_at_gmail_dot_com).
    Moves all data from the old folder to the correct sanitized folder.
    """
    user_dirs = [d for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    # Find duplicates (folders that look like unsanitized versions of sanitized folders)
    consolidated = []
    for user_dir in user_dirs:
        user_id = user_dir.name
        
        # Check if this looks like an unsanitized email (no _at_ or _dot_)
        if '@' not in user_id and '_at_' not in user_id:
            # Try to find a sanitized version
            # Pattern: if we have "yuval8083gmailcom", look for "yuval8083_at_gmail_dot_com"
            # This is a simple heuristic - we'll look for folders that contain the same base name
            base_name = user_id.replace('gmail', '').replace('com', '').replace('@', '')
            
            for other_dir in user_dirs:
                other_id = other_dir.name
                if other_id != user_id and base_name in other_id and '_at_' in other_id:
                    # Found a match - consolidate
                    print(f"  🔄 Consolidating: {user_id} -> {other_id}")
                    try:
                        # Move all files from old folder to new folder
                        for file_path in user_dir.iterdir():
                            if file_path.is_file():
                                dest_path = other_dir / file_path.name
                                if not dest_path.exists():
                                    file_path.rename(dest_path)
                                    print(f"    ✅ Moved {file_path.name}")
                                else:
                                    # File exists in both - keep the newer one
                                    if file_path.stat().st_mtime > dest_path.stat().st_mtime:
                                        file_path.rename(dest_path)
                                        print(f"    ✅ Replaced {file_path.name} (newer version)")
                        
                        # Remove old folder if empty
                        if not any(user_dir.iterdir()):
                            user_dir.rmdir()
                            print(f"    ✅ Removed empty folder {user_id}")
                            consolidated.append(user_id)
                    except Exception as e:
                        print(f"    ⚠️ Error consolidating {user_id}: {e}")
    
    return consolidated

def main():
    """Main migration function."""
    print("🚀 Starting database migration...")
    print("=" * 60)
    
    # Initialize database
    db_manager = DatabaseManager(db_path="data/persona_db.sqlite")
    print("✅ Database initialized")
    
    # Find all user directories in data/
    data_dir = Path('data')
    if not data_dir.exists():
        print("⚠️ No data/ directory found. Nothing to migrate.")
        return
    
    # Consolidate duplicate user folders first
    print("\n📦 Consolidating duplicate user folders...")
    consolidated = consolidate_user_folders(data_dir)
    if consolidated:
        print(f"  ✅ Consolidated {len(consolidated)} duplicate folders")
    else:
        print("  ℹ️ No duplicate folders found")
    
    # Refresh user directories after consolidation
    user_dirs = [d.name for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    if not user_dirs:
        print("⚠️ No user directories found in data/. Nothing to migrate.")
        return
    
    print(f"\n📁 Found {len(user_dirs)} user directories")
    
    # Migrate each user
    migrated_count = 0
    for user_id in user_dirs:
        try:
            migrate_user_data(user_id, db_manager)
            migrated_count += 1
        except Exception as e:
            print(f"  ❌ Error migrating {user_id}: {e}")
            import traceback
            print(traceback.format_exc())
    
    print("\n" + "=" * 60)
    print(f"✅ Migration complete! Migrated {migrated_count} users")
    print(f"📊 Database location: {db_manager.db_path}")
    print("\n💡 Tip: The system will now use the database as the primary storage.")
    print("   JSON/CSV files are kept as backup during the transition period.")

if __name__ == "__main__":
    main()
