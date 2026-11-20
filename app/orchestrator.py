import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from .database import save_job, get_job, get_all_jobs, update_job_status, check_duplicate_application
from .agents.linkedin_agent import LinkedInAgent
from .agents.resume_agent import ResumeAgent
from .agents.email_agent import EmailAgent
from .llm_client import GeminiClient

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def evaluate_eligibility(role_title: str, experience_text: str, raw_jd: str, exp_min: float, exp_max: float) -> Dict[str, Any]:
    """
    Gatekeeper Eligibility Filter:
    1. AI Role Check: Must be AI Developer, ML Engineer, NLP, LangChain, LangGraph, Forward Deployed Engineer, GenAI, etc.
    2. Experience Check: Candidate has 5.5 years. Job must be between 0 to 8 years experience.
    """
    role_lower = (role_title or "").lower()
    jd_lower = (raw_jd or "").lower()
    exp_lower = (experience_text or "").lower()
    
    flag_reasons = []
    
    # 1. AI Role Check
    ai_keywords = [
        "ai", "genai", "generative ai", "llm", "large language model",
        "machine learning", "ml", "deep learning", "nlp", "natural language",
        "langchain", "langgraph", "agentic", "agent", "agents", "rag",
        "forward deployed", "computer vision", "prompt engineer", "prompt engineering",
        "vllm", "diffusion", "neural", "pytorch", "tensorflow"
    ]
    has_ai_in_title = any(re.search(r'\b' + re.escape(k) + r'\b', role_lower) for k in ai_keywords)
    has_ai_in_jd = any(re.search(r'\b' + re.escape(k) + r'\b', jd_lower) for k in ["generative ai", "llm", "langchain", "langgraph", "rag", "multi-agent", "agentic", "prompt engineering"])
    
    is_ai_role = has_ai_in_title or has_ai_in_jd
    if not is_ai_role:
        flag_reasons.append("⚠️ Flagged: Non-AI Role (Candidate specializes in Generative AI / LLMs).")

    # 2. Experience Check: Candidate has 5.5 years. Target: 0 to 8 years.
    is_exp_eligible = True
    if exp_max > 8.0 or any(phrase in exp_lower or phrase in jd_lower for phrase in ["9+ years", "10+ years", "11+ years", "12+ years", "15+ years", "9 to 12", "10 to 15", "8-12 years", "8 to 12 years"]):
        is_exp_eligible = False
        flag_reasons.append(f"⚠️ Flagged: Requires >8 Years Experience (Job asks {experience_text or 'senior level'}, candidate has 5.5 years).")
        
    is_flagged = bool(flag_reasons)
    
    # Compatibility calculation
    if is_ai_role and is_exp_eligible:
        if exp_min <= 5.5 <= exp_max:
            compat_score = 92
        elif exp_max <= 3.0:
            compat_score = 86
        else:
            compat_score = 88
    else:
        if not is_ai_role and not is_exp_eligible:
            compat_score = 38
        elif not is_ai_role:
            compat_score = 45
        else:
            compat_score = 56

    return {
        "is_ai_role": is_ai_role,
        "is_exp_eligible": is_exp_eligible,
        "is_flagged": is_flagged,
        "flag_reasons": flag_reasons,
        "compatibility_score": compat_score
    }

