import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "jobs.db"))

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        linkedin_url TEXT UNIQUE NOT NULL,
        company_name TEXT,
        role_title TEXT,
        location TEXT,
        job_type TEXT,
        experience TEXT,
        recruiter_name TEXT,
        recruiter_profile_url TEXT,
        contact_email TEXT,
        delivery_channel TEXT,
        extracted_skills TEXT,
        modified_keywords TEXT,
        status TEXT DEFAULT 'PENDING_REVIEW',
        ats_score INTEGER DEFAULT 85,
        custom_docx_path TEXT,
        custom_pdf_path TEXT,
        custom_preview_path TEXT,
        email_subject TEXT,
        email_body TEXT,
        linkedin_dm_text TEXT,
        gmail_message_id TEXT,
        sent_at TEXT,
        reply_detected_at TEXT,
        reply_snippet TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Ensure column exists in existing DB
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN custom_preview_path TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN ats_score INTEGER DEFAULT 85")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN post_date TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN scheduled_at TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN gmail_draft_id TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE jobs ADD COLUMN gmail_thread_id TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()

def delete_job(job_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT custom_docx_path, custom_pdf_path, custom_preview_path FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if row:
        for path in [row["custom_docx_path"], row["custom_pdf_path"], row["custom_preview_path"]]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if row["custom_docx_path"] and "job_" in row["custom_docx_path"]:
            job_dir = os.path.dirname(row["custom_docx_path"])
            if os.path.exists(job_dir):
                import shutil
                shutil.rmtree(job_dir, ignore_errors=True)
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return True

def schedule_job_in_db(job_id: int, scheduled_at: str, draft_id: str = None, recipient_email: str = None, subject: str = None, body: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        UPDATE jobs SET
            status = 'SCHEDULED',
            scheduled_at = ?,
            gmail_draft_id = COALESCE(?, gmail_draft_id),
            contact_email = COALESCE(?, contact_email),
            email_subject = COALESCE(?, email_subject),
            email_body = COALESCE(?, email_body),
            updated_at = ?
        WHERE id = ?
    """, (scheduled_at, draft_id, recipient_email, subject, body, now, job_id))
    conn.commit()
    conn.close()

def get_due_scheduled_jobs():
    """Retrieve all jobs marked as SCHEDULED whose scheduled_at is less than or equal to now."""
    conn = get_connection()
    cursor = conn.cursor()
    now_local = datetime.now().isoformat()
    now_utc = datetime.utcnow().isoformat()
    cursor.execute("""
        SELECT * FROM jobs 
        WHERE status = 'SCHEDULED' 
          AND (scheduled_at <= ? OR scheduled_at <= ?)
    """, (now_local, now_utc))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["extracted_skills"] = json.loads(d.get("extracted_skills") or "[]")
        d["modified_keywords"] = json.loads(d.get("modified_keywords") or "[]")
        result.append(d)
    return result

def mark_scheduled_sent(job_id: int, message_id: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        UPDATE jobs SET
            status = 'SENT',
            sent_at = ?,
            gmail_message_id = COALESCE(?, gmail_message_id),
            updated_at = ?
        WHERE id = ?
    """, (now, message_id, now, job_id))
    conn.commit()
    conn.close()

def save_job(job_data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if job exists
    cursor.execute("SELECT id FROM jobs WHERE linkedin_url = ?", (job_data["linkedin_url"],))
    row = cursor.fetchone()
    
    now = datetime.utcnow().isoformat()
    skills_json = json.dumps(job_data.get("extracted_skills", []))
    keywords_json = json.dumps(job_data.get("modified_keywords", []))
    
    if row:
        job_id = row["id"]
        cursor.execute("""
        UPDATE jobs SET
            company_name = ?,
            role_title = ?,
            location = ?,
            job_type = ?,
            experience = ?,
            recruiter_name = ?,
            recruiter_profile_url = ?,
            contact_email = ?,
            delivery_channel = ?,
            extracted_skills = ?,
            modified_keywords = ?,
            status = COALESCE(?, status),
            ats_score = ?,
            post_date = ?,
            custom_docx_path = ?,
            custom_pdf_path = ?,
            custom_preview_path = ?,
            email_subject = ?,
            email_body = ?,
            linkedin_dm_text = ?,
            updated_at = ?
        WHERE id = ?
        """, (
            job_data.get("company_name"),
            job_data.get("role_title"),
            job_data.get("location"),
            job_data.get("job_type"),
            job_data.get("experience"),
            job_data.get("recruiter_name"),
            job_data.get("recruiter_profile_url"),
            job_data.get("contact_email"),
            job_data.get("delivery_channel"),
            skills_json,
            keywords_json,
            job_data.get("status", "PENDING_REVIEW"),
            job_data.get("ats_score", 92),
            job_data.get("post_date", "Recently posted"),
            job_data.get("custom_docx_path"),
            job_data.get("custom_pdf_path"),
            job_data.get("custom_preview_path"),
            job_data.get("email_subject"),
            job_data.get("email_body"),
            job_data.get("linkedin_dm_text"),
            now,
            job_id
        ))
    else:
        cursor.execute("""
        INSERT INTO jobs (
            linkedin_url, company_name, role_title, location, job_type, experience,
            recruiter_name, recruiter_profile_url, contact_email, delivery_channel,
            extracted_skills, modified_keywords, status, ats_score, post_date, custom_docx_path, custom_pdf_path,
            custom_preview_path, email_subject, email_body, linkedin_dm_text, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_data["linkedin_url"],
            job_data.get("company_name"),
            job_data.get("role_title"),
            job_data.get("location"),
            job_data.get("job_type"),
            job_data.get("experience"),
            job_data.get("recruiter_name"),
            job_data.get("recruiter_profile_url"),
            job_data.get("contact_email"),
            job_data.get("delivery_channel"),
            skills_json,
            keywords_json,
            job_data.get("status", "PENDING_REVIEW"),
            job_data.get("ats_score", 92),
            job_data.get("post_date", "Recently posted"),
            job_data.get("custom_docx_path"),
            job_data.get("custom_pdf_path"),
            job_data.get("custom_preview_path"),
            job_data.get("email_subject"),
            job_data.get("email_body"),
            job_data.get("linkedin_dm_text"),
            now,
            now
        ))
        job_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return job_id

def get_job(job_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["extracted_skills"] = json.loads(d.get("extracted_skills") or "[]")
        d["modified_keywords"] = json.loads(d.get("modified_keywords") or "[]")
        return d
    return None

def get_all_jobs():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["extracted_skills"] = json.loads(d.get("extracted_skills") or "[]")
        d["modified_keywords"] = json.loads(d.get("modified_keywords") or "[]")
        result.append(d)
    return result

def update_job_status(job_id: int, status: str, extra: dict = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    if extra:
        set_clauses = ["status = ?", "updated_at = ?"]
        values = [status, now]
        for k, v in extra.items():
            set_clauses.append(f"{k} = ?")
            values.append(v)
        values.append(job_id)
        cursor.execute(f"UPDATE jobs SET {', '.join(set_clauses)} WHERE id = ?", tuple(values))
    else:
        cursor.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (status, now, job_id))
    conn.commit()
    conn.close()

def delete_job(job_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT custom_docx_path, custom_pdf_path, custom_preview_path FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if row:
        for path in [row["custom_docx_path"], row["custom_pdf_path"], row["custom_preview_path"]]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if row["custom_docx_path"] and "job_" in row["custom_docx_path"]:
            job_dir = os.path.dirname(row["custom_docx_path"])
            if os.path.exists(job_dir):
                import shutil
                shutil.rmtree(job_dir, ignore_errors=True)
    cursor.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return True

def schedule_job_in_db(job_id: int, scheduled_at: str, draft_id: str = None, recipient_email: str = None, subject: str = None, body: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        UPDATE jobs SET
            status = 'SCHEDULED',
            scheduled_at = ?,
            gmail_draft_id = COALESCE(?, gmail_draft_id),
            contact_email = COALESCE(?, contact_email),
            email_subject = COALESCE(?, email_subject),
            email_body = COALESCE(?, email_body),
            updated_at = ?
        WHERE id = ?
    """, (scheduled_at, draft_id, recipient_email, subject, body, now, job_id))
    conn.commit()
    conn.close()

def get_due_scheduled_jobs():
    """Retrieve all jobs marked as SCHEDULED whose scheduled_at is less than or equal to now."""
    conn = get_connection()
    cursor = conn.cursor()
    now_local = datetime.now().isoformat()
    now_utc = datetime.utcnow().isoformat()
    cursor.execute("""
        SELECT * FROM jobs 
        WHERE status = 'SCHEDULED' 
          AND (scheduled_at <= ? OR scheduled_at <= ?)
    """, (now_local, now_utc))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["extracted_skills"] = json.loads(d.get("extracted_skills") or "[]")
        d["modified_keywords"] = json.loads(d.get("modified_keywords") or "[]")
        result.append(d)
    return result

def mark_scheduled_sent(job_id: int, message_id: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    cursor.execute("""
        UPDATE jobs SET
            status = 'SENT',
            sent_at = ?,
            gmail_message_id = COALESCE(?, gmail_message_id),
            updated_at = ?
        WHERE id = ?
    """, (now, message_id, now, job_id))
    conn.commit()
    conn.close()
