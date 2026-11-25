-- ============================================================================
-- Sinh học 12 - Web App Giảng dạy & Ôn tập (CT GDPT 2018)
-- PostgreSQL / Supabase Migration Schema
-- Sẵn sàng để triển khai trực tuyến trên Supabase (Auth + Postgres + RLS)
-- ============================================================================

create extension if not exists "pgcrypto";

-- 1. Hồ sơ người dùng (Học sinh & Giáo viên)
create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  email text unique not null,
  full_name text not null,
  role text not null check (role in ('student', 'teacher')),
  class_name text default '',
  school_name text default 'THPT',
  phone text default '',
  bio text default '',
  avatar_color text default '#0f766e',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- 2. Chủ đề học tập (Chủ đề 1, 2, 3...)
create table if not exists public.topics (
  id text primary key,
  order_index int not null default 1,
  title text not null,
  subtitle text default '',
  status text not null default 'published' check (status in ('published', 'coming_soon', 'draft')),
  content_json jsonb not null,
  updated_by uuid references public.profiles(id) on delete set null,
  updated_at timestamptz not null default now()
);

-- 3. Nhật ký điểm danh vào/rời lớp học của học sinh
create table if not exists public.study_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  topic_id text references public.topics(id) on delete set null,
  enter_time timestamptz not null default now(),
  last_heartbeat timestamptz not null default now(),
  leave_time timestamptz,
  duration_seconds int not null default 0,
  last_tab text default 'theory',
  status text not null default 'active' check (status in ('active', 'completed'))
);

create index if not exists idx_study_sessions_user on public.study_sessions(user_id, enter_time desc);
create index if not exists idx_study_sessions_status on public.study_sessions(status);

-- 4. Kết quả làm bài ôn tập (3 phần: 4 đáp án, Đúng/Sai, Trả lời ngắn)
create table if not exists public.quiz_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  topic_id text not null references public.topics(id) on delete cascade,
  quiz_type text not null check (quiz_type in ('mcq', 'true_false', 'short_answer', 'combined')),
  score numeric(5,2) not null,
  max_score numeric(5,2) not null,
  correct_count int not null default 0,
  total_questions int not null default 0,
  duration_seconds int not null default 0,
  answers_json jsonb not null default '{}'::jsonb,
  submitted_at timestamptz not null default now()
);

create index if not exists idx_quiz_attempts_user on public.quiz_attempts(user_id, submitted_at desc);
create index if not exists idx_quiz_attempts_topic on public.quiz_attempts(topic_id);

-- 5. Tiến độ hoàn thành bài giảng / mốc video tương tác
create table if not exists public.lesson_progress (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  topic_id text not null references public.topics(id) on delete cascade,
  lesson_id text not null,
  completed boolean not null default false,
  checkpoint_score int not null default 0,
  updated_at timestamptz not null default now(),
  unique (user_id, topic_id, lesson_id)
);

-- Gợi ý Row Level Security (RLS) khi bật Supabase Auth:
-- alter table public.profiles enable row level security;
-- alter table public.study_sessions enable row level security;
-- alter table public.quiz_attempts enable row level security;
-- Giáo viên có quyền đọc toàn bộ study_sessions & quiz_attempts; Học sinh chỉ đọc/ghi dữ liệu của chính mình.