class JobAutomationOrchestrator:
    """Coordinates LinkedIn parsing, Resume tailoring, Email drafting/sending, and Reply tracking."""

    def __init__(self):
        self.linkedin_agent = LinkedInAgent(llm_client=GeminiClient(agent_role="linkedin"))
        self.resume_agent = ResumeAgent()
        self.email_agent = EmailAgent(
            sender_email="taaryan.official@gmail.com",
            llm_client=GeminiClient(agent_role="email")
        )

    def process_linkedin_url(self, url: str, raw_text: str = None, model: str = "gemini-3.5-flash") -> Dict[str, Any]:
        """Step 1 & 2 & 3 & 4: Scrape, evaluate eligibility, check duplicate, tailor resume, draft email."""
        # 1. Scrape & Research Job via LLM
        job_data = self.linkedin_agent.scrape_post(url, raw_text=raw_text, model=model)
        
        # 2. Gatekeeper Filter
        eligibility = evaluate_eligibility(
            role_title=job_data.get("role_title", ""),
            experience_text=job_data.get("experience", ""),
            raw_jd=job_data.get("raw_text", ""),
            exp_min=job_data.get("exp_min", 0.0),
            exp_max=job_data.get("exp_max", 8.0)
        )
        job_data.update(eligibility)

        # 3. Duplicate Application Shield
        is_dup, dup_msg = check_duplicate_application(
            contact_email=job_data.get("contact_email"),
            company_name=job_data.get("company_name"),
            role_title=job_data.get("role_title"),
            linkedin_url=url
        )
        job_data["duplicate_detected"] = is_dup
        job_data["duplicate_warning"] = dup_msg
        if is_dup:
            job_data["flag_reasons"].append(dup_msg)
            job_data["is_flagged"] = True

        job_data["fetch_date"] = datetime.now().strftime("%Y-%m-%d")

        # Save initial record to get job_id
        job_id = save_job(job_data)
        job_data["id"] = job_id

        # 4. Tailor Resume (4-Pillar Realistic ATS Evaluation & Styling)
        role_title = job_data.get("role_title", "GenAI Engineer")
        extracted_skills = job_data.get("extracted_skills", [])
        raw_jd = job_data.get("raw_text", "")
        resume_res = self.resume_agent.tailor_resume(
            job_id,
            role_title,
            extracted_skills,
            raw_jd=raw_jd,
            exp_min=job_data.get("exp_min", 0.0),
            exp_max=job_data.get("exp_max", 8.0)
        )

        # 5. Draft Email via LLM (Tailored tech skills in polite corporate tone)
        email_draft = self.email_agent.draft_email(job_data, model=model)

        # 6. Update Database with generated artifacts
        job_data["ats_score"] = resume_res.get("ats_score", 85)
        job_data["custom_docx_path"] = resume_res["custom_docx_path"]
        job_data["custom_pdf_path"] = resume_res["custom_pdf_path"]
        job_data["custom_preview_path"] = resume_res.get("custom_preview_path")
        job_data["modified_keywords"] = resume_res["modified_keywords"]
        job_data["email_subject"] = email_draft["subject"]
        job_data["email_body"] = email_draft["body"]
        job_data["status"] = "PENDING_REVIEW"

        save_job(job_data)
        return get_job(job_id)

    def approve_and_send(self, job_id: int, custom_subject: str = None, custom_body: str = None, recipient_email: str = None) -> Dict[str, Any]:
        """User clicks 'Approve & Send' in Dashboard -> Dispatches Email + Attachment."""
        job = get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found."}

        to_email = recipient_email or job.get("contact_email")
        subject = custom_subject or job.get("email_subject")
        body = custom_body or job.get("email_body")
        pdf_path = job.get("custom_pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            candidate = os.path.join(WORKSPACE_ROOT, "generated_resumes", f"job_{job_id}", "Aaryan Gen Ai Resume.pdf")
            pdf_path = candidate if os.path.exists(candidate) else os.path.join(WORKSPACE_ROOT, "Resume", "Aaryan_Resume.pdf")

        if not to_email:
            return {"success": False, "error": "No recipient email address. Please provide an email or use LinkedIn DM."}

        # Send through Gmail
        res = self.email_agent.send_email(to_email, subject, body, pdf_path)
        if res.get("success"):
            update_job_status(job_id, "SENT", {
                "contact_email": to_email,
                "email_subject": subject,
                "email_body": body,
                "gmail_message_id": res.get("message_id", ""),
                "gmail_thread_id": res.get("thread_id", ""),
                "sent_at": datetime.now().isoformat()
            })
            return {"success": True, "message": f"Application email sent to {to_email} and filed in 'AI Carrier'!"}
        else:
            return {"success": False, "error": res.get("error", "Failed to send email.")}

    def schedule_application(self, job_id: int, scheduled_at: str, custom_subject: str = None, custom_body: str = None, recipient_email: str = None) -> Dict[str, Any]:
        """Schedule an email to be sent at a specific date/time, creating a draft in Gmail immediately and triggering detached scheduler."""
        job = get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found."}

        to_email = recipient_email or job.get("contact_email")
        if not to_email:
            return {"success": False, "error": "No recipient email found for this role."}

        subject = custom_subject or job.get("email_subject")
        body = custom_body or job.get("email_body")
        pdf_path = job.get("custom_pdf_path")
        if not pdf_path or not os.path.exists(pdf_path):
            candidate = os.path.join(WORKSPACE_ROOT, "generated_resumes", f"job_{job_id}", "Aaryan Gen Ai Resume.pdf")
            pdf_path = candidate if os.path.exists(candidate) else os.path.join(WORKSPACE_ROOT, "Resume", "Aaryan_Resume.pdf")

        # Create draft in Gmail app immediately so user can see it in Gmail
        draft_res = self.email_agent.create_draft(
            to_email=to_email,
            subject=subject,
            body=body,
            attachment_pdf_path=pdf_path
        )
        draft_id = draft_res.get("draft_id") if draft_res.get("success") else None
        thread_id = draft_res.get("thread_id")

        # Record schedule in database
        from .database import schedule_job_in_db
        schedule_job_in_db(
            job_id=job_id,
            scheduled_at=scheduled_at,
            draft_id=draft_id,
            recipient_email=to_email,
            subject=subject,
            body=body
        )
        if thread_id:
            update_job_status(job_id, "SCHEDULED", {"gmail_thread_id": thread_id})

        # Ensure background scheduler daemon is running independently of web server
        from .scheduler_daemon import ensure_scheduler_running
        try:
            ensure_scheduler_running()
        except Exception as e:
            print(f"[Orchestrator] ensure_scheduler_running notice: {e}")

        return {
            "success": True,
            "message": f"Email scheduled for {scheduled_at}. Filed in 'AI Carrier' folder.",
            "draft_id": draft_id,
            "scheduled_at": scheduled_at
        }

    def mark_dm_sent(self, job_id: int) -> Dict[str, Any]:
        """Mark job application as sent via LinkedIn DM."""
        job = get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found."}
        update_job_status(job_id, "DM_SENT")
        return {"success": True, "message": "Marked as LinkedIn DM Sent."}

    def sync_all_replies(self) -> Dict[str, Any]:
        """Precision tracking: check exclusively inside the 'AI Carrier' folder for any incoming HR responses."""
        carrier_replies = self.email_agent.check_replies_in_carrier_folder()
        jobs = get_all_jobs()
        updated_count = 0
        details = []

        now_str = datetime.utcnow().isoformat()

        for rep in carrier_replies:
            from_addr = (rep.get("from") or "").lower()
            rep_thread = rep.get("thread_id")
            snippet = rep.get("snippet") or "Received an HR response."

            for job in jobs:
                contact = (job.get("contact_email") or "").lower()
                job_thread = job.get("gmail_thread_id")

                is_match = False
                if rep_thread and job_thread and rep_thread == job_thread:
                    is_match = True
                elif contact and contact in from_addr:
                    is_match = True

                if is_match and job.get("status") != "REPLIED":
                    update_job_status(job["id"], "REPLIED", {
                        "reply_snippet": snippet,
                        "reply_detected_at": now_str
                    })
                    updated_count += 1
                    details.append({
                        "job_id": job["id"],
                        "company": job.get("company_name"),
                        "snippet": snippet
                    })

        if updated_count == 0:
            for job in jobs:
                if job.get("status") in ["SENT", "PENDING_REVIEW"] and job.get("contact_email"):
                    reply_info = self.email_agent.check_replies(job["contact_email"])
                    if reply_info.get("has_reply"):
                        update_job_status(job["id"], "REPLIED", {
                            "reply_snippet": reply_info.get("snippet", ""),
                            "reply_detected_at": now_str
                        })
                        updated_count += 1
                        details.append({
                            "job_id": job["id"],
                            "company": job.get("company_name"),
                            "snippet": reply_info.get("snippet")
                        })

        return {
            "success": True,
            "carrier_folder": "AI Carrier",
            "replies_found": updated_count,
            "details": details
        }
