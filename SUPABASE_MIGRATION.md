# Supabase Migration Guide - Vision Stack 2026

## Overview
This document describes the migration from local SQLite/JSON storage to Supabase cloud-native multi-tenant architecture.

## Prerequisites

1. **Supabase Account**: Create a project at https://supabase.com
2. **Database Schema**: Execute the following SQL in Supabase SQL Editor:

```sql
-- Profiles table (stores persona_dna, career_horizon, hard_constraints)
CREATE TABLE IF NOT EXISTS profiles (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    persona_dna JSONB,
    career_horizon JSONB,
    hard_constraints JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id)
);

-- Jobs table (stores job details, match_score, status, hook)
CREATE TABLE IF NOT EXISTS jobs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT,
    company TEXT,
    description TEXT,
    job_url TEXT,
    match_score FLOAT,
    status TEXT DEFAULT 'pending',
    hook TEXT,
    job_data_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_profiles_tenant_id ON profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant_id ON jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score DESC);
```

3. **Row Level Security (RLS)**: Enable RLS and create policies:

```sql
-- Enable RLS
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

-- Policies: Users can only access their own data (tenant_id = current_user)
CREATE POLICY "Users can view own profile" ON profiles
    FOR SELECT USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY "Users can update own profile" ON profiles
    FOR UPDATE USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY "Users can insert own profile" ON profiles
    FOR INSERT WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Similar policies for jobs table
CREATE POLICY "Users can view own jobs" ON jobs
    FOR SELECT USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY "Users can update own jobs" ON jobs
    FOR UPDATE USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY "Users can insert own jobs" ON jobs
    FOR INSERT WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
```

## Configuration

### Local Development (.env)

Create a `.env` file in the project root:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
USE_SUPABASE=true
```

### Streamlit Cloud (st.secrets)

In your Streamlit Cloud app settings, add:

```toml
[secrets]
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your_anon_key_here"
USE_SUPABASE = "true"
```

## Migration Process

### Automatic Migration

The system automatically checks for migration on startup:

1. **Verification Mode**: On first load, checks if data exists in Supabase
2. **Migration Mode**: When `migrate_to_supabase()` is called, migrates local data

### Manual Migration

To manually trigger migration:

```python
from utils import migrate_to_supabase

# Verify only (check if data exists)
status = migrate_to_supabase(verify_only=True)

# Full migration (migrate local data to Supabase)
status = migrate_to_supabase(verify_only=False)
```

### Migration Status

The migration function returns:

```python
{
    "success": True/False,
    "preferences_migrated": True/False,
    "jobs_migrated": True/False,
    "errors": [],
    "warnings": []
}
```

## Zero-Loss Integrity

### Preserved Logic

✅ **1200-Character Cover Letter**: Logic preserved in `pdf_tailor.py` (lines 736-754)
✅ **Soft Traits Injection**: Preserved in `core_engine.py` via `_get_personal_dna_config()`
✅ **Hard Constraints Pre-filtering**: Preserved in `core_engine.py` via `_hard_constraints_fail()`

### Data Preservation

- Local data is **NOT deleted** until migration is verified
- Migration is **idempotent** (safe to run multiple times)
- Fallback to local storage if Supabase fails

## Architecture

### Multi-Tenancy

Every database query is scoped with `tenant_id`:

```python
# Automatic tenant isolation
supabase.get_profile(tenant_id=user_id)  # Only returns data for this tenant
supabase.save_job(job_data, tenant_id=user_id)  # Only saves for this tenant
```

### Stateless Engine

`core_engine.py` now pulls User DNA from Supabase at runtime:

```python
def _get_personal_dna_config(self, prefs: dict | None = None) -> dict:
    # Tries Supabase first, falls back to local
    if use_supabase():
        supabase = get_supabase_manager()
        cloud_prefs = supabase.get_preferences()
        # ... returns DNA config
```

### Vector Readiness

The system is prepared for vector similarity search:

- DNA embeddings stored in `persona_dna.dna_embedding`
- `get_dna_embedding()` method available in `SupabaseDatabaseManager`
- Vector similarity logic already in `core_engine.py` (line 1762)

## Mobile Responsiveness

The UI is now mobile-responsive with:

- Responsive job cards (stacks vertically on mobile)
- Touch-friendly buttons (full-width on mobile)
- Optimized font sizes for small screens
- DNA helix visualization adapts to screen size

CSS breakpoints:
- `@media (max-width: 768px)`: Tablet adjustments
- `@media (max-width: 480px)`: Mobile adjustments

## Testing

1. **Local Testing**:
   ```bash
   # Set USE_SUPABASE=false in .env for local SQLite
   streamlit run app.py
   ```

2. **Cloud Testing**:
   ```bash
   # Set USE_SUPABASE=true in st.secrets
   # Deploy to Streamlit Cloud
   ```

3. **Migration Testing**:
   ```python
   # In app.py or Python console
   from utils import migrate_to_supabase
   status = migrate_to_supabase(verify_only=False)
   print(status)
   ```

## Troubleshooting

### "Supabase manager not available"
- Check credentials in `.env` or `st.secrets`
- Verify `USE_SUPABASE=true` is set

### "Migration verification failed"
- Check Supabase connection
- Verify RLS policies are set correctly
- Check tenant_id format (sanitized email)

### "Preferences not found in Supabase"
- This is OK if starting fresh
- Run migration with `verify_only=False` to migrate local data

## Next Steps

1. ✅ SupabaseDatabaseManager created
2. ✅ Migration function implemented
3. ✅ Core engine refactored for stateless operation
4. ✅ Mobile-responsive UI added
5. ⏳ Test migration with real data
6. ⏳ Monitor Supabase usage and performance
7. ⏳ Implement vector similarity search optimization

## Support

For issues or questions:
- Check Supabase logs in dashboard
- Review migration status in console output
- Verify RLS policies are correctly configured
