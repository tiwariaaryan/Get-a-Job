import subprocess
import json
import os
import re
import shutil
from typing import Dict, Any, Optional, List
from ..llm_client import GeminiClient

CARRIER_LABEL_NAME = "AI Carrier"

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
        top_skills = ", ".join(skills[:3]) if skills else "Python, LLMs & Multi-Agent Systems"

        prompt = (
            "Write a natural, polite, and highly professional job application email from Aaryan Tiwari to " + str(recruiter) + " at " + str(company) + " for the position of " + str(role) + ".\n\n"
            "STRICT CONSTRAINTS (MANDATORY):\n"
            "1. Exactly 3 body paragraphs (excluding the greeting and the sign-off).\n"
            "2. Each paragraph must be MAXIMUM 30 words (strictly enforced). Be concise and straight to the point.\n"
            "3. Tone: Polite, sincere, official, and professional corporate tone.\n"
            "4. DO NOT use words like \x27tailored resume\x27 or \x27adapted keywords\x27. Simply say \x27I have attached my resume for your consideration\x27.\n"
            "5. Paragraph 1: Express strong interest and genuine willingness to join " + str(company) + " as a " + str(role) + ".\n"
            "6. Paragraph 2: Highlight core expertise in " + str(top_skills) + " and building reliable AI solutions.\n"
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
            f"With deep GenAI experience, I am eager to contribute to your engineering team.\n\n"
            f"My core expertise includes {top_skills}, scalable microservices, and enterprise RAG pipelines. "
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

    def send_email(self, to_email: str, subject: str, body: str, attachment_pdf_path: str) -> Dict[str, Any]:
        if not to_email:
            return {"success": False, "error": "No recipient email provided."}
        if not os.path.exists(attachment_pdf_path):
            return {"success": False, "error": f"Attachment file not found: {attachment_pdf_path}"}

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
