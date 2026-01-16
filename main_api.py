"""
FastAPI REST API for Vision Stack 2026 - Infrastructure Layer
Connects core_engine.py (AI logic) and supabase_manager.py (database) to endpoints.
Provides 1200-character cover letter generation and Persona DNA scoring via API.
"""
from fastapi import FastAPI, HTTPException, Depends, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os
import traceback

# Import core modules
from core_engine import CoreEngine
from supabase_manager import SupabaseDatabaseManager
from pdf_tailor import PDFTailor
from utils import get_supabase_manager, use_supabase, get_user_id

# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="Vision Stack 2026 API",
    description="Autonomous CTO Agent API - Persona DNA Scoring & Cover Letter Generation",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific React app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

# Initialize singletons
_engine = None
_supabase = None
_pdf_tailor = None

def get_engine() -> CoreEngine:
    """Get or create CoreEngine singleton."""
    global _engine
    if _engine is None:
        _engine = CoreEngine()
    return _engine

def get_supabase_db() -> Optional[SupabaseDatabaseManager]:
    """Get or create SupabaseDatabaseManager singleton."""
    global _supabase
    if _supabase is None:
        try:
            _supabase = get_supabase_manager()
        except Exception as e:
            print(f"⚠️ Supabase initialization failed: {e}")
            return None
    return _supabase

def get_pdf_tailor() -> PDFTailor:
    """Get or create PDFTailor singleton."""
    global _pdf_tailor
    if _pdf_tailor is None:
        _pdf_tailor = PDFTailor()
    return _pdf_tailor

