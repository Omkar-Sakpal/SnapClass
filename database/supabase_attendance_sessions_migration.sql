-- SnapClass Attendance Sessions & Integrity Migration
--
-- PURPOSE:
-- Formalizes persistent attendance session tracking and enforces unique
-- attendance entries per (student_id, subject_id, timestamp) in PostgreSQL.
--
-- DO NOT RUN AUTOMATICALLY:
-- Review in Supabase SQL Editor before applying to production.
-- The client application operates safely even before this migration is applied.

begin;

-- 1. Create attendance_sessions table with dynamic type matching for foreign keys
do $$
declare
    v_subject_id_type text;
    v_teacher_id_type text;
begin
    -- Resolve live data type of public.subjects.subject_id
    select case when udt_name = 'int8' or data_type = 'bigint' then 'bigint' else 'integer' end
    into v_subject_id_type
    from information_schema.columns
    where table_schema = 'public' and table_name = 'subjects' and column_name = 'subject_id';

    -- Resolve live data type of public.teachers.teacher_id
    select case when udt_name = 'int8' or data_type = 'bigint' then 'bigint' else 'integer' end
    into v_teacher_id_type
    from information_schema.columns
    where table_schema = 'public' and table_name = 'teachers' and column_name = 'teacher_id';

    if v_subject_id_type is null or v_teacher_id_type is null then
        raise exception 'Live schema check failed: public.subjects or public.teachers missing required id columns.';
    end if;

    execute format('
        create table if not exists public.attendance_sessions (
            session_id text primary key,
            subject_id %s not null references public.subjects(subject_id) on delete cascade,
            teacher_id %s not null references public.teachers(teacher_id) on delete cascade,
            started_at timestamptz not null default now(),
            ended_at timestamptz,
            status text not null default ''active'' check (status in (''active'', ''completed'')),
            created_at timestamptz not null default now()
        )', v_subject_id_type, v_teacher_id_type);
end $$;

-- 2. Index for fast teacher and subject queries
create index if not exists idx_attendance_sessions_subject_teacher
    on public.attendance_sessions(subject_id, teacher_id);

-- 3. Explicit Grants
revoke all on table public.attendance_sessions from public;
revoke all on table public.attendance_sessions from anon;
grant select, insert, update on table public.attendance_sessions to authenticated;

-- 4. Enable Row Level Security (RLS)
alter table public.attendance_sessions enable row level security;

-- 5. Policies: Teacher manages sessions for own subjects (idempotent)
drop policy if exists "teacher manages own attendance sessions" on public.attendance_sessions;
create policy "teacher manages own attendance sessions" on public.attendance_sessions
for all to authenticated
using (
    exists (
        select 1 from public.subjects sub
        join public.teachers t on t.teacher_id = sub.teacher_id
        where sub.subject_id = attendance_sessions.subject_id
          and t.auth_user_id = (select auth.uid())
    )
)
with check (
    exists (
        select 1 from public.subjects sub
        join public.teachers t on t.teacher_id = sub.teacher_id
        where sub.subject_id = attendance_sessions.subject_id
          and t.auth_user_id = (select auth.uid())
    )
);

-- 6. Safely deduplicate historical duplicate rows prior to creating unique index,
--    keeping the highest attendance_id for each duplicate group.
delete from public.attendance_logs a
using public.attendance_logs b
where a.attendance_id < b.attendance_id
  and a.student_id = b.student_id
  and a.subject_id = b.subject_id
  and a.timestamp = b.timestamp;

-- 7. Enforce uniqueness on attendance_logs to prevent duplicate entries per session timestamp
create unique index if not exists idx_unique_attendance_log_entry
    on public.attendance_logs(student_id, subject_id, timestamp);

commit;
