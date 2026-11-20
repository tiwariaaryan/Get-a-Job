import os
import subprocess
import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from typing import List, Dict, Any, Tuple
from xhtml2pdf import pisa
from PIL import Image

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEMPLATE_DOCX = os.path.join(WORKSPACE_ROOT, "Resume", "Aaryan_Gen_Ai_Resume_Template.docx")
BASE_RESUME_DOCX = os.path.join(WORKSPACE_ROOT, "Resume", "Aaryan_Resume.docx")
GENERATED_DIR = os.path.join(WORKSPACE_ROOT, "generated_resumes")

class ResumeAgent:
    """Agent for tailoring dynamic ATS keywords using Aaryan_Gen_Ai_Resume_Template.docx,
    compiling full-height 2-page documents named 'Aaryan Gen Ai Resume', and calculating ATS score."""

    def __init__(self, template_docx_path: str = TEMPLATE_DOCX):
        if not os.path.exists(template_docx_path):
            template_docx_path = BASE_RESUME_DOCX
        self.template_docx_path = template_docx_path
        os.makedirs(GENERATED_DIR, exist_ok=True)

    def _apply_blue_boxes_to_paragraph(self, paragraph, items: List[str]):
        """Format paragraph with individual executive blue boxes (#3A6799) with white text and clean separation."""
        p_elem = paragraph._element
        for r in list(p_elem.xpath('./w:r')):
            p_elem.remove(r)

        for idx, item in enumerate(items):
            item_clean = item.strip()
            if not item_clean:
                continue

            # Keyword run inside individual blue box
            r = paragraph.add_run(f"  {item_clean}  ")
            r.font.name = "Calibri"
            r.font.bold = True
            r.font.size = Pt(10)

            # XML formatting for #3A6799 fill and #FFFFFF white text
            rPr = r._element.get_or_add_rPr()
            color_el = OxmlElement('w:color')
            color_el.set(qn('w:val'), 'FFFFFF')
            rPr.append(color_el)

            shd_el = OxmlElement('w:shd')
            shd_el.set(qn('w:val'), 'clear')
            shd_el.set(qn('w:color'), 'auto')
            shd_el.set(qn('w:fill'), '3A6799')
            rPr.append(shd_el)

            # Clean whitespace separation between boxes (no shading)
            if idx < len(items) - 1:
                sp = paragraph.add_run("   ")
                sp.font.name = "Calibri"
                sp.font.size = Pt(10)

    def tailor_resume(self, job_id: int, role_title: str, target_skills: List[str], raw_jd: str = "", exp_min: float = 0.0, exp_max: float = 8.0) -> Dict[str, Any]:
        """Modify keywords dynamically for ATS compliance, apply blue skill boxes in multiple lines, and compile full 2-page documents."""
        doc = docx.Document(self.template_docx_path)
        modified_keywords = []

        # Standard base skill inventory matching original 3 rows of 4 items
        base_core = [
            "Agentic AI", "Machine Learning", "Deep Learning", "RAG Pipelines",
            "Prompt Engineering", "NLP", "Statistical Modeling", "Data Mining",
            "LLM Orchestration", "Feature Engineering", "Data Visualization", "AI Automation"
        ]

        base_tech = [
            "Python", "LangChain", "Scikit-learn", "TensorFlow/PyTorch",
            "REST APIs", "FastAPI", "Docker", "Kubernetes",
            "SQL/MySQL", "Cloud Platforms (AWS/GCP)", "Streamlit", "Git/CI-CD"
        ]

        # Categorize target skills
        core_keywords_set = {"rag", "agent", "llm", "prompt", "nlp", "learning", "model", "eval", "vision", "genai", "generative ai", "retrieval", "vector", "ai systems"}
        
        injected_core = []
        injected_tech = []
        
        for s in (target_skills or []):
            s_clean = s.strip()
            if not s_clean or len(s_clean) < 2:
                continue
            s_lower = s_clean.lower()
            if any(k in s_lower for k in core_keywords_set):
                if s_clean not in base_core and s_clean not in injected_core:
                    injected_core.append(s_clean)
            else:
                if s_clean not in base_tech and s_clean not in injected_tech:
                    injected_tech.append(s_clean)

        # Build dynamic skill lists (top ATS injected at the start, maintaining 12 total items in 3 distinct rows of 4)
        final_core = list(base_core)
        for s in injected_core[:3]:
            if s not in final_core:
                final_core.insert(0, s)
                modified_keywords.append({"section": "Core Expertise", "new": s, "type": "ATS Skill Added"})

        final_tech = list(base_tech)
        for s in injected_tech[:3]:
            if s not in final_tech:
                final_tech.insert(0, s)
                modified_keywords.append({"section": "Technical Skills", "new": s, "type": "ATS Skill Added"})

        # Group skills strictly into 3 multiple lines (4 items per line) matching original resume
        core_rows = [
            final_core[0:4],
            final_core[4:8],
            final_core[8:12]
        ]
        tech_rows = [
            final_tech[0:4],
            final_tech[4:8],
            final_tech[8:12]
        ]

        summary_text = ""

        # Update DOCX paragraphs
        for i, p in enumerate(doc.paragraphs):
            text_upper = p.text.upper()

            # Format 3 multiple rows of CORE EXPERTISE
            if "CORE EXPERTISE" in text_upper:
                for row_idx, row_items in enumerate(core_rows):
                    target_p_idx = i + 1 + row_idx
                    if target_p_idx < len(doc.paragraphs):
                        self._apply_blue_boxes_to_paragraph(doc.paragraphs[target_p_idx], row_items)

            # Format 3 multiple rows of TECHNICAL SKILLS
            if "TECHNICAL SKILLS" in text_upper:
                for row_idx, row_items in enumerate(tech_rows):
                    target_p_idx = i + 1 + row_idx
                    if target_p_idx < len(doc.paragraphs):
                        self._apply_blue_boxes_to_paragraph(doc.paragraphs[target_p_idx], row_items)

            # Professional Summary block
            if "PROFESSIONAL SUMMARY" in text_upper and i + 1 < len(doc.paragraphs):
                sum_p = doc.paragraphs[i + 1]
                orig_summary = sum_p.text
                if role_title and "Lead" not in role_title:
                    aligned_summary = orig_summary.replace("Lead GenAI Engineer", f"Lead GenAI & {role_title}")
                    sum_p.text = aligned_summary
                    summary_text = aligned_summary
                    modified_keywords.append({"section": "Professional Summary", "old": "Lead GenAI Engineer", "new": f"Lead GenAI & {role_title}"})
                else:
                    summary_text = orig_summary

        # Per-job directory ensuring the file is literally named 'Aaryan Gen Ai Resume'
        job_dir = os.path.join(GENERATED_DIR, f"job_{job_id}")
        os.makedirs(job_dir, exist_ok=True)

        custom_docx_path = os.path.join(job_dir, "Aaryan Gen Ai Resume.docx")
        doc.save(custom_docx_path)

        # Legacy root path copy
        legacy_docx_path = os.path.join(GENERATED_DIR, f"Aaryan_Resume_Job_{job_id}.docx")
        doc.save(legacy_docx_path)

        # 2. Compile to high-fidelity full-height 2-page PDF
        custom_pdf_path = os.path.join(job_dir, "Aaryan Gen Ai Resume.pdf")
        self._compile_pixel_perfect_pdf(
            doc,
            custom_pdf_path,
            summary_text,
            core_rows=core_rows,
            tech_rows=tech_rows
        )

        # Legacy root pdf copy
        legacy_pdf_path = os.path.join(GENERATED_DIR, f"Aaryan_Resume_Job_{job_id}.pdf")
        if os.path.exists(custom_pdf_path):
            import shutil
            shutil.copyfile(custom_pdf_path, legacy_pdf_path)

        # 3. Generate high-resolution multi-page PNG preview
        preview_image_path = self._generate_png_preview(custom_pdf_path, job_id)

        # 4. Calculate ATS Match Score
        ats_score = self._calculate_ats_score(role_title, target_skills, raw_jd, doc, exp_min=exp_min, exp_max=exp_max)

        return {
            "custom_docx_path": custom_docx_path,
            "custom_pdf_path": custom_pdf_path,
            "custom_preview_path": preview_image_path,
            "modified_keywords": modified_keywords,
            "ats_score": ats_score
        }

    def _calculate_ats_score(self, role: str, target_skills: List[str], raw_jd: str, doc: docx.Document, exp_min: float = 0.0, exp_max: float = 8.0) -> int:
        """Calculate realistic, hard quality check 4-pillar ATS Match Score (45% to 94%)."""
        full_resume_text = " ".join([p.text.lower() for p in doc.paragraphs])
        
        # Pillar 1: Exact Keyword Overlap (40 points max)
        if not target_skills:
            target_skills = ["python", "generative ai", "llms", "fastapi"]
        
        matched_count = sum(1 for s in target_skills if s.lower() in full_resume_text)
        skill_ratio = matched_count / max(len(target_skills), 1)
        pillar_keywords = skill_ratio * 40.0
        
        # Pillar 2: Role Title & AI Competency Alignment (25 points max)
        role_lower = (role or "").lower()
        ai_role_keywords = ["ai", "genai", "generative ai", "llm", "machine learning", "ml", "deep learning", "nlp", "agent", "rag", "forward deployed"]
        is_ai = any(ak in role_lower for ak in ai_role_keywords) or any(ak in raw_jd.lower() for ak in ["genai", "llm", "agentic", "langchain", "prompt engineering"])
        
        if is_ai:
            clean_tokens = [t for t in re.sub(r'[^a-zA-Z]', ' ', role_lower).split() if len(t) > 2 and t not in ["senior", "lead", "engineer", "developer", "specialist", "role", "position"]]
            matching_tokens = sum(1 for t in clean_tokens if t in full_resume_text)
            if clean_tokens:
                token_ratio = matching_tokens / len(clean_tokens)
                pillar_role = 18.0 + (token_ratio * 7.0)
            else:
                pillar_role = 22.0
        else:
            pillar_role = 8.0
            
        # Pillar 3: Experience & Seniority Alignment (20 points max)
        # Candidate has 5.5 years. Target job range: 0 to 8 years.
        if exp_max > 8.0 or any(phrase in raw_jd.lower() for phrase in ["9+ years", "10+ years", "12+ years", "9 to", "10 to", "12 to"]):
            pillar_exp = 7.0
        elif exp_min <= 5.5 <= exp_max:
            pillar_exp = 20.0
        elif exp_max <= 3.0:
            pillar_exp = 18.0
        elif exp_min <= 7.0:
            pillar_exp = 17.0
        else:
            pillar_exp = 14.0
            
        # Pillar 4: Production Framework & Tooling Depth (15 points max)
        key_frameworks = ["langchain", "langgraph", "rag", "pytorch", "fastapi", "docker", "vllm", "vector database"]
        matched_frameworks = sum(1 for fw in key_frameworks if fw in full_resume_text and (fw in raw_jd.lower() or fw in " ".join(target_skills).lower()))
        pillar_tools = min(15.0, 9.0 + (matched_frameworks * 1.5))
        
        raw_total = pillar_keywords + pillar_role + pillar_exp + pillar_tools
        final_ats = int(min(max(raw_total, 45), 94))
        return final_ats

    def _compile_pixel_perfect_pdf(self, doc: docx.Document, pdf_path: str, summary_text: str, core_rows: List[List[str]] = None, tech_rows: List[List[str]] = None):
        """Compile complete 2-page PDF with multi-line skills tables and full-height Page 1 (including Introlligent & PE-AI-PLATFORM)."""
        if not core_rows:
            core_rows = [
                ["Agentic AI", "Machine Learning", "Deep Learning", "RAG Pipelines"],
                ["Prompt Engineering", "NLP", "Statistical Modeling", "Data Mining"],
                ["LLM Orchestration", "Feature Engineering", "Data Visualization", "AI Automation"]
            ]
        if not tech_rows:
            tech_rows = [
                ["Python", "LangChain", "Scikit-learn", "TensorFlow/PyTorch"],
                ["REST APIs", "FastAPI", "Docker", "Kubernetes"],
                ["SQL/MySQL", "Cloud Platforms (AWS/GCP)", "Streamlit", "Git/CI-CD"]
            ]

        def make_table_html(rows):
            html = '<table class="skills-table" cellpadding="0" cellspacing="0">'
            for r in rows:
                html += '<tr>'
                for item in r:
                    html += f'<td><div class="skill-badge">{item}</div></td>'
                html += '</tr>'
            html += '</table>'
            return html

        core_table_html = make_table_html(core_rows)
        tech_table_html = make_table_html(tech_rows)

        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
    @page {{
        size: letter portrait;
        margin: 24pt 36pt 24pt 36pt;
    }}
    body {{
        font-family: Calibri, 'Segoe UI', Arial, sans-serif;
        font-size: 9.8pt;
        line-height: 1.25;
        color: #000000;
    }}
    .header-box {{
        text-align: center;
        margin-bottom: 8pt;
    }}
    .header-name {{
        font-size: 26pt;
        font-weight: bold;
        color: #000000;
        margin-bottom: 2pt;
        line-height: 1.05;
    }}
    .header-title {{
        font-size: 12.5pt;
        color: #1F4E79;
        margin-bottom: 3pt;
    }}
    .header-contact {{
        font-size: 9.5pt;
        color: #222222;
    }}
    .section-title {{
        font-size: 13.5pt;
        font-weight: bold;
        color: #1F4E79;
        text-transform: uppercase;
        margin-top: 8pt;
        margin-bottom: 3pt;
        letter-spacing: 0.2px;
    }}
    .summary-body {{
        font-size: 9.8pt;
        text-align: justify;
        margin-bottom: 6pt;
        line-height: 1.28;
    }}
    .skills-table {{
        width: 100%;
        margin-bottom: 5pt;
    }}
    .skills-table td {{
        width: 25%;
        padding: 2pt 3pt;
        vertical-align: middle;
    }}
    .skill-badge {{
        background-color: #3A6799;
        color: #FFFFFF;
        font-size: 8.8pt;
        font-weight: bold;
        text-align: center;
        padding: 3pt 4pt;
        border-radius: 3px;
    }}
    .job-header {{
        font-size: 11pt;
        font-weight: bold;
        color: #000000;
        margin-top: 6pt;
        margin-bottom: 1pt;
    }}
    .job-sub {{
        font-size: 9.2pt;
        color: #444444;
        margin-bottom: 3pt;
    }}
    ul.bullet-list {{
        margin: 0 0 5pt 14pt;
        padding: 0;
    }}
    ul.bullet-list li {{
        font-size: 9.5pt;
        line-height: 1.25;
        margin-bottom: 2pt;
        color: #111111;
    }}
    .project-title {{
        font-size: 11pt;
        font-weight: bold;
        color: #1F4E79;
        margin-top: 6pt;
        margin-bottom: 2pt;
    }}
    .page-break {{
        page-break-after: always;
    }}
    /* Page 2 styling */
    .page2-job-header {{
        font-size: 12pt;
        font-weight: bold;
        color: #000000;
        margin-top: 10pt;
        margin-bottom: 2pt;
    }}
    .page2-job-sub {{
        font-size: 10pt;
        color: #444444;
        margin-bottom: 6pt;
    }}
    .page2-bullet-list {{
        margin: 0 0 10pt 16pt;
        padding: 0;
    }}
    .page2-bullet-list li {{
        font-size: 10pt;
        line-height: 1.35;
        margin-bottom: 4pt;
        color: #111111;
    }}
    .page2-project-title {{
        font-size: 12pt;
        font-weight: bold;
        color: #1F4E79;
        margin-top: 12pt;
        margin-bottom: 4pt;
    }}
    .page2-section-title {{
        font-size: 13.5pt;
        font-weight: bold;
        color: #1F4E79;
        text-transform: uppercase;
        margin-top: 14pt;
        margin-bottom: 5pt;
    }}
