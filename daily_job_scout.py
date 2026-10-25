#!/usr/bin/env python3
"""
Autonomous Daily Job Scout Agent (matching the 7 AM n8n scheduleTrigger workflow)
Runs headlessly:
1. Loads Master Resume
2. Builds LinkedIn URL with 24h filter
3. Runs Apify Scraper Asynchronously
4. Parses & Deduplicates against Supabase
5. ATS-Optimizes top jobs
6. Generates ModernCV LaTeX resumes
7. Records jobs in Supabase
8. Outputs Email Digest
"""
import os
import sys
from datetime import datetime
from pipeline import (
    build_linkedin_url,
    run_apify_async,
    parse_apify_jobs,
    check_supabase_duplicates,
    store_job_in_supabase,
    generate_ats_optimized_resume,
    build_moderncv_latex,
    generate_email_digest_html,
    APIFY_TOKEN,
    SUPABASE_URL,
    SUPABASE_KEY
)

def run_daily_pipeline(query="AI Product Manager", location="Pune, Maharashtra, India", max_jobs=5):
    print("=" * 60)
    print(f"🎯 Starting Daily Job Scout Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Load Resume
    resume_path = "master_resume.md"
    if os.path.exists(resume_path):
        with open(resume_path, "r", encoding="utf-8") as f:
            resume_text = f.read()
        print(f"✓ Loaded Master Resume ({len(resume_text.split())} words)")
    else:
        resume_text = "Swapnil Jathar - Associate Product Manager | AI Systems"
        print("⚠️ No master_resume.md found; using fallback profile.")

    # 2. Build LinkedIn URL
    search_url = build_linkedin_url(query=query, location=location, time_filter="pastWeek")
    print(f"✓ Built LinkedIn Search URL:\n  {search_url}\n")

    # 3. Scrape via Apify Async
    print("🚀 Triggering Apify crawler...")
    raw_items, err = run_apify_async(search_url, max_items=max_jobs * 3, status_callback=print)

    if err:
        print(f"⚠️ Apify notice: {err}")
        return

    # 4. Parse & Clean
    parsed_jobs = parse_apify_jobs(raw_items, max_days=7, max_limit=max_jobs * 2)
    print(f"✓ Parsed & cleaned {len(parsed_jobs)} job listings.")

    # 5. Supabase Deduplication
    new_jobs = check_supabase_duplicates(parsed_jobs, SUPABASE_URL, SUPABASE_KEY)
    print(f"✓ After Supabase deduplication: {len(new_jobs)} new listings.")

    if not new_jobs:
        print("ℹ️ No new listings to process today.")
        return

    target_jobs = new_jobs[:max_jobs]
    processed_records = []

    # 6. ATS Tailoring & LaTeX Generation
    os.makedirs("resumes", exist_ok=True)

    for i, job in enumerate(target_jobs, 1):
        co = job["company"]
        title = job["title"]
        print(f"\n[{i}/{len(target_jobs)}] Processing: {title} @ {co}")

        # ATS Optimization
        ats_text, _ = generate_ats_optimized_resume(resume_text, job["jobDescription"], target_role=title)
        latex_code = build_moderncv_latex(ats_text)

        # Save files
        safe_co = "".join(c for c in co if c.isalnum() or c in (' ', '_')).rstrip().replace(" ", "_").lower()
        date_str = datetime.now().strftime("%Y%m%d")

        tex_filename = f"resumes/resume_{safe_co}_{date_str}.tex"
        txt_filename = f"resumes/resume_{safe_co}_{date_str}.txt"

        with open(tex_filename, "w", encoding="utf-8") as f:
            f.write(latex_code)
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(ats_text)

        print(f"  ✓ Saved LaTeX: {tex_filename}")
        print(f"  ✓ Saved ATS Text: {txt_filename}")

        # Store in Supabase
        stored, s_err = store_job_in_supabase(job, SUPABASE_URL, SUPABASE_KEY)
        if stored:
            print("  ✓ Stored record in Supabase.")
        else:
            print(f"  ⚠️ Supabase store note: {s_err}")

        processed_records.append(job)

    # 7. Generate Email Digest
    email_html = generate_email_digest_html(processed_records)
    digest_file = f"email_digest_{datetime.now().strftime('%Y%m%d')}.html"
    with open(digest_file, "w", encoding="utf-8") as f:
        f.write(email_html)
    print(f"\n✓ Generated Email Digest: {digest_file}")

    print("\n" + "=" * 60)
    print(f"🎉 Pipeline Complete! Processed {len(processed_records)} target opportunities.")
    print("=" * 60)

if __name__ == "__main__":
    run_daily_pipeline()
