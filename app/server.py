import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from .database import init_db, get_all_jobs, get_job
from .orchestrator import JobAutomationOrchestrator

app = FastAPI(title="LinkedIn Multi-Agent Job Application Suite")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
init_db()

import asyncio

async def in_process_scheduler_loop():
    """In-process async worker running inside FastAPI to dispatch due jobs every 15s."""
    from .scheduler_daemon import dispatch_due_jobs
    while True:
        try:
            dispatch_due_jobs()
        except Exception as e:
            print(f"[In-Process Scheduler Error]: {e}")
        await asyncio.sleep(15)

@app.on_event("startup")
async def startup_event():
    # 1. Start in-process background task
    asyncio.create_task(in_process_scheduler_loop())
    # 2. Ensure detached scheduler daemon is also active for when web UI is closed
    try:
        from .scheduler_daemon import ensure_scheduler_running
        ensure_scheduler_running()
    except Exception as e:
        print(f"[Server Startup] Detached daemon notice: {e}")

orchestrator = JobAutomationOrchestrator()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

class ProcessRequest(BaseModel):
    url: str
    raw_text: Optional[str] = None
    model: Optional[str] = "gemini-3.5-flash"

class SendRequest(BaseModel):
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None

class ScheduleRequest(BaseModel):
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    scheduled_at: str

@app.get("/")
def get_dashboard():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"message": "Job Application Suite API running."}

@app.post("/api/jobs/process")
def process_job(req: ProcessRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="LinkedIn URL is required.")
    try:
        job = orchestrator.process_linkedin_url(req.url, raw_text=req.raw_text, model=req.model or "gemini-3.5-flash")
        return {"success": True, "job": job}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/jobs")
def list_jobs():
    jobs = get_all_jobs()
    return {"jobs": jobs}

@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job": job}

@app.get("/api/jobs/{job_id}/preview")
def view_preview(job_id: int):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    preview_path = job.get("custom_preview_path")
    alt_path = os.path.join(os.path.dirname(__file__), "..", "generated_resumes", f"Aaryan_Resume_Job_{job_id}_preview-1.png")
    if not preview_path or not os.path.exists(preview_path):
        if os.path.exists(alt_path):
            preview_path = alt_path
        else:
            pdf_path = job.get("custom_pdf_path")
            if pdf_path and os.path.exists(pdf_path):
                from .agents.resume_agent import ResumeAgent
                agent = ResumeAgent()
                preview_path = agent._generate_png_preview(pdf_path, job_id)
    if not preview_path or not os.path.exists(preview_path):
        raise HTTPException(status_code=404, detail="Preview not available.")
    return FileResponse(preview_path, media_type="image/png")

@app.get("/api/jobs/{job_id}/docx")
def download_docx(job_id: int):
    job = get_job(job_id)
    if not job or not job.get("custom_docx_path") or not os.path.exists(job["custom_docx_path"]):
        raise HTTPException(status_code=404, detail="DOCX file not found.")
    return FileResponse(
        job["custom_docx_path"],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="Aaryan Gen Ai Resume.docx"
    )

@app.get("/api/jobs/{job_id}/pdf")
def view_pdf(job_id: int):
    job = get_job(job_id)
    if not job or not job.get("custom_pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not found.")
    pdf_path = job["custom_pdf_path"]
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file does not exist on disk.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="Aaryan Gen Ai Resume.pdf"'}
    )

@app.post("/api/jobs/{job_id}/send")
def approve_and_send(job_id: int, req: SendRequest):
    res = orchestrator.approve_and_send(
        job_id=job_id,
        custom_subject=req.subject,
        custom_body=req.body,
        recipient_email=req.recipient_email
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

@app.post("/api/jobs/{job_id}/schedule")
def approve_and_schedule(job_id: int, req: ScheduleRequest):
    res = orchestrator.schedule_application(
        job_id=job_id,
        scheduled_at=req.scheduled_at,
        custom_subject=req.subject,
        custom_body=req.body,
        recipient_email=req.recipient_email
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

@app.post("/api/jobs/{job_id}/mark_dm")
def mark_dm(job_id: int):
    res = orchestrator.mark_dm_sent(job_id)
    return res

@app.post("/api/jobs/{job_id}/cancel_schedule")
def cancel_schedule(job_id: int):
    res = orchestrator.cancel_and_reset_scheduled_application(job_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

@app.post("/api/jobs/check_replies")
def check_replies():
    res = orchestrator.sync_all_replies()
    return res

@app.delete("/api/jobs/{job_id}")
def delete_single_job(job_id: int):
    from .database import delete_job
    success = delete_job(job_id)
    return {"success": success, "message": f"Application #{job_id} deleted."}

@app.delete("/api/jobs")
def delete_all_history():
    from .database import delete_all_jobs
    success = delete_all_jobs()
    return {"success": success, "message": "All application history cleared."}

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
