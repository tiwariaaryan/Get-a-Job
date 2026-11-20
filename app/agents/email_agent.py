import subprocess
import json
import os
import re
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, List
from ..llm_client import GeminiClient

CARRIER_LABEL_NAME = "AI Carrier"
os.environ["AGY_ACCOUNT"] = "taaryan.official@gmail.com"

def get_gmail_bin() -> str:
    which_bin = shutil.which("gmail")
    if which_bin:
        return which_bin
    fallback = "/Users/aaryantiwari/.gemini/antigravity/bin/gmail"
    if os.path.exists(fallback):
        return fallback
    return "gmail"

GMAIL_BIN = get_gmail_bin()

def enforce_strict_email_constraints(body: str, recruiter: str = "Hiring Team", role: str = "GenAI Engineer", company: str = "the team") -> str:
    sig = (
        "Sincerely,\n"
        "Aaryan Tiwari\n"
        "Lead GenAI Engineer | +91 7488372401 | taaryan.official@gmail.com\n"
        "Portfolio: https://tiwariaaryan.github.io"
    )

    sig_markers = [
        "sincerely", "best regards", "warm regards", "regards",
        "thanks and regards", "thank you", "respectfully"
    ]
    
    lines = body.strip().split("\n")
    body_lines = []
    greeting = ""

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if not greeting and (lower.startswith("dear ") or lower.startswith("hi ") or lower.startswith("hello ") or lower.startswith("greetings")):
            greeting = stripped
            continue
        if any(lower.startswith(marker) for marker in sig_markers):
            break
        body_lines.append(line)

    if not greeting:
        first_name = recruiter.split()[0] if recruiter and recruiter != "Hiring Team" else "Hiring Manager"
        greeting = f"Dear {first_name},"

    raw_paras = [p.strip() for p in "\n".join(body_lines).split("\n\n") if p.strip()]
    selected_paras = raw_paras[:3]

    if not selected_paras:
        selected_paras = [
            f"I am writing to express my strong interest in joining {company} as a {role}. With deep experience in Generative AI, I am very eager to contribute to your engineering team.",
            "My core expertise includes Python, LLMs, scalable microservices, and enterprise RAG pipelines. I focus on deploying resilient, high-performance AI solutions that align with business goals.",
            f"I have attached my resume for your consideration. I would welcome the opportunity to discuss how my technical background can support {company}'s engineering objectives."
        ]

    constrained_paras = []
    for p in selected_paras:
        words = p.split()
        if len(words) > 30:
            truncated = " ".join(words[:30])
            if not truncated.endswith((".", "!", "?")):
                truncated += "."
            constrained_paras.append(truncated)
        else:
            constrained_paras.append(p)

    final_email = f"{greeting}\n\n" + "\n\n".join(constrained_paras) + f"\n\n{sig}"
    return final_email.strip()

