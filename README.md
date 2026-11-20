# JobFlow AI – Multi-Agent LinkedIn Application & ATS Pipeline

An autonomous multi-agent system designed to ingest LinkedIn job posts, tailor your resume by 20% for ATS compliance (Skills & Summary), draft customized cold emails & LinkedIn InMail notes, and manage applications and HR replies via Gmail.

---

### How to Run (1-Click)

In Finder, simply **double-click**:
👉 **`start_app.command`**

That is it! It automatically:
1. Boots the complete application (FastAPI backend + interactive dashboard).
2. Connects all agents (LinkedIn, Resume ATS, Outreach Email & Tracking).
3. Opens the unified dashboard in your default browser at **http://localhost:8085**.

To stop the application at any time, simply press **Ctrl + C** in the Terminal window or close it.

---

### Key Information
* **Connected Gmail:** taaryan.official@gmail.com
* **Base Resume:** Resume/Aaryan_Resume.docx
* **LLM Engine:** Gemini 3.5 Flash (with automatic 3.5-lite and 2.5-flash fallback)
* **API Quota Management:** Each agent has its own dedicated API key to prevent rate limit exhaustion.
