import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

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

    # Dynamic migrations
    columns_to_add = [
        ("custom_preview_path", "TEXT"),
        ("ats_score", "INTEGER DEFAULT 85"),
        ("post_date", "TEXT"),
        ("scheduled_at", "TEXT"),
        ("gmail_draft_id", "TEXT"),
        ("gmail_thread_id", "TEXT"),
        ("company_industry", "TEXT DEFAULT 'Artificial Intelligence & Technology'"),
        ("company_overview", "TEXT"),
        ("jd_summary", "TEXT DEFAULT '[]'"),
        ("exp_min", "REAL DEFAULT 0"),
        ("exp_max", "REAL DEFAULT 8"),
        ("is_ai_role", "INTEGER DEFAULT 1"),
        ("is_exp_eligible", "INTEGER DEFAULT 1"),
        ("is_flagged", "INTEGER DEFAULT 0"),
        ("flag_reasons", "TEXT DEFAULT '[]'"),
        ("compatibility_score", "INTEGER DEFAULT 85"),
        ("duplicate_detected", "INTEGER DEFAULT 0"),
        ("duplicate_warning", "TEXT"),
        ("alternate_emails", "TEXT DEFAULT '[]'"),
        ("fetch_date", "TEXT")
    ]
    for col_name, col_def in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass
            
    conn.commit()
    conn.close()

def _deserialize_row(row_dict: dict) -> dict:
    d = dict(row_dict)
    for json_field in ["extracted_skills", "modified_keywords", "jd_summary", "flag_reasons", "alternate_emails"]:
        val = d.get(json_field)
        if isinstance(val, str):
            try:
                d[json_field] = json.loads(val or "[]")
            except Exception:
                d[json_field] = []
        elif val is None:
            d[json_field] = []
    # Boolean helpers
    d["is_ai_role"] = bool(d.get("is_ai_role", 1))
    d["is_exp_eligible"] = bool(d.get("is_exp_eligible", 1))
    d["is_flagged"] = bool(d.get("is_flagged", 0))
    d["duplicate_detected"] = bool(d.get("duplicate_detected", 0))
    return d

def check_duplicate_application(contact_email: str = None, company_name: str = None, role_title: str = None, linkedin_url: str = None, exclude_job_id: int = None) -> Tuple[bool, str]:
    """Check if an application has already been sent or drafted to this sender, company + role, or post URL."""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT id, company_name, role_title, contact_email, status, sent_at, scheduled_at, created_at FROM jobs WHERE 1=1"
    params = []
    if exclude_job_id:
        query += " AND id != ?"
        params.append(exclude_job_id)
        
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    
    email_clean = (contact_email or "").strip().lower()
    comp_clean = (company_name or "").strip().lower()
    role_clean = (role_title or "").strip().lower()
    
    for r in rows:
        row_id = r["id"]
        row_status = r["status"]
        row_comp = (r["company_name"] or "").strip().lower()
        row_role = (r["role_title"] or "").strip().lower()
        row_email = (r["contact_email"] or "").strip().lower()
        date_str = r["sent_at"] or r["scheduled_at"] or r["created_at"] or "previously"
        if len(date_str) > 10:
            date_str = date_str[:10]

        # 1. Exact email match (ignore generic career placeholders if company differs)
        if email_clean and email_clean == row_email and not email_clean.startswith("careers@"):
            status_desc = "already sent" if row_status == "SENT" else ("already scheduled" if row_status == "SCHEDULED" else "already drafted")
            return True, f"Duplicate detected: An application was {status_desc} to {email_clean} for '{r['role_title']}' at {r['company_name']} (#{row_id}) on {date_str}."

        # 2. Same company & similar role
        if comp_clean and comp_clean == row_comp and comp_clean not in ["hiring company", "company", ""]:
            if role_clean and (role_clean in row_role or row_role in role_clean):
                status_desc = "already sent" if row_status == "SENT" else ("already scheduled" if row_status == "SCHEDULED" else "already drafted")
                return True, f"Duplicate detected: Application {status_desc} for '{r['role_title']}' at {r['company_name']} (#{row_id}) on {date_str}."
                
    return False, ""