class EmailAgent:
    def __init__(self, sender_email: str = "taaryan.official@gmail.com", llm_client: Optional[GeminiClient] = None):
        self.sender_email = sender_email
        self.llm = llm_client or GeminiClient()
        self._carrier_label_id = "Label_1"

    def get_or_create_carrier_label_id(self) -> str:
        try:
            res = subprocess.run([GMAIL_BIN, "readonly", "labels", "--json"], capture_output=True, text=True, env=os.environ.copy())
            if res.returncode == 0:
                raw = res.stdout.strip()
                if "[" in raw:
                    labels = json.loads(raw[raw.find("["):])
                    for l in labels:
                        if l.get("name", "").lower() == CARRIER_LABEL_NAME.lower():
                            self._carrier_label_id = l.get("id")
                            return self._carrier_label_id
        except Exception as e:
            print(f"[EmailAgent] Error checking labels: {e}")

        try:
            create_res = subprocess.run([
                GMAIL_BIN, "mutate", "create-label", CARRIER_LABEL_NAME,
                "--bg-color", "blue", "--text-color", "white", "--json"
            ], capture_output=True, text=True, env=os.environ.copy())
            if create_res.returncode == 0:
                raw_c = create_res.stdout.strip()
                match = re.search(r"ID:\s*([A-Za-z0-9_]+)", raw_c)
                if match:
                    self._carrier_label_id = match.group(1)
                    return self._carrier_label_id
        except Exception as e:
            print(f"[EmailAgent] Error creating label: {e}")

        return self._carrier_label_id

    def tag_as_carrier_item(self, message_id: str = None, thread_id: str = None):
        label_id = self.get_or_create_carrier_label_id()
        if not label_id:
            return

        if thread_id:
            try:
                subprocess.run([
                    GMAIL_BIN, "mutate", "thread-modify", thread_id, "--add", label_id
                ], capture_output=True, text=True, env=os.environ.copy())
                print(f"[EmailAgent] Thread {thread_id} labeled as '{CARRIER_LABEL_NAME}'.")
            except Exception as e:
                print(f"[EmailAgent] Error labeling thread: {e}")

        if message_id:
            try:
                subprocess.run([
                    GMAIL_BIN, "mutate", "add-label", message_id, label_id
                ], capture_output=True, text=True, env=os.environ.copy())
                print(f"[EmailAgent] Message {message_id} labeled as '{CARRIER_LABEL_NAME}'.")
            except Exception as e:
                print(f"[EmailAgent] Error labeling message: {e}")

    def draft_email(self, job_data: Dict[str, Any], model: str = "gemini-2.5-flash") -> Dict[str, str]:
        role = job_data.get("role_title", "GenAI Engineer")
        company = job_data.get("company_name", "the team")
        recruiter = job_data.get("recruiter_name", "Hiring Team")
        skills = job_data.get("extracted_skills", [])
        top_skills = ", ".join(skills[:4]) if skills else "Generative AI, Python, LLMs & Multi-Agent Systems"

        prompt = (
            "Write a natural, polite, and highly professional job application email from Aaryan Tiwari to " + str(recruiter) + " at " + str(company) + " for the position of " + str(role) + ".\n\n"
            "STRICT CONSTRAINTS (MANDATORY):\n"
            "1. Exactly 3 body paragraphs (excluding the greeting and the sign-off).\n"
            "2. Each paragraph must be MAXIMUM 30 words (strictly enforced). Be concise and straight to the point.\n"
            "3. Tone: Polite, sincere, official, and professional corporate tone.\n"
            "4. DO NOT use words like \x27tailored resume\x27 or \x27adapted keywords\x27. Simply say \x27I have attached my resume for your consideration\x27.\n"
            "5. Paragraph 1: Express strong interest and genuine willingness to join " + str(company) + " as a " + str(role) + ".\n"
            "6. Paragraph 2: Highlight my core technical expertise and hands-on skills in " + str(top_skills) + " matching your job description.\n"
            "7. Paragraph 3: Politely ask to look into the attached resume and express readiness to discuss how to contribute.\n"
            "8. Sign-off:\n"
            "Sincerely,\n"
            "Aaryan Tiwari\n"
            "Lead GenAI Engineer | +91 7488372401 | taaryan.official@gmail.com\n"
            "Portfolio: https://tiwariaaryan.github.io\n\n"
            "Return ONLY a JSON object with keys subject and body."
        )

        try:
            res = self.llm.generate_json(prompt, model=model)
            if res and res.get("subject") and res.get("body"):
                raw_body = res["body"].strip()
                constrained_body = enforce_strict_email_constraints(raw_body, recruiter=recruiter, role=role, company=company)
                return {
                    "subject": res["subject"].strip(),
                    "body": constrained_body
                }
        except Exception as e:
            print(f"[EmailAgent] LLM email drafting fallback due to: {e}")

        first_name = recruiter.split()[0] if recruiter and recruiter != "Hiring Team" else "Hiring Manager"
        subject = f"Application: {role} - Aaryan Tiwari"
        
        fallback_body = (
            f"Dear {first_name},\n\n"
            f"I am writing to express my strong interest in joining {company} as a {role}. "
            f"With over 5 years of specialized experience in AI engineering, I am eager to contribute.\n\n"
            f"My core expertise aligns directly with your requirements in {top_skills}. "
            f"I focus on delivering reliable AI solutions that drive real business impact.\n\n"
            f"I have attached my resume for your consideration. "
            f"I would appreciate the opportunity to discuss how my skills and background can support {company}'s upcoming goals.\n\n"
            f"Sincerely,\n"
            f"Aaryan Tiwari\n"
            f"Lead GenAI Engineer | +91 7488372401 | taaryan.official@gmail.com\n"
            f"Portfolio: https://tiwariaaryan.github.io"
        )
        
        constrained_fallback = enforce_strict_email_constraints(fallback_body, recruiter=recruiter, role=role, company=company)
        return {"subject": subject, "body": constrained_fallback}

    def send_via_smtp(self, to_email: str, subject: str, body: str, attachment_pdf_path: str = None) -> Dict[str, Any]:
        """Send application email with attached PDF directly via Gmail SMTP using Google App Password."""
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        app_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
        smtp_user = os.environ.get("GMAIL_SMTP_USER", self.sender_email).strip()

        if not app_password:
            return {"success": False, "error": "No GMAIL_APP_PASSWORD configured in .env"}

        msg = MIMEMultipart()
        msg["From"] = f"Aaryan Tiwari <{smtp_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        # Attach text body
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Attach PDF if present
        if attachment_pdf_path and os.path.exists(attachment_pdf_path):
            with open(attachment_pdf_path, "rb") as f:
                part = MIMEBase("application", "pdf")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            fname = os.path.basename(attachment_pdf_path)
            part.add_header("Content-Disposition", f"attachment; filename=\"{fname}\"")
            msg.attach(part)

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
            server.starttls()
            server.login(smtp_user, app_password)
            server.sendmail(smtp_user, [to_email], msg.as_string())
            server.quit()
            
            gen_id = f"smtp_{int(datetime.now().timestamp())}"
            return {
                "success": True,
                "message_id": gen_id,
                "thread_id": gen_id,
                "delivery_channel": "GMAIL_SMTP"
            }
        except Exception as e:
            return {"success": False, "error": f"SMTP dispatch failed: {e}"}

    def send_email(self, to_email: str, subject: str, body: str, attachment_pdf_path: str) -> Dict[str, Any]:
        if not to_email:
            return {"success": False, "error": "No recipient email provided."}
        if not os.path.exists(attachment_pdf_path):
            return {"success": False, "error": f"Attachment file not found: {attachment_pdf_path}"}

        # 1. Prefer direct Gmail SMTP if App Password is set (fast, reliable, bypasses OAuth 403)
        if os.environ.get("GMAIL_APP_PASSWORD"):
            smtp_res = self.send_via_smtp(to_email, subject, body, attachment_pdf_path)
            if smtp_res.get("success"):
                return smtp_res
            print(f"[EmailAgent] SMTP dispatch fallback notice: {smtp_res.get('error')}")

        # 2. Fallback to Gmail CLI
        cmd = [
            GMAIL_BIN,
            "mutate",
            "send-with-attachment",
            "--to", to_email,
            "--subject", subject,
            "--body", body,
            "--file", attachment_pdf_path,
            "--json"
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, env=os.environ.copy())
            output = res.stdout.strip()
            msg_id = ""
            thread_id = ""
            try:
                data = json.loads(output)
                msg_id = data.get("id") or data.get("messageId") or ""
                thread_id = data.get("threadId") or ""
            except Exception:
                m = re.search(r"ID=([^\s]+)", output)
                msg_id = m.group(1) if m else "sent"

            if msg_id or thread_id:
                self.tag_as_carrier_item(message_id=msg_id, thread_id=thread_id)

            return {
                "success": True,
                "message_id": msg_id,
                "thread_id": thread_id,
                "carrier_label": CARRIER_LABEL_NAME,
                "raw_output": output
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": e.stderr or str(e)
            }

    def create_draft(self, to_email: str, subject: str, body: str, attachment_pdf_path: str = None) -> Dict[str, Any]:
        if not to_email:
            return {"success": False, "error": "No recipient email provided."}

        cmd = [
            GMAIL_BIN,
            "mutate",
            "create-draft",
            "--to", to_email,
            "--subject", subject,
            "--body", body,
            "--json"
        ]
        if attachment_pdf_path and os.path.exists(attachment_pdf_path):
            cmd.extend(["--file", attachment_pdf_path])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, env=os.environ.copy())
            output = res.stdout.strip()
            draft_id = ""
            thread_id = ""
            msg_id = ""

            try:
                data = json.loads(output)
                draft_id = data.get("id") or data.get("draftId") or ""
                msg_obj = data.get("message", {})
                thread_id = msg_obj.get("threadId") or data.get("threadId") or ""
                msg_id = msg_obj.get("id") or ""
            except Exception:
                pass

            if not draft_id:
                m = re.search(r"ID=([^\s]+)", output)
                if m:
                    draft_id = m.group(1)

            if draft_id and (not thread_id or not msg_id):
                try:
                    d_res = subprocess.run([GMAIL_BIN, "readonly", "get-draft", draft_id, "--json"], capture_output=True, text=True, env=os.environ.copy())
                    if d_res.returncode == 0:
                        d_data = json.loads(d_res.stdout)
                        msg_obj = d_data.get("message", {})
                        thread_id = msg_obj.get("threadId") or thread_id
                        msg_id = msg_obj.get("id") or msg_id
                except Exception as e:
                    print(f"[EmailAgent] Error fetching draft details for {draft_id}: {e}")

            if msg_id or thread_id:
                self.tag_as_carrier_item(message_id=msg_id, thread_id=thread_id)

            return {"success": True, "draft_id": draft_id, "thread_id": thread_id, "output": output}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": e.stderr or str(e)}

    def check_replies_in_carrier_folder(self) -> List[Dict[str, Any]]:
        cmd = [
            GMAIL_BIN,
            "readonly",
            "search",
            f"label:\"{CARRIER_LABEL_NAME}\" -from:me",
            "--max", "25",
            "--json"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
            if res.returncode == 0 and res.stdout.strip():
                stdout = res.stdout
                json_start = stdout.find("[")
                if json_start != -1:
                    messages = json.loads(stdout[json_start:])
                    replies = []
                    for m in messages:
                        from_email = m.get("from") or m.get("sender") or ""
                        snippet = m.get("snippet") or self._get_message_snippet(m.get("id"))
                        replies.append({
                            "message_id": m.get("id"),
                            "thread_id": m.get("threadId"),
                            "from": from_email,
                            "subject": m.get("subject"),
                            "snippet": snippet,
                            "date": m.get("date")
                        })
                    return replies
        except Exception as e:
            print(f"[EmailAgent] Error scanning AI Carrier folder: {e}")
        return []

    def check_replies(self, contact_email: str) -> Dict[str, Any]:
        if not contact_email or "@" not in contact_email:
            return {"has_reply": False, "snippet": ""}

        cmd = [
            GMAIL_BIN,
            "readonly",
            "search",
            f"from:{contact_email}",
            "--max", "3",
            "--json"
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
            if res.returncode == 0 and res.stdout.strip():
                stdout = res.stdout
                json_start = stdout.find("[")
                if json_start != -1:
                    raw_json = stdout[json_start:]
                    messages = json.loads(raw_json)
                    if messages and len(messages) > 0:
                        msg_id = messages[0].get("id")
                        snippet = self._get_message_snippet(msg_id)
                        return {
                            "has_reply": True,
                            "snippet": snippet or "Received a response from HR."
                        }
        except Exception as e:
            print(f"[EmailAgent] Error checking replies: {e}")

        return {"has_reply": False, "snippet": ""}

    def _get_message_snippet(self, msg_id: str) -> str:
        if not msg_id:
            return ""
        cmd = [GMAIL_BIN, "readonly", "get", msg_id, "--json"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
            if res.returncode == 0:
                stdout = res.stdout
                json_start = stdout.find("{")
                if json_start != -1:
                    data = json.loads(stdout[json_start:])
                    return data.get("snippet", "")
        except Exception:
            pass
        return ""


    def audit_past_month_applications(self) -> Dict[str, Any]:
        """
        Audits all past 30 days of email activity sent through the app:
        - Scans both 'AI Carrier' label and user 'inbox' for recruiter replies & bounces
        - Detects 'Address not found' delivery failures & extracts bounced recipients
        - Checks total sent applications in the past 30 days
        - Identifies duplicate applications sent to same recipient or same job role
        - Uses resilient local cache if CLI environment does not have direct access token
        """
        cache_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gmail_audit_cache.json")
        env = os.environ.copy()
        env["AGY_ACCOUNT"] = self.sender_email
        
        # Scan AI Carrier AND Inbox for bounces / replies
        search_queries = [
            f'label:"{CARRIER_LABEL_NAME}"',
            'in:inbox newer_than:30d (from:mailer-daemon OR "Address not found" OR "Delivery Status Notification")'
        ]
        
        all_raw_messages = []
        seen_msg_ids = set()
        
        for q in search_queries:
            cmd = [GMAIL_BIN, "readonly", "search", q, "--max", "50", "--json"]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, env=env)
                if res.returncode == 0 and res.stdout.strip():
                    raw = res.stdout[res.stdout.find("["):] if "[" in res.stdout else "[]"
                    batch = json.loads(raw)
                    for b in batch:
                        bid = b.get("id")
                        if bid and bid not in seen_msg_ids:
                            seen_msg_ids.add(bid)
                            all_raw_messages.append(b)
            except Exception as e:
                print(f"[EmailAgent] Notice in query '{q}': {e}")

        sent_messages = []
        incoming_replies = []
        bounces = []
        recipient_counts = {}
        role_counts = {}
        
        for m in all_raw_messages:
            msg_id = m.get("id")
            thread_id = m.get("threadId")
            if not msg_id:
                continue
                
            try:
                g_res = subprocess.run([GMAIL_BIN, "readonly", "get", msg_id, "--json"], capture_output=True, text=True, env=env)
                if g_res.returncode == 0 and "{" in g_res.stdout:
                    detail = json.loads(g_res.stdout[g_res.stdout.find("{"):])
                    headers = {h.get("name", "").lower(): h.get("value", "") for h in detail.get("payload", {}).get("headers", [])}
                    labels = detail.get("labelIds", [])
                    from_hdr = headers.get("from", "").lower()
                    to_hdr = headers.get("to", "").lower()
                    subject_hdr = headers.get("subject", "")
                    date_hdr = headers.get("date", "")
                    snippet = detail.get("snippet", "")
                    
                    # Detect Bounces / Delivery Failures (Address Not Found)
                    is_bounce = False
                    if any(term in from_hdr for term in ["mailer-daemon", "postmaster"]) or \
                       any(term in subject_hdr.lower() for term in ["delivery status", "failure", "undeliverable", "address not found"]):
                        is_bounce = True
                    elif any(term in snippet.lower() for term in ["address not found", "wasn't delivered to", "couldn't be found", "domain couldn't be found"]):
                        is_bounce = True
                        
                    if is_bounce:
                        # Extract the exact failed recipient email address
                        m_rcpt = re.search(r'(?:delivered to|domain|to)\s+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', snippet, re.I)
                        bounced_rcpt = ""
                        if m_rcpt:
                            bounced_rcpt = m_rcpt.group(1).lower()
                        else:
                            all_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', snippet)
                            valid_targets = [e.lower() for e in all_emails if not e.startswith("taaryan.") and "google" not in e and "daemon" not in e]
                            if valid_targets:
                                bounced_rcpt = valid_targets[0]
                                
                        reason = "Address not found: domain couldn't be found" if "domain" in snippet.lower() else "Delivery failure / Address not found"
                        bounces.append({
                            "message_id": msg_id,
                            "thread_id": thread_id,
                            "subject": subject_hdr,
                            "from": from_hdr,
                            "snippet": snippet,
                            "bounced_recipient": bounced_rcpt,
                            "reason": reason,
                            "date": date_hdr
                        })
                    elif "SENT" in labels or self.sender_email.lower() in from_hdr:
                        m_to = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', to_hdr)
                        clean_to = m_to.group(0).lower() if m_to else to_hdr.strip()
                        
                        sent_messages.append({
                            "message_id": msg_id,
                            "thread_id": thread_id,
                            "recipient": clean_to,
                            "subject": subject_hdr,
                            "date": date_hdr,
                            "snippet": snippet
                        })
                        if clean_to:
                            recipient_counts[clean_to] = recipient_counts.get(clean_to, 0) + 1
                        if subject_hdr:
                            norm_subj = subject_hdr.lower().replace("re:", "").strip()
                            role_counts[norm_subj] = role_counts.get(norm_subj, 0) + 1
                    else:
                        incoming_replies.append({
                            "message_id": msg_id,
                            "thread_id": thread_id,
                            "from": from_hdr,
                            "to": to_hdr,
                            "subject": subject_hdr,
                            "date": date_hdr,
                            "snippet": snippet
                        })
            except Exception as e:
                print(f"[EmailAgent] Error inspecting message {msg_id}: {e}")

        # If live scan returned 0 messages (e.g. running in webserver without injected tokens), load from persistent cache
        if len(sent_messages) == 0 and os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached = json.load(f)
                return cached
            except Exception as e:
                print(f"[EmailAgent] Error loading cache: {e}")

        duplicates = []
        for rcpt, count in recipient_counts.items():
            if count > 1 and not rcpt.startswith("taaryan."):
                duplicates.append({
                    "type": "RECIPIENT_DUPLICATE",
                    "recipient": rcpt,
                    "count": count,
                    "warning": f"Duplicate detected: {count} applications were sent to {rcpt}."
                })

        for subj, count in role_counts.items():
            if count > 1 and "application:" in subj:
                duplicates.append({
                    "type": "ROLE_DUPLICATE",
                    "subject": subj,
                    "count": count,
                    "warning": f"Duplicate detected: {count} applications sent for '{subj}'."
                })

        health_pct = "100%"
        if len(bounces) > 0 and len(sent_messages) > 0:
            pct = int(round((1 - (len(bounces) / len(sent_messages))) * 100))
            health_pct = f"{max(0, pct)}%"

        result = {
            "success": True,
            "scan_period": "Past 30 Days",
            "total_messages_scanned": len(all_raw_messages),
            "total_sent_month": len(sent_messages),
            "total_replies_detected": len(incoming_replies),
            "duplicates_count": len(duplicates),
            "duplicates_found": duplicates,
            "bounced_count": len(bounces),
            "bounced_emails": bounces,
            "health_score": health_pct,
            "sent_messages": sent_messages,
            "replies": incoming_replies,
            "summary": f"Scanned past 30 days in Gmail ({CARRIER_LABEL_NAME} & Inbox): {len(sent_messages)} sent, {len(incoming_replies)} replies, {len(duplicates)} duplicates flagged, {len(bounces)} bounces detected."
        }

        # Cache live successful scan
        if len(sent_messages) > 0:
            try:
                with open(cache_file, "w") as f:
                    json.dump(result, f, indent=2)
            except Exception:
                pass

        return result
