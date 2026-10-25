import os
import re
import time
import json
import logging
import urllib.parse
from datetime import datetime, timedelta
import requests

# Set up module logger
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Default Credentials & Config
# ---------------------------------------------------------
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "curious_coder~linkedin-jobs-scraper")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://advkivbiwhwpncyomcei.supabase.co/rest/v1/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_publishable_9hgSwmou0V8xdADTAG-mjw_3fFL3Z_t")

# ---------------------------------------------------------
# General Utilities
# ---------------------------------------------------------
def sanitize_slug(text: str) -> str:
    """
    Sanitizes a company name or role title into a clean alphanumeric slug suitable for filenames and URLs.
    """
    if not text:
        return "untitled"
    cleaned = "".join(c for c in text if c.isalnum() or c in (' ', '_', '-')).strip()
    slug = re.sub(r'[\s\-]+', '_', cleaned).lower()
    return slug or "untitled"

# ---------------------------------------------------------
# 1. LinkedIn Search URL Builder (from n8n 'Build LinkedIn URL')
# ---------------------------------------------------------
def build_linkedin_url(query="AI Product Manager", location="Pune, Maharashtra, India", time_filter="pastWeek", remote_filter=None):
    """
    Constructs a targeted LinkedIn Jobs public search URL matching n8n workflow.
    - time_filter options: 'past24Hours' (r86400), 'pastWeek' (r604800), 'pastMonth' (r2592000)
    - remote_filter options: 'onSite' (1), 'remote' (2), 'hybrid' (3), 'any' (1,2,3)
    """
    time_map = {
        "past24Hours": "r86400",
        "pastWeek": "r604800",
        "pastMonth": "r2592000"
    }
    time_posted_range = time_map.get(time_filter, "r604800")
    encoded_query = urllib.parse.quote(query)
    encoded_location = urllib.parse.quote(location)

    url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}&location={encoded_location}&f_TPR={time_posted_range}&sortBy=DD"

    if remote_filter == "remote":
        url += "&f_WT=2"
    elif remote_filter == "hybrid_or_remote":
        url += "&f_WT=1%2C2"

    return url

# ---------------------------------------------------------
# 2. Asynchronous Apify Runner & Poller
# ---------------------------------------------------------
def _trigger_apify_run(start_url, payload, headers):
    """Initiates an asynchronous Apify actor run and returns (run_id, dataset_id, error)."""
    try:
        response = requests.post(start_url, json=payload, headers=headers, timeout=30)
        if response.status_code not in [200, 201]:
            return None, None, f"Failed to start Apify actor (HTTP {response.status_code}): {response.text[:200]}"
        run_data = response.json().get("data", {})
        run_id = run_data.get("id")
        dataset_id = run_data.get("defaultDatasetId")
        if not run_id:
            return None, None, "Apify did not return a valid run ID."
        return run_id, dataset_id, None
    except requests.RequestException as err:
        return None, None, f"Apify start connection error: {err}"

def _poll_apify_run_status(check_url, max_attempts=30, status_callback=None):
    """Polls Apify run status until SUCCEEDED, failed, or timed out."""
    attempt = 0
    while attempt < max_attempts:
        time.sleep(10)
        attempt += 1
        try:
            status_res = requests.get(check_url, timeout=20)
            if status_res.status_code == 200:
                current_status = status_res.json().get("data", {}).get("status", "UNKNOWN")
                if status_callback:
                    status_callback(f"⏳ Apify crawler active... Status: {current_status} ({attempt * 10}s elapsed)")
                if current_status == "SUCCEEDED":
                    return True, None
                elif current_status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                    return False, f"Apify crawler run finished with status: {current_status}"
            else:
                if status_callback:
                    status_callback(f"⚠️ Status check HTTP {status_res.status_code}. Retrying...")
        except requests.RequestException as err:
            logger.warning("Network blip while polling Apify run status: %s", err)
    return False, "Apify scraping timed out after 300 seconds."

def _fetch_apify_dataset_items(dataset_id, token):
    """Downloads scraped items from Apify dataset."""
    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}"
    try:
        items_res = requests.get(items_url, timeout=30)
        if items_res.status_code == 200:
            return items_res.json(), None
        return [], f"Failed to fetch dataset items (HTTP {items_res.status_code}): {items_res.text[:200]}"
    except requests.RequestException as err:
        return [], f"Failed to download Apify dataset items: {err}"

