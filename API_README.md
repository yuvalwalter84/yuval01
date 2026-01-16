# Vision Stack 2026 API Documentation

## Overview

FastAPI REST API that connects `core_engine.py` (AI logic) and `supabase_manager.py` (database) to endpoints. Provides 1200-character cover letter generation and Persona DNA scoring via HTTP endpoints.

## Installation

```bash
# Install dependencies
pip install fastapi uvicorn[standard] supabase

# Or use requirements.txt
pip install -r requirements.txt
```

## Configuration

Set environment variables or use `.env` file:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
USE_SUPABASE=true
API_PORT=8000
API_HOST=0.0.0.0
```

## Running the API

```bash
# Development (with auto-reload)
python main_api.py

# Or using uvicorn directly
uvicorn main_api:app --host 0.0.0.0 --port 8000 --reload

# Production
uvicorn main_api:app --host 0.0.0.0 --port 8000 --workers 4
```

## API Documentation

Once running, access interactive API docs at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Authentication & Multi-Tenancy

All endpoints require the `X-Tenant-ID` header for tenant isolation:

```bash
curl -H "X-Tenant-ID: user@example.com" http://localhost:8000/api/v1/profile
```

The tenant_id is automatically sanitized (email addresses converted to filesystem-safe format).

## Core Endpoints

### 1. Profile & Persona DNA

#### POST `/api/v1/profile/analyze`
Deep Profile Analysis - Extracts Persona DNA from CV.

**Request Body:**
```json
{
  "cv_text": "Full CV text content...",
  "skill_bucket": ["Python", "FastAPI"],
  "rejection_learnings": []
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "persona_dna": {...},
    "career_horizon": {...},
    "hard_constraints": {...}
  },
  "tenant_id": "user_at_example_dot_com"
}
```

#### GET `/api/v1/profile`
Get user profile from Supabase.

**Response:**
```json
{
  "success": true,
  "data": {
    "persona_dna": {...},
    "career_horizon": {...},
    "hard_constraints": {...}
  }
}
```

#### POST `/api/v1/profile/save`
Save profile to Supabase.

**Request Body:**
```json
{
  "persona_dna": {...},
  "career_horizon": {...},
  "hard_constraints": {...}
}
```

#### GET `/api/v1/profile/dna-embedding`
Get DNA embedding vector for vector similarity search.

**Response:**
```json
{
  "success": true,
  "data": {
    "embedding": [0.123, 0.456, ...]
  }
}
```

### 2. Job Analysis & Scoring

#### POST `/api/v1/jobs/analyze`
Analyze Job Match - Persona DNA Scoring.

**Request Body:**
```json
{
  "job_description": "Full job description...",
  "cv_text": "Full CV text...",
  "job_title": "Software Engineer",
  "job_url": "https://example.com/job/123",
  "strict_industry_match": true
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "match_score": 85,
    "explanation": "Strong match because...",
    "gaps": ["Missing skill X"],
    "discarded": false
  }
}
```

#### POST `/api/v1/jobs/save`
Save job with match score, status, and hook.

**Request Body:**
```json
{
  "job_data": {
    "title": "Software Engineer",
    "company": "Tech Corp",
    "description": "...",
    "job_url": "..."
  },
  "match_score": 85,
  "status": "pending",
  "hook": "Strategic hook for cover letter"
}
```

#### GET `/api/v1/jobs`
Get jobs with optional filters.

**Query Parameters:**
- `status` (optional): Filter by status (pending, applied, rejected)
- `min_score` (optional): Minimum match score

**Example:**
```bash
GET /api/v1/jobs?status=pending&min_score=70
```

#### GET `/api/v1/jobs/{job_url}`
Get job by URL.

#### PATCH `/api/v1/jobs/{job_id}/status`
Update job status.

**Request Body:**
```json
{
  "status": "applied"
}
```

### 3. Cover Letter Generation (1200-Character)

#### POST `/api/v1/cover-letter/generate`
Generate 1200-Character Cover Letter.

**Request Body:**
```json
{
  "cv_text": "Full CV text...",
  "job_description": "Full job description...",
  "job_title": "Software Engineer",
  "company": "Tech Corp",
  "skill_bucket": ["Python", "FastAPI"],
  "master_profile": {...},
  "digital_persona": {...}
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "cover_letter": "Dear Hiring Manager,\n\n...",
    "length": 1150,
    "job_title": "Software Engineer",
    "company": "Tech Corp"
  }
}
```

**Features:**
- ✅ Generates 800-1200 characters (enforced)
- ✅ Detects language (Hebrew/English) automatically
- ✅ Uses only actual CV experience (never invents skills)
- ✅ Includes soft traits from digital_persona
- ✅ Truncates at sentence boundaries if needed

### 4. Preferences

#### GET `/api/v1/preferences`
Get user preferences.

#### POST `/api/v1/preferences`
Save user preferences.

**Request Body:**
```json
{
  "preferences": {
    "personal_dna": {...},
    "career_horizon": {...}
  }
}
```

## Error Handling

All errors return JSON with `success: false`:

```json
{
  "success": false,
  "error": "Error message here"
}
```

HTTP Status Codes:
- `200`: Success
- `404`: Resource not found
- `500`: Internal server error
- `503`: Service unavailable (e.g., Supabase disconnected)

## Example Usage (cURL)

```bash
# Analyze profile
curl -X POST http://localhost:8000/api/v1/profile/analyze \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: user@example.com" \
  -d '{
    "cv_text": "Full CV text here..."
  }'

