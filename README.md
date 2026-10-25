# 🎯 Job Scout Agent · LinkedIn Jobs & ATS Tailoring Dashboard

An intelligent Streamlit dashboard for tech and product professionals that crawls LinkedIn job listings via Apify, scores opportunities against a master resume, and generates tailored resume variations.

---

## 🚀 Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables (Optional)
If not set, default credentials configured in `app.py` will be used:
```bash
export APIFY_API_TOKEN="your_apify_token_here"
export SUPABASE_URL="https://your-project.supabase.co/rest/v1/"
export SUPABASE_KEY="your_supabase_key"
```

### 3. Launch the Dashboard
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 🛠 Features

1. **📋 Scored Job Feed**:
   - **Live LinkedIn Scraping**: Queries Apify (`curious_coder/linkedin-jobs-scraper`) for live roles in your target location (e.g. Pune, India).
   - **Offline / Demo Feed Mode**: Toggleable in the sidebar for immediate preview and testing without waiting for live scraping runs or consuming Apify credits.
   - **Scoring Engine**: Evaluates title alignment, must-have skills (AI, LLM, Python, Agile), and filters out unwanted keywords.
   - **Interactive Actions**:
     - `✨ Tailor Resume`: Auto-generates a targeted resume file (`resume_<company>_<date>.md`) and provides a one-click download.
     - `⏭️ Skip`: Marks a listing as reviewed.
     - `🚫 Not a Fit`: Records your preference to refine future recommendations.

2. **📄 Master Resume**:
   - **Multi-Format Upload**: Upload your existing resume in **PDF (`.pdf`)**, **Microsoft Word (`.docx`)**, **Markdown (`.md`)**, or **Plain Text (`.txt`)**.
   - **Auto-Parsing**: Automatically extracts text, calculates word count, and offers a live preview before applying.
   - **Dynamic Re-scoring**: Saving a newly uploaded resume immediately triggers the scoring engine to recalculate job fit percentages.
   - **In-App Editor**: Switch to edit mode to make quick manual updates to [`master_resume.md`](file:///Users/swapnil/Job_Search_Agent/master_resume.md).

3. **⚙️ Agent Activity & Logs**:
   - Live session metrics (total jobs evaluated, high matches $\ge 80\%$, actions taken).
   - Interactive table tracking your decisions history.
   - Integration status for Apify and Supabase.
>>>>>>> 86ba938 (feat: initial Job Scout Agent with ATS tailoring, human-in-the-loop review, and auth flow)
