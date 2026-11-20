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

def evaluate_eligibility(role_title: str, experience_text: str, raw_jd: str, exp_min: float, exp_max: float, extracted_skills: List[str] = None) -> Dict[str, Any]:
    """
    Gatekeeper Eligibility Filter & Dynamic Compatibility Scoring:
    1. AI Role Check: Must be AI Developer, ML Engineer, NLP, LangChain, LangGraph, Forward Deployed Engineer, GenAI, etc.
    2. Experience Check: Candidate has 5.5 years. Job must be between 0 to 8 years experience.
    3. Dynamic Compatibility Score (0 - 100%) based on Role, Skills Overlap & Experience Alignment.
    """
    role_lower = (role_title or "").lower()
    jd_lower = (raw_jd or "").lower()
    exp_lower = (experience_text or "").lower()
    skills = [s.lower() for s in (extracted_skills or [])]
    
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
    
    # Pillar 1: Role Alignment (up to 35 pts)
    if any(k in role_lower for k in ["genai", "generative ai", "llm", "agent", "lead ai"]):
        p1_role = 34.0
    elif is_ai_role:
        p1_role = 28.0
    else:
        p1_role = 8.0

    # Pillar 2: Skills Match (up to 35 pts)
    candidate_skills = {"python", "generative ai", "llm", "llms", "langchain", "langgraph", "fastapi", "rag", "pytorch", "multi-agent", "docker"}
    if skills:
        matched_sk = sum(1 for s in skills if any(cs in s for cs in candidate_skills))
        p2_skills = min(35.0, (matched_sk / len(skills)) * 35.0)
    else:
        p2_skills = 26.0

    # Pillar 3: Experience Match (up to 30 pts)
    if not is_exp_eligible:
        p3_exp = 8.0
    elif 3.0 <= 5.5 <= exp_max:
        p3_exp = 30.0
    elif exp_max <= 2.0:
        p3_exp = 25.0
    elif exp_max <= 8.0:
        p3_exp = 26.0
    else:
        p3_exp = 20.0

    total_compat = int(min(max(p1_role + p2_skills + p3_exp, 38), 96))

    return {
        "is_ai_role": is_ai_role,
        "is_exp_eligible": is_exp_eligible,
        "is_flagged": is_flagged,
        "flag_reasons": flag_reasons,
        "compatibility_score": total_compat
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
            exp_max=job_data.get("exp_max", 8.0),
            extracted_skills=job_data.get("extracted_skills", [])
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

        # 6. Check duplicate application across database
        dup = self.check_duplicate_application(
            job_data.get("contact_email", ""),
            job_data.get("company_name", ""),
            job_data.get("role_title", ""),
            exclude_job_id=job_id
        )
        if dup:
            job_data["duplicate_detected"] = 1
            job_data["duplicate_warning"] = dup["reason"]
        else:
            job_data["duplicate_detected"] = 0
            job_data["duplicate_warning"] = ""

        # 7. Update Database with generated artifacts
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

    def check_duplicate_application(self, to_email: str, company_name: str, role_title: str, exclude_job_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Hard Duplicate Prevention Guard:
        Checks whether an application has already been dispatched, scheduled, or bounced for:
        1. Exact same recipient email
        2. Same company name and matching role title
        """
        jobs = get_all_jobs()
        norm_to = (to_email or "").strip().lower()
        norm_comp = (company_name or "").strip().lower()
        norm_role = (role_title or "").strip().lower()

        for j in jobs:
            if exclude_job_id and j.get("id") == exclude_job_id:
                continue
            
            status = j.get("status", "")
            if status not in ("SENT", "SCHEDULED", "REPLIED", "BOUNCED"):
                continue

            j_email = (j.get("contact_email") or "").strip().lower()
            j_comp = (j.get("company_name") or "").strip().lower()
            j_role = (j.get("role_title") or "").strip().lower()

            # Check 1: Same recipient email address
            if norm_to and j_email and norm_to == j_email and not norm_to.startswith("taaryan."):
                sent_d = (j.get("sent_at") or j.get("created_at") or "")[:10]
                return {
                    "is_duplicate": True,
                    "type": "RECIPIENT_DUPLICATE",
                    "matched_job_id": j.get("id"),
                    "recipient": j_email,
                    "company": j.get("company_name"),
                    "role": j.get("role_title"),
                    "date": sent_d,
                    "reason": f"An application was already sent to {j_email} on {sent_d} for {j.get('company_name')} ({j.get('role_title')})."
                }

            # Check 2: Same company name & role title
            if norm_comp and j_comp and (norm_comp in j_comp or j_comp in norm_comp):
                # Clean role tokens
                r1 = set(re.findall(r'[a-zA-Z0-9]+', norm_role))
                r2 = set(re.findall(r'[a-zA-Z0-9]+', j_role))
                common = r1.intersection(r2) - {"engineer", "developer", "lead", "senior", "ai", "ml", "at", "for"}
                if norm_role == j_role or len(common) >= 1 or (norm_role in j_role or j_role in norm_role):
                    sent_d = (j.get("sent_at") or j.get("created_at") or "")[:10]
                    return {
                        "is_duplicate": True,
                        "type": "COMPANY_ROLE_DUPLICATE",
                        "matched_job_id": j.get("id"),
                        "recipient": j_email,
                        "company": j.get("company_name"),
                        "role": j.get("role_title"),
                        "date": sent_d,
                        "reason": f"An application for {j.get('role_title')} at {j.get('company_name')} was already sent to {j_email or 'recruiter'}."
                    }

        return None

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

        # HARD DUPLICATE DELIVERY BLOCK - Guarantees no duplicate email is ever delivered
        dup = self.check_duplicate_application(to_email, job.get("company_name", ""), job.get("role_title", ""), exclude_job_id=job_id)
        if dup:
            update_job_status(job_id, job.get("status"), {
                "duplicate_detected": 1,
                "duplicate_warning": dup["reason"]
            })
            return {
                "success": False,
                "duplicate_blocked": True,
                "error": f"⚠️ DUPLICATE DELIVERY BLOCKED: {dup['reason']} Email dispatch was blocked to prevent spamming."
            }

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

        # HARD DUPLICATE DELIVERY BLOCK - Guarantees no duplicate email is ever scheduled
        dup = self.check_duplicate_application(to_email, job.get("company_name", ""), job.get("role_title", ""), exclude_job_id=job_id)
        if dup:
            update_job_status(job_id, job.get("status"), {
                "duplicate_detected": 1,
                "duplicate_warning": dup["reason"]
            })
            return {
                "success": False,
                "duplicate_blocked": True,
                "error": f"⚠️ DUPLICATE SCHEDULE BLOCKED: {dup['reason']} Scheduling was aborted to prevent duplicate outreach."
            }

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

    def cancel_and_reset_scheduled_application(self, job_id: int) -> Dict[str, Any]:
        """Cancel a scheduled email send, delete any pending Gmail draft, and reset job to reviewable state."""
        from .database import cancel_scheduled_job
        job = get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found."}

        draft_id = job.get("gmail_draft_id")
        if draft_id:
            try:
                from .agents.email_agent import GMAIL_BIN
                subprocess.run([GMAIL_BIN, "mutate", "delete-draft", str(draft_id)], capture_output=True, text=True)
            except Exception:
                pass

        cancel_scheduled_job(job_id)
        return {
            "success": True,
            "message": "Scheduled email cancelled. Application reset to review state so you can reschedule or send now."
        }

    def mark_dm_sent(self, job_id: int) -> Dict[str, Any]:
        """Mark job application as sent via LinkedIn DM."""
        job = get_job(job_id)
        if not job:
            return {"success": False, "error": "Job not found."}
        update_job_status(job_id, "DM_SENT")
        return {"success": True, "message": "Marked as LinkedIn DM Sent."}

    def sync_all_replies(self) -> Dict[str, Any]:
        """
        Deep 30-Day Application & Reply Audit:
        Scans Gmail past month sent emails in 'AI Carrier', checks for duplicate sends,
        detects incoming recruiter replies, flags bounces, and updates all job records.
        """
        audit_res = self.email_agent.audit_past_month_applications()
        jobs = get_all_jobs()
        now_str = datetime.now().isoformat()
        
        # 1. Update detected replies
        replies_found_count = 0
        for rep in audit_res.get("replies", []):
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
                    replies_found_count += 1

        # 2. Cross-reference sent applications from database
        sent_or_bounced = [j for j in jobs if j.get("status") in ("SENT", "BOUNCED")]
        if len(sent_or_bounced) > audit_res.get("total_sent_month", 0):
            audit_res["total_sent_month"] = len(sent_or_bounced)

        # 3. Detect duplicates across jobs database & email audit (by recipient & by company+role)
        db_duplicates = []
        comp_role_map = {}
        rcpt_map = {}

        for j in jobs:
            c = (j.get("contact_email") or "").lower().strip()
            if c and not c.startswith("taaryan."):
                rcpt_map.setdefault(c, []).append(j)
            
            comp = (j.get("company_name") or "").strip().lower()
            role = (j.get("role_title") or "").strip().lower()
            if comp:
                key = f"{comp}::{role}"
                comp_role_map.setdefault(key, []).append(j)

        for rcpt, j_list in rcpt_map.items():
            if len(j_list) > 1:
                warn = f"Duplicate alert: {len(j_list)} applications sent/registered to {rcpt}."
                db_duplicates.append({
                    "type": "RECIPIENT_DUPLICATE",
                    "recipient": rcpt,
                    "count": len(j_list),
                    "warning": warn
                })
                for j in j_list:
                    update_job_status(j["id"], j.get("status"), {
                        "duplicate_detected": 1,
                        "duplicate_warning": warn
                    })

        for key, j_list in comp_role_map.items():
            if len(j_list) > 1:
                comp_name = j_list[0].get("company_name")
                role_name = j_list[0].get("role_title")
                warn = f"Duplicate alert: {len(j_list)} applications sent for {comp_name} - {role_name}."
                # Avoid duplicate entries in list
                if not any(d.get("type") == "ROLE_DUPLICATE" and d.get("company") == comp_name for d in db_duplicates):
                    db_duplicates.append({
                        "type": "ROLE_DUPLICATE",
                        "company": comp_name,
                        "role": role_name,
                        "count": len(j_list),
                        "warning": warn
                    })
                for j in j_list:
                    update_job_status(j["id"], j.get("status"), {
                        "duplicate_detected": 1,
                        "duplicate_warning": warn
                    })

        existing_warns = {d.get("warning") for d in audit_res.get("duplicates_found", [])}
        for dd in db_duplicates:
            if dd.get("warning") not in existing_warns:
                audit_res.setdefault("duplicates_found", []).append(dd)
        audit_res["duplicates_count"] = len(audit_res.get("duplicates_found", []))

        # 4. Update bounced jobs in database
        bounced_count = 0
        for b in audit_res.get("bounced_emails", []):
            b_rcpt = (b.get("bounced_recipient") or "").lower()
            b_snip = b.get("snippet") or "Address not found: domain could not be found."
            for j in jobs:
                j_mail = (j.get("contact_email") or "").lower()
                if (b_rcpt and b_rcpt == j_mail) or (j_mail and j_mail in (b.get("subject", "") + b_snip).lower()):
                    update_job_status(j["id"], "BOUNCED", {
                        "reply_snippet": f"⚠️ Address not found: Message was not delivered to {j_mail} because domain could not be found."
                    })
                    bounced_count += 1

        if bounced_count > audit_res.get("bounced_count", 0):
            audit_res["bounced_count"] = bounced_count

        total_sent = audit_res.get("total_sent_month", 0)
        total_bounced = audit_res.get("bounced_count", 0)
        if total_sent > 0:
            h_pct = int(round(max(0, (total_sent - total_bounced) / total_sent) * 100))
            audit_res["health_score"] = f"{h_pct}%"
        else:
            audit_res["health_score"] = "100%"

        audit_res["jobs_audited_count"] = len(jobs)
        audit_res["replies_found"] = replies_found_count or len(audit_res.get("replies", []))
        audit_res["summary"] = f"Scanned past 30 days in Gmail (AI Carrier & Inbox): {total_sent} sent, {audit_res['replies_found']} replies, {audit_res['duplicates_count']} duplicates flagged, {total_bounced} bounce detected."
        return audit_res