</style>
</head>
<body>
    <!-- PAGE 1: Fully filled down to bottom margin -->
    <div class="header-box">
        <div class="header-name">Aaryan Tiwari</div>
        <div class="header-title">Lead GenAI Engineer</div>
        <div class="header-contact">
            taaryan.official@gmail.com &nbsp;|&nbsp; Ph: 7488372401 / 9664387116 &nbsp;|&nbsp; Portfolio: tiwariaaryan.github.io
        </div>
    </div>

    <div class="section-title">PROFESSIONAL SUMMARY</div>
    <div class="summary-body">
        {summary_text or "Lead GenAI Engineer with 5+ years of experience in Machine Learning, Deep Learning, Generative AI, and Data Science. Skilled in building end-to-end AI solutions using LLMs, RAG, NLP, agentic workflows, and cloud-based deployment. Proven track record of leading 20+ AI engineers and delivering scalable GenAI platforms with Claude, Gemini, FastAPI, Docker, and Kubernetes."}
    </div>

    <div class="section-title">EDUCATION</div>
    <div style="font-size: 9.8pt; margin-bottom: 5pt;">
        <strong>Bachelor’s Degree – Jaipur Engineering College and Research Center</strong><br/>
        <span style="color: #444;">2017 – 2021</span>
    </div>

    <div class="section-title">CORE EXPERTISE</div>
    {core_table_html}

    <div class="section-title">TECHNICAL SKILLS</div>
    {tech_table_html}

    <div class="section-title">PROFESSIONAL EXPERIENCE</div>
    <div class="job-header">Lead AI Engineer – Introlligent</div>
    <div class="job-sub">Oct 2024 – Present | Bengaluru, India</div>
    <ul class="bullet-list">
        <li>Leading development of enterprise AI platforms focused on Machine Learning, Deep Learning, Generative AI, and LLM-powered automation systems. Managing 20+ AI engineers.</li>
        <li>Designed AI evaluation pipelines using statistical techniques, data mining, and LLM-based scoring for response grounding and semantic validation.</li>
        <li>Built scalable FastAPI microservices for async AI processing, batch evaluations, and end-to-end AI solution deployment on cloud platforms.</li>
        <li>Architected AI infrastructure integrating Claude and Gemini APIs with enterprise systems, following software engineering best practices.</li>
        <li>Directed containerized deployment using Docker and Kubernetes for production-grade AI services.</li>
    </ul>

    <div class="project-title">PE-AI-PLATFORM</div>
    <ul class="bullet-list">
        <li><strong>MCP Orchestration Layer:</strong> Built orchestration systems exposing 23+ enterprise APIs for autonomous, end-to-end AI workflows.</li>
        <li><strong>Grounding Engine:</strong> Developed factual and semantic validation systems using NLP, statistical analysis, and Claude/Gemini APIs.</li>
        <li><strong>AI Evaluation Platform:</strong> Created LLM-as-a-Judge systems with large-scale experimentation for response evaluation and benchmarking.</li>
        <li><strong>Synthetic Data Generation:</strong> Built data generation pipelines using feature engineering and data mining for evaluation workflows.</li>
        <li><strong>QA Automation:</strong> Automated UAT test case and RTM generation using LLM-powered requirement extraction.</li>
    </ul>

    <div class="page-break"></div>

    <!-- PAGE 2: Balanced and complete -->
    <div class="page2-job-header" style="margin-top: 0;">AI/ML Engineer – Ernst &amp; Young (EY GDS)</div>
    <div class="page2-job-sub">Feb 2022 – Jul 2024</div>
    <ul class="page2-bullet-list">
        <li>Led Generative AI and Data Science initiatives focused on LLM applications, NLP, ML model development, and workflow optimization.</li>
        <li>Designed RAG-based AI applications using LangChain, vector databases, and enterprise retrieval systems.</li>
        <li>Developed scalable AI services integrating ML models, deep learning, and data analysis pipelines for enterprise automation.</li>
    </ul>

    <div class="page2-project-title">Key GenAI Projects</div>
    <ul class="page2-bullet-list">
        <li><strong>Text-to-SQL:</strong> Built LLM-powered NLP solution converting natural language to SQL using Gemini APIs with data mining techniques.</li>
        <li><strong>PDF Data Extraction:</strong> Developed pipelines using Gemini models and text mining to extract structured data from PDFs at scale.</li>
        <li><strong>GenAI POCs:</strong> Built AI chat systems using RAG, image analysis using CNN, and similarity search with deep learning embeddings.</li>
    </ul>

    <div class="page2-job-header">Associate Software Developer – Aapna Infotech Pvt Ltd</div>
    <div class="page2-job-sub">Apr 2021 – Feb 2022</div>
    <ul class="page2-bullet-list">
        <li>Worked on enterprise workflow management systems, backend automation services, REST API integrations, and data-driven application development.</li>
    </ul>

    <div class="page2-section-title">INTERESTS</div>
    <div style="font-size: 10.5pt; color: #222222; line-height: 1.5; margin-top: 6pt;">
        Chess &bull; Writing &bull; AI/ML Research &bull; System Design &bull; Emerging AI Architectures &bull; Open Source Contributions
    </div>