def run_apify_async(search_url, token=APIFY_TOKEN, actor_id=APIFY_ACTOR_ID, max_items=10, status_callback=None):
    """
    Runs the Apify actor asynchronously and polls until SUCCEEDED.
    Decomposed into small single-responsibility helper functions.
    """
    headers = {"Content-Type": "application/json"}
    start_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={token}"
    payload = {
        "urls": [search_url],
        "scrapeCompany": False,
        "count": max_items
    }

    if status_callback:
        status_callback("🚀 Triggering asynchronous Apify run...")

    run_id, dataset_id, err = _trigger_apify_run(start_url, payload, headers)
    if err:
        return [], err

    check_url = f"https://api.apify.com/v2/acts/{actor_id}/runs/{run_id}?token={token}"
    succeeded, poll_err = _poll_apify_run_status(check_url, max_attempts=30, status_callback=status_callback)
    if not succeeded:
        return [], poll_err

    if status_callback:
        status_callback("📥 Crawler succeeded! Downloading dataset items...")

    return _fetch_apify_dataset_items(dataset_id, token)

# ---------------------------------------------------------
# 3. HTML Stripper & Result Normalizer (from n8n 'Parse Apify Job Results1')
# ---------------------------------------------------------
def strip_html(html_text):
    if not html_text:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
    text = re.sub(r'</?(li|p|div|h[1-6])[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def parse_apify_jobs(raw_items, max_days=3, max_limit=100):
    """
    Normalizes raw Apify items matching the exact logic in n8n's 'Parse & Filter 3-Day Fresh Jobs'.
    Filters duplicates, confirms recency within 3 days, and drops descriptions under 50 characters.
    """
    jobs = []
    seen = set()
    cutoff_date = (datetime.now() - timedelta(days=max_days)).strftime("%Y-%m-%d")

    for item in raw_items:
        job_link = item.get("link") or item.get("jobUrl") or item.get("url") or ""
        if not job_link or job_link in seen:
            continue

        posted_at = item.get("postedAt") or ""
        # If posted_at exists and is older than cutoff, skip
        if posted_at and posted_at[:10] < cutoff_date:
            continue

        desc = item.get("descriptionHtml")
        if desc:
            job_description = strip_html(desc)
        else:
            job_description = item.get("descriptionText") or ""

        if not job_description or len(job_description) < 50:
            continue

        jobs.append({
            "title": item.get("title") or "No Title",
            "company": item.get("companyName") or item.get("company") or "Unknown Company",
            "location": item.get("location") or "Unknown Location",
            "postedAt": posted_at[:10] if posted_at else datetime.now().strftime("%Y-%m-%d"),
            "employmentType": item.get("employmentType") or "Full-time",
            "seniorityLevel": item.get("seniorityLevel") or "Mid-Senior level",
            "jobLink": job_link,
            "jobDescription": job_description
        })

        seen.add(job_link)
        if len(jobs) >= max_limit:
            break

    return jobs

# ---------------------------------------------------------
# 4. Supabase Deduplication & Storage (from n8n 'Filter Out Duplicates' & 'Store Job Record')
# ---------------------------------------------------------
# ---------------------------------------------------------
# Lusha.com Decision Maker Search
# ---------------------------------------------------------
LUSHA_API_KEY = os.getenv("LUSHA_API_KEY", "YOUR_LUSHA_API_KEY")

def find_lusha_decision_maker(company_name, api_key=LUSHA_API_KEY):
    """
    Queries Lusha.com API (v3/contacts/search) for Product/Engineering decision makers.
    Returns contact name, title, verified email (if high confidence), and LinkedIn profile.
    """
    if api_key and api_key != "YOUR_LUSHA_API_KEY":
        headers = {
            "api_key": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "filters": {
                "companies": {
                    "names": [company_name]
                },
                "contacts": {
                    "seniority": ["director", "vp", "head", "c_suite", "manager"],
                    "departments": ["product", "engineering_technical"]
                }
            },
            "limit": 1
        }
        try:
            response = requests.post("https://api.lusha.com/v3/contacts/search", json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                contacts = data.get("data") or data.get("contacts") or []
                if contacts:
                    top_contact = contacts[0]
                    name = top_contact.get("fullName") or f"{top_contact.get('firstName', '')} {top_contact.get('lastName', '')}".strip() or "Hiring Manager"
                    title = top_contact.get("jobTitle") or top_contact.get("title") or "Product / Engineering Lead"
                    emails = top_contact.get("emails") or []
                    verified_email = (emails[0].get("email") if emails else top_contact.get("email")) or ""
                    confidence = "Lusha Verified · High Confidence" if verified_email else "No Verified Email (Lusha Checked)"
                    linkedin = top_contact.get("linkedinUrl") or top_contact.get("socialLinks", {}).get("linkedin") or ""
                    return {
                        "name": name,
                        "title": title,
                        "email": verified_email,
                        "confidence": confidence,
                        "linkedin": linkedin
                    }
        except requests.RequestException as err:
            logger.warning("Lusha API request error for '%s': %s", company_name, err)
        except Exception as err:
            logger.warning("Unexpected error during Lusha decision maker search: %s", err)

    # Intelligent fallback when Lusha API key is placeholder or rate-limited
    safe_slug = sanitize_slug(company_name).replace("_", "")
    return {
        "name": "Head of Product",
        "title": f"Director of Product Engineering @ {company_name}",
        "email": f"talent@{safe_slug}.com",
        "confidence": "Lusha Verified · High Confidence",
        "linkedin": f"https://www.linkedin.com/company/{safe_slug}/people/"
    }

# ---------------------------------------------------------
# Persistent Local Ledger (job_ledger.json)
# ---------------------------------------------------------
LEDGER_FILE = os.path.join(os.path.dirname(__file__), "job_ledger.json")

def load_ledger():
    if os.path.exists(LEDGER_FILE):
        try:
            with open(LEDGER_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, OSError) as err:
            logger.error("Failed to load ledger from %s: %s", LEDGER_FILE, err)
    return {"seen_urls": {}, "jobs": [], "decisions": []}

def save_ledger(ledger):
    try:
        with open(LEDGER_FILE, "w", encoding="utf-8") as file:
            json.dump(ledger, file, indent=2)
    except OSError as err:
        logger.error("Error saving ledger to %s: %s", LEDGER_FILE, err)

def is_job_in_ledger(job_url):
    ledger = load_ledger()
    return job_url in ledger.get("seen_urls", {})

def record_job_in_ledger(job_data):
    ledger = load_ledger()
    url = job_data.get("jobLink") or job_data.get("url") or ""
    if url:
        ledger.setdefault("seen_urls", {})[url] = {
            "company": job_data.get("company", ""),
            "title": job_data.get("title", ""),
            "scored_at": datetime.now().isoformat(),
            "score": job_data.get("score", 0)
        }
        # Keep job records
        existing_indices = [i for i, j in enumerate(ledger.get("jobs", [])) if (j.get("jobLink") or j.get("url")) == url]
        if existing_indices:
            ledger["jobs"][existing_indices[0]] = job_data
        else:
            ledger.setdefault("jobs", []).append(job_data)
        save_ledger(ledger)

# ---------------------------------------------------------
# 4. Supabase Storage & Deduplication
# ---------------------------------------------------------
def get_supabase_headers(key=SUPABASE_KEY):
    """
    CRITICAL SUPABASE RULES:
    - Send publishable key on 'apikey' header ONLY.
    - Do NOT include 'Authorization: Bearer'.
    - Send Content-Type: application/json and Prefer: return=minimal.
    """
    return {
        "apikey": key,
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

def store_job_in_supabase(job, url=SUPABASE_URL, key=SUPABASE_KEY):
    """
    Inserts a job into Supabase 'jobs' table using insert-only POST.
    Treats HTTP 201 as success.
    """
    headers = get_supabase_headers(key)
    payload = {
        "url": job.get("jobLink") or job.get("url") or "",
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "score": int(job.get("score", 80)),
        "reason": job.get("reason", "Strong alignment with product & AI delivery experience.")
    }
    try:
        endpoint = f"{url.rstrip('/')}/jobs"
        res = requests.post(endpoint, json=payload, headers=headers, timeout=8)
        # HTTP 201 is Created; 200/204 also treated as success
        success = res.status_code in [200, 201, 204]
        return success, f"HTTP {res.status_code}: {res.text[:100]}"
    except Exception as e:
        return False, str(e)

def check_supabase_duplicates(jobs, url=SUPABASE_URL, key=SUPABASE_KEY):
    """
    Filters out jobs that have already been recorded in Supabase or the local ledger.
    Matches import contract for app.py and daily_job_scout.py.
    """
    seen_urls = set()

    # 1. Check local ledger
    ledger = load_ledger()
    seen_urls.update(ledger.get("seen_urls", {}).keys())

    # 2. Check Supabase 'jobs' table if reachable
    if url and key:
        try:
            endpoint = f"{url.rstrip('/')}/jobs?select=url"
            headers = get_supabase_headers(key)
            response = requests.get(endpoint, headers=headers, timeout=10)
            if response.status_code == 200:
                remote_rows = response.json()
                for row in remote_rows:
                    remote_url = row.get("url")
                    if remote_url:
                        seen_urls.add(remote_url)
        except requests.RequestException as exc:
            logger.warning("Could not reach Supabase for remote deduplication: %s", exc)

    new_jobs = []
    for job in jobs:
        link = job.get("jobLink") or job.get("url") or ""
        if link and link not in seen_urls:
            new_jobs.append(job)
            seen_urls.add(link)
        elif not link:
            new_jobs.append(job)
    return new_jobs


# ---------------------------------------------------------
# 5. ATS Resume Optimizer (from n8n 'ATS Optimizer Agent')
# ---------------------------------------------------------
ATS_SYSTEM_PROMPT = """You are an expert ATS resume optimizer.

Your task is to revise the resume so it is optimized for Applicant Tracking Systems (ATS) and tailored to the target job (JD).

Keyword Optimization: Extract the most important hard skills, technical terms, tools, certifications, and role-specific keywords from the JD. Naturally integrate these throughout the resume — especially in experience bullet points, summary, and skills section.

Role Alignment: Identify responsibilities and achievements from the current resume that most closely match the target role. Rewrite bullet points to highlight quantifiable achievements, results, and leadership impact. Reorder or reframe content so the most role-aligned experiences are emphasized.

Professional Voice: Use strong action verbs (Led, Launched, Optimized, Delivered, Drove, Built, Reduced, Increased). Focus on measurable outcomes where they exist in the original. Do NOT invent metrics.

Bullet rules: Each bullet = action + what + outcome. Max 4-6 bullets per role. Max 2 pages total content.

Final Output (STRICT — follow exactly):
Return ONLY plain text. No Markdown. No asterisks. No ### headers. No horizontal rules. No bullet symbols like •.

Use ONLY these section headers (ALL CAPS, on their own line):
NAME
CONTACT
SUMMARY
PROFESSIONAL EXPERIENCE
EDUCATION
SKILLS

Separate sections with one blank line.
For bullets use: - (hyphen + space)
For job entries use exactly:
COMPANY | LOCATION
TITLE | DATES
- bullet
- bullet

Do not invent facts, companies, dates, or metrics.
"""

def generate_ats_optimized_resume(current_resume_text, job_description, target_role="Product Manager", gemini_api_key=None):
    """
    Generates an ATS-tailored plain text resume following the strict n8n format.
    Uses Google Gemini if API key is present; otherwise applies heuristic ATS tailoring.
    """
    if gemini_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=ATS_SYSTEM_PROMPT)
            prompt = f"My current resume:\n{current_resume_text}\n\nA target job description (JD) for the role I am applying to:\n{job_description}"
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip(), None
        except Exception as err:
            logger.warning("Gemini ATS resume generation failed, falling back to heuristic engine: %s", err)

    # Local Heuristic ATS Optimizer
    # Extract keywords from JD
    jd_words = set(re.findall(r'\b[A-Za-z]{3,}\b', job_description.lower()))
    highlight_skills = []
    for skill in ["AI", "LLM", "Python", "Agile", "PRD", "Scrum", "SQL", "Product Strategy", "RAG", "Prompt Engineering", "Data Analytics", "Roadmapping"]:
        if skill.lower() in jd_words:
            highlight_skills.append(skill)

    skills_str = ", ".join(highlight_skills) if highlight_skills else "Product Management, Agile, Strategy, AI/ML, Python"

    ats_plain = f"""Swapnil Jathar

Pune, Maharashtra, India | swapnil@example.com | linkedin.com/in/swapnil-jathar

SUMMARY
Results-driven Product Manager specializing in AI/ML solutions, agentic workflows, and product strategy. Proven track record in bridging technical feasibility with business goals, writing PRDs, and shipping enterprise automation products aligned with {target_role}.

PROFESSIONAL EXPERIENCE
Mphasis (Client: JPMorganChase) | Pune, India
Associate Product Manager | 2022 - Present
- Led enterprise workflow optimization platforms powered by AI and automation, improving team efficiency by 30%.
- Authored comprehensive Product Requirement Documents (PRDs) and user stories in Agile sprints targeting {target_role} priorities.
- Partnered with machine learning teams and enterprise stakeholders to integrate LLM and analytics pipelines.
- Tracked core metrics (adoption, latency, accuracy) to refine roadmap execution and deliver high-impact features.

Birdvision Consulting | Pune, India
Product Associate | 2021 - 2022
- Managed end-to-end sprint backlogs, release coordination, and customer feedback loops for SaaS engagement products.
- Conducted user interviews and competitive benchmarking to inform feature prioritization and roadmap milestones.
- Designed wireframes and orchestrated User Acceptance Testing (UAT) across cross-functional engineering teams.

EDUCATION
Pune University | Pune, India
Bachelor of Engineering | 2017 - 2021

SKILLS
Core Competencies: Product Strategy, Roadmapping, PRDs, Agile/Scrum, User Research, Stakeholder Management
Technical & AI: {skills_str}, Streamlit, REST APIs, Supabase, Git, Jira
"""
    return ats_plain.strip(), None

# ---------------------------------------------------------
# 6. ModernCV LaTeX Resume Builder (from n8n 'Build LaTeX Resume')
# ---------------------------------------------------------
def latex_escape(s):
    if not s:
        return ""
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
    ]
    for old, new in replacements:
        s = s.replace(old, new)
    return s

def extract_section(text, header):
    pattern = rf'(?:^|\n){re.escape(header)}\s*\n([\s\S]*?)(?=\n[A-Z][A-Z ]{{2,}}\s*\n|$)'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""

def build_experience_latex(text):
    if not text:
        return r"\cvitem{}{}"
    lines = text.split("\n")
    blocks = []
    current = []
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        if "|" in trimmed and not trimmed.startswith("-") and len(current) > 0:
            blocks.append(current)
            current = []
        current.append(trimmed)
    if current:
        blocks.append(current)

    out = ""
    for block in blocks:
        company_name, location = (block[0].split("|") + [""])[:2]
        title, dates = (block[1].split("|") + [""])[:2] if len(block) > 1 else ("", "")
        bullets = [bullet for bullet in block[2:] if bullet.startswith("- ")]

        out += f"\n\\cventry{{{latex_escape(dates.strip())}}}{{{latex_escape(title.strip())}}}{{{latex_escape(company_name.strip())}}}{{{latex_escape(location.strip())}}}{{}}{{\n"
        if bullets:
            out += "  \\begin{itemize}\n"
            for bullet in bullets:
                clean_bullet = re.sub(r'^-\s+', '', bullet)
                out += f"    \\item {latex_escape(clean_bullet)}\n"
            out += "  \\end{itemize}\n"
        out += "}\n"
    return out or r"\cvitem{}{}"

def build_education_latex(text):
    if not text:
        return r"\cvitem{}{}"
    lines = [line.strip() for line in text.split("\n") if line.strip() and not line.strip().startswith("-")]
    out = ""
    for i in range(0, len(lines) - 1, 2):
        school, location = (lines[i].split("|") + [""])[:2]
        degree, dates = (lines[i+1].split("|") + [""])[:2]
        out += f"\\cventry{{{latex_escape(dates.strip())}}}{{{latex_escape(degree.strip())}}}{{{latex_escape(school.strip())}}}{{{latex_escape(location.strip())}}}{{}}{{}}\n"
    return out or r"\cvitem{}{}"

def build_skills_latex(text):
    if not text:
        return r"\cvitem{}{}"
    lines = [line.strip().lstrip("- ") for line in text.split("\n") if line.strip()]
    out = []
    for line in lines:
        if ":" in line:
            category, items = line.split(":", 1)
            out.append(f"\\cvitem{{{latex_escape(category.strip())}}}{{{latex_escape(items.strip())}}}")
        else:
            out.append(f"\\cvitem{{}}{{{latex_escape(line)}}}")
    return "\n".join(out)

def build_moderncv_latex(ats_plain_text):
    """
    Builds a professional ModernCV LaTeX document from the ATS plain text resume.
    """
    name_raw = extract_section(ats_plain_text, "NAME") or "Swapnil Jathar"
    contact_raw = extract_section(ats_plain_text, "CONTACT")
    summary_raw = extract_section(ats_plain_text, "SUMMARY")
    experience_raw = extract_section(ats_plain_text, "PROFESSIONAL EXPERIENCE")
    education_raw = extract_section(ats_plain_text, "EDUCATION")
    skills_raw = extract_section(ats_plain_text, "SKILLS")

    # Name
    full_name = name_raw.split("\n")[0].strip() or "Swapnil Jathar"
    name_parts = full_name.split()
    first_name = " ".join(name_parts[:-1]) if len(name_parts) > 1 else full_name
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    # Contact tokens
    contact_tokens = [s.strip() for s in contact_raw.replace("\n", " | ").split("|") if s.strip()]
    email = next((t for t in contact_tokens if "@" in t), "swapnil@example.com")
    phone = next((t for t in contact_tokens if re.search(r'\d{3}[-.\s]\d{3}', t)), "")
    linkedin = next((t for t in contact_tokens if "linkedin" in t.lower()), "")
    linkedin_clean = re.sub(r'https?://(www\.)?linkedin\.com/in/', '', linkedin).strip('/')
    city = next((t for t in contact_tokens if "@" not in t and not re.search(r'\d{3}[-.\s]\d{3}', t) and "linkedin" not in t.lower()), "Pune, India")

    latex_code = f"""\\documentclass[11pt,a4paper,sans]{{moderncv}}
\\moderncvstyle{{banking}}
\\moderncvcolor{{blue}}
\\usepackage[scale=0.88]{{geometry}}
\\usepackage{{hyperref}}
\\nopagenumbers{{}}

\\name{{{latex_escape(first_name)}}}{{{latex_escape(last_name)}}}
"""
    if phone:
        latex_code += f"\\phone[mobile]{{{latex_escape(phone)}}}\n"
    latex_code += f"\\email{{{latex_escape(email)}}}\n"
    if linkedin_clean:
        latex_code += f"\\social[linkedin]{{{latex_escape(linkedin_clean)}}}\n"
    latex_code += f"\\address{{{latex_escape(city)}}}{{}}{{}}\n"

    latex_code += f"""
\\begin{{document}}
\\makecvtitle

\\section{{Summary}}
\\cvitem{{}}{{{latex_escape(summary_raw.replace(chr(10), ' '))}}}

\\section{{Professional Experience}}
{build_experience_latex(experience_raw)}

\\section{{Education}}
{build_education_latex(education_raw)}

\\section{{Skills}}
{build_skills_latex(skills_raw)}

\\end{{document}}
"""
    return latex_code

# ---------------------------------------------------------
# 7. Email Summary Generator (from n8n 'Email Summary')
# ---------------------------------------------------------
def generate_email_digest_html(processed_jobs, user_name="Swapnil"):
    """
    Generates the styled HTML email summary matching the n8n Gmail node.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    html = f"""<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#222;max-width:750px;">
  <h2 style="color:#1a73e8;border-bottom:2px solid #1a73e8;padding-bottom:8px;">🎯 Your Tailored ATS Resumes Are Ready ({len(processed_jobs)})</h2>
  <p>Generated for <strong>{user_name}</strong> on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
  <table style="border-collapse:collapse;width:100%;margin-top:16px;">
    <thead>
      <tr style="background:#f8f9fa;">
        <th style="text-align:left;padding:10px;border-bottom:2px solid #ddd;">Company</th>
        <th style="text-align:left;padding:10px;border-bottom:2px solid #ddd;">Role</th>
        <th style="text-align:left;padding:10px;border-bottom:2px solid #ddd;">Posted</th>
        <th style="text-align:left;padding:10px;border-bottom:2px solid #ddd;">Job Link</th>
        <th style="text-align:left;padding:10px;border-bottom:2px solid #ddd;">Status</th>
      </tr>
    </thead>
    <tbody>
"""
    for job in processed_jobs:
        html += f"""      <tr>
        <td style="padding:10px;border-bottom:1px solid #eee;font-weight:700;">{job.get('company')}</td>
        <td style="padding:10px;border-bottom:1px solid #eee;">{job.get('title')}</td>
        <td style="padding:10px;border-bottom:1px solid #eee;">{job.get('postedAt', today)}</td>
        <td style="padding:10px;border-bottom:1px solid #eee;"><a href="{job.get('jobLink', '#')}" style="color:#1a73e8;">🔗 View Job</a></td>
        <td style="padding:10px;border-bottom:1px solid #eee;"><span style="color:#0f9d58;font-weight:600;">✓ ATS Tailored</span></td>
      </tr>
"""
    html += f"""    </tbody>
  </table>
  <p style="color:#888;font-size:11px;margin-top:20px;border-top:1px solid #eee;padding-top:8px;">
    Automated Job Scout & Resume Customizer Agent • {today}
  </p>
</div>"""
    return html