# Analyze job match
curl -X POST http://localhost:8000/api/v1/jobs/analyze \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: user@example.com" \
  -d '{
    "job_description": "Job description here...",
    "cv_text": "CV text here..."
  }'

# Generate cover letter
curl -X POST http://localhost:8000/api/v1/cover-letter/generate \
  -H "Content-Type: application/json" \
  -d '{
    "cv_text": "CV text...",
    "job_description": "Job description...",
    "job_title": "Software Engineer",
    "company": "Tech Corp"
  }'
```

## Example Usage (Python)

```python
import requests

BASE_URL = "http://localhost:8000"
TENANT_ID = "user@example.com"

headers = {
    "Content-Type": "application/json",
    "X-Tenant-ID": TENANT_ID
}

# Analyze profile
response = requests.post(
    f"{BASE_URL}/api/v1/profile/analyze",
    headers=headers,
    json={"cv_text": "CV text here..."}
)
profile_data = response.json()

# Generate cover letter
response = requests.post(
    f"{BASE_URL}/api/v1/cover-letter/generate",
    headers={"Content-Type": "application/json"},
    json={
        "cv_text": "CV text...",
        "job_description": "Job description...",
        "job_title": "Software Engineer",
        "company": "Tech Corp"
    }
)
cover_letter = response.json()["data"]["cover_letter"]
```

## Integration with React Frontend

The API is ready for React frontend integration:

1. **CORS**: Configured to allow all origins (update for production)
2. **JSON**: All endpoints return JSON
3. **Error Handling**: Consistent error format
4. **Authentication**: Tenant isolation via `X-Tenant-ID` header

### React Example

```javascript
const API_BASE = 'http://localhost:8000';

// Analyze profile
const analyzeProfile = async (cvText, tenantId) => {
  const response = await fetch(`${API_BASE}/api/v1/profile/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Tenant-ID': tenantId
    },
    body: JSON.stringify({ cv_text: cvText })
  });
  return await response.json();
};

// Generate cover letter
const generateCoverLetter = async (cvText, jobDescription, jobTitle, company) => {
  const response = await fetch(`${API_BASE}/api/v1/cover-letter/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      cv_text: cvText,
      job_description: jobDescription,
      job_title: jobTitle,
      company: company
    })
  });
  return await response.json();
};
```

## Core Logic Preservation

✅ **1200-Character Cover Letter**: Logic preserved from `pdf_tailor.py` (reframing_analysis method)
✅ **Persona DNA Scoring**: Uses `core_engine.py` analyze_match method
✅ **Hard Constraints**: Pre-filtering via core_engine logic
✅ **Soft Traits**: Injected from digital_persona in cover letter generation
✅ **Vector Similarity**: DNA embedding retrieval supported

## Testing

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test with interactive docs
# Open http://localhost:8000/docs in browser
```

## Production Deployment

1. Set `USE_SUPABASE=true` in environment
2. Configure proper CORS origins (replace `["*"]` in `main_api.py`)
3. Use production WSGI server (e.g., Gunicorn with Uvicorn workers)
4. Set up reverse proxy (nginx) for SSL/TLS
5. Enable rate limiting and authentication middleware

## Next Steps

- [ ] Add JWT authentication for enhanced security
- [ ] Implement rate limiting
- [ ] Add request/response logging
- [ ] Set up API versioning strategy
- [ ] Add OpenAPI schema export
- [ ] Implement WebSocket support for real-time updates
