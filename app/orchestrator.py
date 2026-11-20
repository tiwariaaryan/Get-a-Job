import os
from typing import Dict, Any, List
from .database import save_job, get_job, get_all_jobs, update_job_status
from .agents.linkedin_agent import LinkedInAgent
from .agents.resume_agent import ResumeAgent
from .agents.email_agent import EmailAgent
from .llm_client import GeminiClient

class JobAutomationOrchestrator:
    """Coordinates LinkedIn parsing, Resume tailoring, Email drafting/sending, and Reply tracking."""

    def __init__(self):
        # Dedicated Gemini clients per agent to prevent quota exhaustion
        self.linkedin_agent = LinkedInAgent(llm_client=GeminiClient(agent_role="linkedin"))
        self.resume_agent = ResumeAgent()
        self.email_agent = EmailAgent(
            sender_email="taaryan.official@gmail.com",
            llm_client=GeminiClient(agent_role="email")
        )

    def process_linkedin_url(self, url: str, raw_text: str = None, model: str = "gemini-3.5-flash") -> Dict[str, Any]:
        """Step 1 & 2 & 3 & 4: Scrape, tailor resume, draft email with Gemini 3.5 (fallback to 3.5-lite & 2.5)."""
        # 1. Scrape & Research Job via LLM
        job_data = self.linkedin_agent.scrape_post(url, raw_text=raw_text, model=model)
        
        # Save initial record to get job_id
        job_id = save_job(job_data)
        job_data["id"] = job_id

        # 2. Tailor Resume (Skills + Summary 20% ATS adaptation & Scoring)
        role_title = job_data.get("role_title", "GenAI Engineer")
        extracted_skills = job_data.get("extracted_skills", [])
        raw_jd = job_data.get("raw_text", "")
        resume_res = self.resume_agent.tailor_resume(job_id, role_title, extracted_skills, raw_jd=raw_jd)

        # 3. Draft Email via LLM
        email_draft = self.email_agent.draft_email(job_data, model=model)

        # 4. Update Database with generated artifacts
        job_data["ats_score"] = resume_res.get("ats_score", 92)
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
                "sent_at": os.getenv("CURRENT_TIME") or None
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

        # Check against carrier folder responses
        for rep in carrier_replies:
            from_addr = (rep.get("from") or "").lower()
            rep_thread = rep.get("thread_id")
            snippet = rep.get("snippet") or "Received an HR response."

            for job in jobs:
                contact = (job.get("contact_email") or "").lower()
                job_thread = job.get("gmail_thread_id")

                # Match by Gmail thread ID or recruiter email
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

        # Fallback to direct check if no replies found from carrier scan
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