</body>
</html>
"""

        with open(pdf_path, "wb") as f_out:
            pisa.CreatePDF(html_content, dest=f_out)

    def _generate_png_preview(self, pdf_path: str, job_id: int) -> str:
        """Convert all pages of PDF to PNG and stitch vertically into a crisp 2-page preview image."""
        job_dir = os.path.dirname(pdf_path)
        output_prefix = os.path.join(job_dir, "Aaryan Gen Ai Resume_preview")
        combined_path = f"{output_prefix}.png"
        page1_path = f"{output_prefix}-1.png"
        page2_path = f"{output_prefix}-2.png"

        legacy_prefix = os.path.join(GENERATED_DIR, f"Aaryan_Resume_Job_{job_id}_preview")

        try:
            subprocess.run([
                "pdftoppm",
                "-png",
                "-r", "150",
                pdf_path,
                output_prefix
            ], check=True, timeout=12)

            pages_to_stitch = []
            if os.path.exists(page1_path):
                pages_to_stitch.append(Image.open(page1_path))
            if os.path.exists(page2_path):
                pages_to_stitch.append(Image.open(page2_path))

            if len(pages_to_stitch) > 1:
                gap = 24
                total_w = max(p.width for p in pages_to_stitch)
                total_h = sum(p.height for p in pages_to_stitch) + gap * (len(pages_to_stitch) - 1)
                combined = Image.new("RGB", (total_w, total_h), (226, 232, 240))
                curr_y = 0
                for p in pages_to_stitch:
                    offset_x = (total_w - p.width) // 2
                    combined.paste(p, (offset_x, curr_y))
                    curr_y += p.height + gap
                combined.save(combined_path)
                combined.save(f"{legacy_prefix}.png")
                combined.save(f"{legacy_prefix}-1.png")
                return combined_path
            elif len(pages_to_stitch) == 1:
                return page1_path
        except Exception as e:
            print(f"[ResumeAgent] pdftoppm preview generation failed: {e}")
        return page1_path if os.path.exists(page1_path) else ""
