-- ============================================================
-- Supabase Schema for Job Scout & Resume Customizer Agent
-- ============================================================
-- Run this in your Supabase Dashboard -> SQL Editor -> New Query

-- 1. Create the 'jobs' table
CREATE TABLE IF NOT EXISTS public.jobs (
    id BIGSERIAL PRIMARY KEY,
    job_url TEXT UNIQUE NOT NULL,
    job_title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    score INT DEFAULT 75,
    status TEXT DEFAULT 'processed',
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create index on job_url for fast deduplication lookup
CREATE INDEX IF NOT EXISTS idx_jobs_url ON public.jobs (job_url);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

-- 4. Policy allowing anonymous / service access
CREATE POLICY "Allow anon read and insert"
ON public.jobs
FOR ALL
USING (true)
WITH CHECK (true);