def save_job(job_data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if job exists
    cursor.execute("SELECT id FROM jobs WHERE linkedin_url = ?", (job_data["linkedin_url"],))
    row = cursor.fetchone()
    
    now = datetime.utcnow().isoformat()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    skills_json = json.dumps(job_data.get("extracted_skills", []))
    keywords_json = json.dumps(job_data.get("modified_keywords", []))
    jd_summary_json = json.dumps(job_data.get("jd_summary", []))
    flag_reasons_json = json.dumps(job_data.get("flag_reasons", []))
    alt_emails_json = json.dumps(job_data.get("alternate_emails", []))
    
    fetch_date = job_data.get("fetch_date") or today_str
    
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
            company_industry = ?,
            company_overview = ?,
            jd_summary = ?,
            exp_min = ?,
            exp_max = ?,
            is_ai_role = ?,
            is_exp_eligible = ?,
            is_flagged = ?,
            flag_reasons = ?,
            compatibility_score = ?,
            duplicate_detected = ?,
            duplicate_warning = ?,
            alternate_emails = ?,
            fetch_date = COALESCE(fetch_date, ?),
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
            job_data.get("ats_score", 85),
            job_data.get("post_date", "Recently posted"),
            job_data.get("custom_docx_path"),
            job_data.get("custom_pdf_path"),
            job_data.get("custom_preview_path"),
            job_data.get("email_subject"),
            job_data.get("email_body"),
            job_data.get("linkedin_dm_text"),
            job_data.get("company_industry", "Artificial Intelligence & Technology"),
            job_data.get("company_overview", ""),
            jd_summary_json,
            job_data.get("exp_min", 0.0),
            job_data.get("exp_max", 8.0),
            1 if job_data.get("is_ai_role", True) else 0,
            1 if job_data.get("is_exp_eligible", True) else 0,
            1 if job_data.get("is_flagged", False) else 0,
            flag_reasons_json,
            job_data.get("compatibility_score", 85),
            1 if job_data.get("duplicate_detected", False) else 0,
            job_data.get("duplicate_warning", ""),
            alt_emails_json,
            fetch_date,
            now,
            job_id
        ))
    else:
        cursor.execute("""
        INSERT INTO jobs (
            linkedin_url, company_name, role_title, location, job_type, experience,
            recruiter_name, recruiter_profile_url, contact_email, delivery_channel,
            extracted_skills, modified_keywords, status, ats_score, post_date, custom_docx_path, custom_pdf_path,
            custom_preview_path, email_subject, email_body, linkedin_dm_text,
            company_industry, company_overview, jd_summary, exp_min, exp_max,
            is_ai_role, is_exp_eligible, is_flagged, flag_reasons, compatibility_score,
            duplicate_detected, duplicate_warning, alternate_emails, fetch_date,
            created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?
        )
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
            job_data.get("ats_score", 85),
            job_data.get("post_date", "Recently posted"),
            job_data.get("custom_docx_path"),
            job_data.get("custom_pdf_path"),
            job_data.get("custom_preview_path"),
            job_data.get("email_subject"),
            job_data.get("email_body"),
            job_data.get("linkedin_dm_text"),
            job_data.get("company_industry", "Artificial Intelligence & Technology"),
            job_data.get("company_overview", ""),
            jd_summary_json,
            job_data.get("exp_min", 0.0),
            job_data.get("exp_max", 8.0),
            1 if job_data.get("is_ai_role", True) else 0,
            1 if job_data.get("is_exp_eligible", True) else 0,
            1 if job_data.get("is_flagged", False) else 0,
            flag_reasons_json,
            job_data.get("compatibility_score", 85),
            1 if job_data.get("duplicate_detected", False) else 0,
            job_data.get("duplicate_warning", ""),
            alt_emails_json,
            fetch_date,
            now,
            now
        ))
        job_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return job_id

def get_job(job_id: int) -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return _deserialize_row(row)
    return None

def get_all_jobs() -> List[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [_deserialize_row(r) for r in rows]

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

def delete_all_jobs() -> bool:
    """Clear all applications from history and remove generated files."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()
    
    # Remove files inside generated_resumes
    gen_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "generated_resumes"))
    if os.path.exists(gen_dir):
        import shutil
        for item in os.listdir(gen_dir):
            item_path = os.path.join(gen_dir, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)
                elif item != ".gitkeep":
                    os.remove(item_path)
            except Exception:
                pass
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

def get_due_scheduled_jobs() -> List[dict]:
    """Retrieve all jobs marked as SCHEDULED whose scheduled_at is <= now."""
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
    return [_deserialize_row(r) for r in rows]

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
