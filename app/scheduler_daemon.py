import os
import sys
import time
import json
import subprocess
from datetime import datetime

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, WORKSPACE_ROOT)

from app.database import get_due_scheduled_jobs, mark_scheduled_sent, get_job
from app.agents.email_agent import GMAIL_BIN, EmailAgent

PID_FILE = os.path.join(WORKSPACE_ROOT, ".scheduler.pid")

def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def ensure_scheduler_running():
    """Ensure the detached background scheduler is running independently of the web app."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if is_pid_running(pid):
                return pid
        except Exception:
            pass

    # Launch detached background daemon
    python_bin = sys.executable
    script_path = os.path.abspath(__file__)
    log_path = os.path.join(WORKSPACE_ROOT, "scheduler.log")
    
    with open(log_path, "a") as log_file:
        proc = subprocess.Popen(
            [python_bin, script_path],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
            cwd=WORKSPACE_ROOT
        )
    
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    return proc.pid

def dispatch_due_jobs():
    """Check database for due scheduled applications and dispatch them immediately."""
    agent = EmailAgent()
    due_jobs = get_due_scheduled_jobs()
    for job in due_jobs:
        job_id = job["id"]
        recipient = job.get("contact_email")
        subject = job.get("email_subject") or f"Application for {job.get('role_title', 'Role')} - Aaryan Tiwari"
        body = job.get("email_body") or ""
        draft_id = job.get("gmail_draft_id")
        pdf_path = job.get("custom_pdf_path")

        if not pdf_path or not os.path.exists(pdf_path):
            candidate = os.path.join(WORKSPACE_ROOT, "generated_resumes", f"job_{job_id}", "Aaryan Gen Ai Resume.pdf")
            pdf_path = candidate if os.path.exists(candidate) else os.path.join(WORKSPACE_ROOT, "Resume", "Aaryan_Resume.pdf")

        print(f"[{datetime.now().isoformat()}] Dispatching scheduled application #{job_id} to {recipient}...")

        sent_success = False
        msg_id = ""

        # 1. Try sending via pre-created Gmail draft
        if draft_id:
            try:
                res = subprocess.run([
                    GMAIL_BIN, "mutate", "send-draft", draft_id, "--json"
                ], capture_output=True, text=True, check=True, env=os.environ.copy())
                sent_success = True
                try:
                    data = json.loads(res.stdout)
                    msg_id = data.get("id") or "sent"
                    th_id = data.get("threadId") or ""
                    agent.tag_as_carrier_item(message_id=msg_id, thread_id=th_id)
                except Exception:
                    msg_id = "sent"
                print(f"[{datetime.now().isoformat()}] Draft {draft_id} sent successfully and filed in 'AI Carrier'.")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] Draft send failed: {e}. Falling back to direct send...")

        # 2. Fallback to direct send with attached PDF
        if not sent_success and recipient:
            send_res = agent.send_email(
                to_email=recipient,
                subject=subject,
                body=body,
                attachment_pdf_path=pdf_path
            )
            if send_res.get("success"):
                sent_success = True
                msg_id = send_res.get("message_id", "sent")
                print(f"[{datetime.now().isoformat()}] Direct send with attachment successful.")

        if sent_success:
            mark_scheduled_sent(job_id, message_id=msg_id)
            print(f"[{datetime.now().isoformat()}] Application #{job_id} marked as SENT in database.")
        else:
            print(f"[{datetime.now().isoformat()}] Failed to dispatch scheduled application #{job_id}.")

def run_scheduler_loop():
    """Independent background loop that dispatches scheduled application emails on time."""
    pid = os.getpid()
    with open(PID_FILE, "w") as f:
        f.write(str(pid))
    
    print(f"[{datetime.now().isoformat()}] JobFlow Scheduler Daemon started (PID {pid}).")

    while True:
        try:
            dispatch_due_jobs()
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Scheduler error: {e}")
        time.sleep(15)

if __name__ == "__main__":
    run_scheduler_loop()
