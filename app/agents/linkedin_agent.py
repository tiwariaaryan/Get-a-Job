import re
import json
import requests
from typing import Dict, Any, List, Optional
from ..llm_client import GeminiClient

class LinkedInAgent:
    """Agent for parsing, extracting, and understanding LinkedIn job postings using Gemini LLM."""

    def __init__(self, llm_client: Optional[GeminiClient] = None):
        self.llm = llm_client or GeminiClient()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def scrape_post(self, url: str, raw_text: str = None, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
        """Fetch and extract job details from LinkedIn URL or provided raw text."""
        clean_url = url.strip() if url else ""
        html_content = raw_text or ""
        
        if not html_content and clean_url:
            try:
                resp = requests.get(clean_url, headers=self.headers, timeout=12)
                if resp.status_code == 200:
                    html_content = resp.text
            except Exception as e:
                print(f"[LinkedInAgent] Request error: {e}")

        # Attempt extraction via Gemini LLM first
        extracted = self._extract_via_llm(clean_url, html_content, model=model)
        if not extracted:
            # Fallback to heuristic parser
            extracted = self._parse_content(clean_url, html_content)
            
        return extracted

    def _extract_via_llm(self, url: str, content: str, model: str = "gemini-2.5-flash") -> Optional[Dict[str, Any]]:
        """Use Gemini to extract structured job intelligence."""
        if not content or len(content.strip()) < 20:
            return None

        prompt = f"""
You are an expert technical recruiter analyzing a LinkedIn job post.
Analyze the following post text and extract structured job intelligence:

Post Text:
\"\"\"
{content[:4000]}
\"\"\"

Extract and return a JSON object with EXACTLY these keys:
- "company_name": Name of the hiring company (or "Hiring Company")
- "role_title": The exact job title (e.g. "GenAI Engineer", "Lead AI Engineer")
- "location": Location string (e.g. "Noida, India", "Riyadh, Saudi Arabia", "Dubai, UAE", "Remote")
- "job_type": "Full-Time", "Freelance", "Contract", or "Part-Time"
- "experience": Required experience string (e.g. "0–1 Year", "3+ Years")
- "recruiter_name": Name of the recruiter or author (or "Hiring Team")
- "post_date": When the post was published (e.g. "5 hours ago", "2 days ago", or "Nov 19, 2026")
- "contact_email": Contact email found in post, or empty string "" if none found
- "extracted_skills": List of 5-8 top technical skills mentioned (e.g. ["Generative AI", "Python", "LLMs", "FastAPI"])
- "linkedin_dm_text": A concise, high-converting 3-sentence outreach note for Aaryan Tiwari (Lead GenAI Engineer, 5+ yrs exp, tiwariaaryan.github.io) asking to connect.
"""
        try:
            data = self.llm.generate_json(prompt, model=model)
            if data and data.get("company_name"):
                company = data.get("company_name", "Hiring Company")
                email = data.get("contact_email", "")
                
                # If no email found in post, suggest company domain pattern
                delivery_channel = "EMAIL" if email else "LINKEDIN_DM"
                if not email and company:
                    slug = re.sub(r'[^a-zA-Z0-9]', '', company.lower())
                    suggested_email = f"careers@{slug}.com"
                    delivery_channel = "BOTH"
                else:
                    suggested_email = email

                data["linkedin_url"] = url
                data["recruiter_profile_url"] = url
                data["contact_email"] = suggested_email or ""
                data["delivery_channel"] = delivery_channel
                data["raw_text"] = content
                return data
        except Exception as e:
            print(f"[LinkedInAgent] LLM extraction fallback due to: {e}")
            return None

    def _parse_content(self, url: str, html: str) -> Dict[str, Any]:
        """Heuristic fallback extraction from HTML / text."""
        title = ""
        description = ""
        og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.I)
        og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html, re.I)
        
        if og_title:
            title = og_title.group(1).replace("&amp;", "&")
        if og_desc:
            description = og_desc.group(1).replace("&amp;", "&")
            
        full_text = f"{title}\n{description}"
        if not full_text.strip() and html:
            full_text = re.sub(r'<[^>]+>', ' ', html)

        email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
        emails = re.findall(email_pattern, full_text)
        ignored = {"example@example.com", "user@domain.com"}
        valid_emails = [e for e in emails if e.lower() not in ignored and not e.endswith((".png", ".jpg"))]
        contact_email = valid_emails[0] if valid_emails else None

        company_name = "Hiring Company"
        if "Algomindz Solutions" in full_text:
            company_name = "Algomindz Solutions"
        else:
            comp_match = re.search(r'([A-Z][a-zA-Z0-9\s&]{2,30}?(?:Solutions|Technologies|Tech|Pvt|Ltd|Inc|LLC|Corporation|Systems|Labs|Software|Studio))\b', full_text)
            if comp_match:
                company_name = comp_match.group(1).strip()

        role_title = "GenAI / AI Application Engineer"
        role_match = re.search(r'(?:WE\'RE HIRING\s*\|\s*|hiring\s*[:\|–-]?\s*)([A-Za-z0-9\s\/\+\–-]+?)(?:\s*–|\s*\||\s*at|\s*\n|\.|$)', full_text, re.I)
        if role_match and len(role_match.group(1).strip()) > 3:
            role_title = role_match.group(1).strip()

        location = "Flexible / Remote"
        loc_match = re.search(r'(?:📍\s*(?:Location)?\s*[:–-]?\s*|Location\s*[:–-]?\s*)([A-Za-z\s,]+)', full_text, re.I)
        if loc_match:
            cand = loc_match.group(1).strip().split("\n")[0].strip()
            if cand and len(cand) < 40 and not cand.lower().startswith("location"):
                location = cand
        if "noida" in full_text.lower() and (location == "Flexible / Remote" or "location" in location.lower()):
            location = "Noida, India"
        elif any(k in full_text.lower() for k in ["saudi", "riyadh", "jeddah"]):
            location = "Saudi Arabia"
        elif any(k in full_text.lower() for k in ["uae", "dubai", "abu dhabi"]):
            location = "UAE"

        job_type = "Full-Time"
        if re.search(r'freelanc(?:er|ing|e)', full_text, re.I):
            job_type = "Freelance"

        experience = "0–1 Year" if "0–1" in full_text or "0-1" in full_text else "1-3 Years"
        extracted_skills = ["Generative AI", "Python", "LLMs", "FastAPI", "Prompt Engineering"]

        # Extract publication / post date
        post_date = "Recently posted"
        date_match = re.search(r'([0-9]+\s*(?:hours?|hrs?|days?|weeks?|months?)\s*ago)', full_text, re.I)
        if date_match:
            post_date = date_match.group(1).strip()
        elif "5 hours ago" in full_text:
            post_date = "5 hours ago"

        recruiter_name = "Veda Nand" if "Veda Nand" in full_text else "Hiring Team"
        delivery_channel = "EMAIL" if contact_email else "BOTH"
        suggested_email = contact_email or f"careers@{re.sub(r'[^a-zA-Z0-9]', '', company_name.lower())}.com"

        dm_text = (
            f"Hi {recruiter_name.split()[0]},\n\n"
            f"I came across your post regarding the {role_title} opportunity at {company_name}. "
            f"With 5+ years of experience in Generative AI, Python & LLMs and architecting agentic workflows, "
            f"I have delivered production GenAI platforms and scalable AI systems.\n\n"
            f"My CV and portfolio (tiwariaaryan.github.io) are ready. I would welcome the chance to connect!\n\n"
            f"Best regards,\nAaryan Tiwari"
        )

        return {
            "linkedin_url": url,
            "company_name": company_name,
            "role_title": role_title,
            "location": location,
            "post_date": post_date,
            "job_type": job_type,
            "experience": experience,
            "recruiter_name": recruiter_name,
            "recruiter_profile_url": url,
            "contact_email": suggested_email,
            "delivery_channel": delivery_channel,
            "extracted_skills": extracted_skills,
            "linkedin_dm_text": dm_text,
            "raw_text": full_text
        }