def get_tenant_id(x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")) -> str:
    """
    Extract tenant_id from header or use default.
    Multi-tenant isolation: Every request must include X-Tenant-ID header.
    """
    if x_tenant_id:
        # Sanitize tenant_id (same logic as utils.get_user_id)
        import re
        tenant_id = str(x_tenant_id)
        if '@' in tenant_id:
            tenant_id = tenant_id.replace('@', '_at_').replace('.', '_dot_')
        tenant_id = re.sub(r'[^a-zA-Z0-9_-]', '', tenant_id)[:100]
        return tenant_id or 'default_user'
    return 'default_user'

# ============================================================================
# PYDANTIC MODELS (Request/Response Schemas)
# ============================================================================

class CVUploadRequest(BaseModel):
    cv_text: str = Field(..., description="CV text content")
    skill_bucket: Optional[List[str]] = Field(None, description="Optional skill bucket")
    rejection_learnings: Optional[List[str]] = Field(None, description="Optional rejection learnings")

class JobAnalysisRequest(BaseModel):
    job_description: str = Field(..., description="Job description text")
    cv_text: str = Field(..., description="CV text for matching")
    job_title: Optional[str] = Field(None, description="Job title")
    job_url: Optional[str] = Field(None, description="Job URL")
    strict_industry_match: bool = Field(True, description="Strict industry matching flag")

class CoverLetterRequest(BaseModel):
    cv_text: str = Field(..., description="CV text")
    job_description: str = Field(..., description="Job description")
    job_title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    skill_bucket: Optional[List[str]] = Field(None, description="Optional skill bucket")
    master_profile: Optional[Dict[str, Any]] = Field(None, description="Optional master profile")
    digital_persona: Optional[Dict[str, Any]] = Field(None, description="Optional digital persona")

class ProfileSaveRequest(BaseModel):
    persona_dna: Dict[str, Any] = Field(..., description="Persona DNA data")
    career_horizon: Dict[str, Any] = Field(..., description="Career horizon data")
    hard_constraints: Dict[str, Any] = Field(..., description="Hard constraints data")

class PreferencesRequest(BaseModel):
    preferences: Dict[str, Any] = Field(..., description="Preferences dictionary")

class JobSaveRequest(BaseModel):
    job_data: Dict[str, Any] = Field(..., description="Job details")
    match_score: float = Field(..., ge=0, le=100, description="Match score (0-100)")
    status: str = Field("pending", description="Job status")
    hook: Optional[str] = Field(None, description="Strategic hook")

class JobStatusUpdate(BaseModel):
    status: str = Field(..., description="New job status")

# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - API status."""
    return {
        "status": "active",
        "service": "Vision Stack 2026 API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    supabase_status = "connected" if get_supabase_db() else "disconnected"
    return {
        "status": "healthy",
        "supabase": supabase_status,
        "engine": "ready"
    }

# ============================================================================
# PROFILE & PERSONA ENDPOINTS
# ============================================================================

@app.post("/api/v1/profile/analyze")
async def analyze_profile(
    request: CVUploadRequest,
    tenant_id: str = Depends(get_tenant_id),
    engine: CoreEngine = Depends(get_engine)
):
    """
    Deep Profile Analysis - Extracts Persona DNA from CV.
    
    This endpoint performs the full deep_profile_analysis, extracting:
    - Professional DNA
    - Latent capabilities
    - Career horizon
    - Hard constraints
    """
    try:
        result = engine.deep_profile_analysis(
            cv_text=request.cv_text,
            skill_bucket=request.skill_bucket,
            rejection_learnings=request.rejection_learnings
        )
        
        # Save to Supabase if available
        supabase = get_supabase_db()
        if supabase and result:
            persona_dna = result.get('persona_dna', {})
            career_horizon = result.get('career_horizon', {})
            hard_constraints = result.get('hard_constraints', {})
            
            supabase.save_profile(
                persona_dna=persona_dna,
                career_horizon=career_horizon,
                hard_constraints=hard_constraints,
                tenant_id=tenant_id
            )
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": result,
            "tenant_id": tenant_id
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Profile analysis failed: {str(e)}")

@app.get("/api/v1/profile")
async def get_profile(
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Get user profile (persona_dna, career_horizon, hard_constraints) from Supabase."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        profile = supabase.get_profile(tenant_id=tenant_id)
        
        if not profile:
            return JSONResponse(status_code=404, content={
                "success": False,
                "message": "Profile not found",
                "tenant_id": tenant_id
            })
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": profile,
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")

@app.post("/api/v1/profile/save")
async def save_profile(
    request: ProfileSaveRequest,
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Save user profile to Supabase."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        success = supabase.save_profile(
            persona_dna=request.persona_dna,
            career_horizon=request.career_horizon,
            hard_constraints=request.hard_constraints,
            tenant_id=tenant_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save profile")
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "Profile saved successfully",
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")

@app.get("/api/v1/profile/dna-embedding")
async def get_dna_embedding(
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Get DNA embedding vector for vector similarity search."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        embedding = supabase.get_dna_embedding(tenant_id=tenant_id)
        
        if not embedding:
            return JSONResponse(status_code=404, content={
                "success": False,
                "message": "DNA embedding not found",
                "tenant_id": tenant_id
            })
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": {"embedding": embedding},
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get DNA embedding: {str(e)}")

# ============================================================================
# JOB ANALYSIS ENDPOINTS
# ============================================================================

@app.post("/api/v1/jobs/analyze")
async def analyze_job(
    request: JobAnalysisRequest,
    tenant_id: str = Depends(get_tenant_id),
    engine: CoreEngine = Depends(get_engine)
):
    """
    Analyze Job Match - Persona DNA Scoring.
    
    This endpoint uses analyze_match from core_engine.py to:
    - Calculate match score (0-100)
    - Generate explanation
    - Identify gaps
    - Apply hard constraints filtering
    - Use vector similarity if DNA embedding is available
    """
    try:
        # Get DNA embedding from Supabase if available
        dna_embedding = None
        supabase = get_supabase_db()
        if supabase:
            dna_embedding = supabase.get_dna_embedding(tenant_id=tenant_id)
        
        # Get digital persona for better matching
        digital_persona = None
        if supabase:
            profile = supabase.get_profile(tenant_id=tenant_id)
            if profile:
                digital_persona = profile.get('persona_dna', {})
        
        # Analyze match
        result = engine.analyze_match(
            job_description=request.job_description,
            cv_text=request.cv_text,
            job_title=request.job_title,
            job_url=request.job_url,
            strict_industry_match=request.strict_industry_match,
            dna_embedding=dna_embedding,
            digital_persona=digital_persona
        )
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": result,
            "tenant_id": tenant_id
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Job analysis failed: {str(e)}")

@app.post("/api/v1/jobs/save")
async def save_job(
    request: JobSaveRequest,
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Save job with match score, status, and hook to Supabase."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        job_id = supabase.save_job(
            job_data=request.job_data,
            match_score=request.match_score,
            status=request.status,
            hook=request.hook,
            tenant_id=tenant_id
        )
        
        if not job_id:
            raise HTTPException(status_code=500, detail="Failed to save job")
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": {"job_id": job_id},
            "message": "Job saved successfully",
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to save job: {str(e)}")

@app.get("/api/v1/jobs")
async def get_jobs(
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Get jobs for tenant with optional filters (status, min_score)."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        jobs = supabase.get_jobs(
            status=status,
            min_score=min_score,
            tenant_id=tenant_id
        )
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": jobs,
            "count": len(jobs),
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get jobs: {str(e)}")

@app.get("/api/v1/jobs/{job_url:path}")
async def get_job_by_url(
    job_url: str,
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Get job by URL for current tenant."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        job = supabase.get_job_by_url(job_url=job_url, tenant_id=tenant_id)
        
        if not job:
            return JSONResponse(status_code=404, content={
                "success": False,
                "message": "Job not found",
                "tenant_id": tenant_id
            })
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": job,
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get job: {str(e)}")

@app.patch("/api/v1/jobs/{job_id}/status")
async def update_job_status(
    job_id: int,
    request: JobStatusUpdate,
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Update job status."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        success = supabase.update_job_status(
            job_id=job_id,
            status=request.status,
            tenant_id=tenant_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update job status")
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "Job status updated successfully",
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update job status: {str(e)}")

# ============================================================================
# COVER LETTER GENERATION ENDPOINT (1200-Character)
# ============================================================================

@app.post("/api/v1/cover-letter/generate")
async def generate_cover_letter(
    request: CoverLetterRequest,
    pdf_tailor: PDFTailor = Depends(get_pdf_tailor)
):
    """
    Generate 1200-Character Cover Letter.
    
    This endpoint uses pdf_tailor.py's generate_cover_letter method which:
    - Generates a cover letter of 800-1200 characters
    - Detects language (Hebrew/English) and responds in same language
    - Uses only actual experience from CV (never invents skills)
    - Includes soft traits and strategic hooks from digital_persona
    - Truncates to 1200 characters at sentence boundaries if needed
    """
    try:
        # Use reframing_analysis method which generates 1200-char cover letters
        cover_letter = pdf_tailor.reframing_analysis(
            job_description=request.job_description,
            cv_text=request.cv_text,
            skill_bucket=request.skill_bucket,
            master_profile=request.master_profile,
            digital_persona=request.digital_persona
        )
        
        # Ensure length is 800-1200 characters (pdf_tailor handles this, but verify)
        length = len(cover_letter)
        if length > 1200:
            # Should not happen, but handle edge case
            cover_letter = cover_letter[:1200]
            last_period = cover_letter.rfind('.')
            if last_period > 800:
                cover_letter = cover_letter[:last_period + 1]
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": {
                "cover_letter": cover_letter,
                "length": len(cover_letter),
                "job_title": request.job_title,
                "company": request.company
            }
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Cover letter generation failed: {str(e)}")

# ============================================================================
# PREFERENCES ENDPOINTS
# ============================================================================

@app.get("/api/v1/preferences")
async def get_preferences(
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Get user preferences from Supabase."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        preferences = supabase.get_preferences(tenant_id=tenant_id)
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "data": preferences,
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get preferences: {str(e)}")

@app.post("/api/v1/preferences")
async def save_preferences(
    request: PreferencesRequest,
    tenant_id: str = Depends(get_tenant_id),
    supabase: Optional[SupabaseDatabaseManager] = Depends(get_supabase_db)
):
    """Save user preferences to Supabase."""
    try:
        if not supabase:
            raise HTTPException(status_code=503, detail="Supabase not available")
        
        success = supabase.save_preferences(
            preferences=request.preferences,
            tenant_id=tenant_id
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save preferences")
        
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "Preferences saved successfully",
            "tenant_id": tenant_id
        })
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to save preferences: {str(e)}")

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler."""
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": f"Internal server error: {str(exc)}"}
    )

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or default to 8000
    port = int(os.getenv("API_PORT", 8000))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    print(f"🚀 Starting Vision Stack 2026 API on http://{host}:{port}")
    print(f"📚 API Documentation: http://{host}:{port}/docs")
    
    uvicorn.run(
        "main_api:app",
        host=host,
        port=port,
        reload=True,  # Auto-reload on code changes (development)
        log_level="info"
    )
