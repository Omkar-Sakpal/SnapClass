-- SnapClass Auth/RLS migration for the five tables already created.
-- Review before running. It does not drop tables or delete records.
-- Uses Supabase Auth; do NOT use a secret/service-role key in the client app.

begin;

-- Link app profiles to authenticated Supabase users.
alter table public.teachers alter column password drop not null;
alter table public.teachers add column if not exists auth_user_id uuid unique references auth.users(id) on delete cascade;
alter table public.students add column if not exists auth_user_id uuid unique references auth.users(id) on delete cascade;
alter table public.students add column if not exists email text;

-- Enable RLS explicitly.
alter table public.teachers enable row level security;
alter table public.students enable row level security;
alter table public.subjects enable row level security;
alter table public.subject_students enable row level security;
alter table public.attendance_logs enable row level security;

-- Drop policies with these names so this migration can be re-run.
drop policy if exists "teacher reads own profile" on public.teachers;
drop policy if exists "teacher creates own profile" on public.teachers;
drop policy if exists "teacher updates own profile" on public.teachers;
drop policy if exists "student reads own profile" on public.students;
drop policy if exists "student creates own profile" on public.students;
drop policy if exists "student updates own profile" on public.students;
drop policy if exists "teacher reads enrolled students" on public.students;
drop policy if exists "authenticated users can read subjects" on public.subjects;
drop policy if exists "teacher creates own subjects" on public.subjects;
drop policy if exists "teacher updates own subjects" on public.subjects;
drop policy if exists "teacher deletes own subjects" on public.subjects;
drop policy if exists "student reads own enrollments" on public.subject_students;
drop policy if exists "student enrolls self" on public.subject_students;
drop policy if exists "teacher reads subject enrollments" on public.subject_students;
drop policy if exists "teacher reads attendance for own subjects" on public.attendance_logs;
drop policy if exists "student reads own attendance" on public.attendance_logs;
drop policy if exists "teacher records attendance for own subjects" on public.attendance_logs;
drop policy if exists "teacher updates attendance for own subjects" on public.attendance_logs;

create policy "teacher reads own profile" on public.teachers
for select to authenticated using (auth_user_id = (select auth.uid()));
create policy "teacher creates own profile" on public.teachers
for insert to authenticated with check (auth_user_id = (select auth.uid()));
create policy "teacher updates own profile" on public.teachers
for update to authenticated using (auth_user_id = (select auth.uid()))
with check (auth_user_id = (select auth.uid()));

create policy "student reads own profile" on public.students
for select to authenticated using (auth_user_id = (select auth.uid()));
create policy "student creates own profile" on public.students
for insert to authenticated with check (auth_user_id = (select auth.uid()));
create policy "student updates own profile" on public.students
for update to authenticated using (auth_user_id = (select auth.uid()))
with check (auth_user_id = (select auth.uid()));
create policy "teacher reads enrolled students" on public.students
for select to authenticated
using (exists (
  select 1 from public.subject_students ss
  join public.subjects sub on sub.subject_id = ss.subject_id
  join public.teachers t on t.teacher_id = sub.teacher_id
  where ss.student_id = students.student_id and t.auth_user_id = (select auth.uid())
));

-- Authenticated users may look up subjects to join using a subject code.
-- Subject ownership still controls create/update/delete operations.
create policy "authenticated users can read subjects" on public.subjects
for select to authenticated using (true);
create policy "teacher creates own subjects" on public.subjects
for insert to authenticated
with check (exists (
  select 1 from public.teachers t
  where t.teacher_id = subjects.teacher_id and t.auth_user_id = (select auth.uid())
));
create policy "teacher updates own subjects" on public.subjects
for update to authenticated
using (exists (
  select 1 from public.teachers t
  where t.teacher_id = subjects.teacher_id and t.auth_user_id = (select auth.uid())
))
with check (exists (
  select 1 from public.teachers t
  where t.teacher_id = subjects.teacher_id and t.auth_user_id = (select auth.uid())
));
create policy "teacher deletes own subjects" on public.subjects
for delete to authenticated
using (exists (
  select 1 from public.teachers t
  where t.teacher_id = subjects.teacher_id and t.auth_user_id = (select auth.uid())
));

create policy "student reads own enrollments" on public.subject_students
for select to authenticated
using (exists (
  select 1 from public.students s
  where s.student_id = subject_students.student_id and s.auth_user_id = (select auth.uid())
) or exists (
  select 1 from public.subjects sub
  join public.teachers t on t.teacher_id = sub.teacher_id
  where sub.subject_id = subject_students.subject_id and t.auth_user_id = (select auth.uid())
));
create policy "student enrolls self" on public.subject_students
for insert to authenticated
with check (exists (
  select 1 from public.students s
  where s.student_id = subject_students.student_id and s.auth_user_id = (select auth.uid())
));
create policy "teacher reads subject enrollments" on public.subject_students
for delete to authenticated
using (exists (
  select 1 from public.subjects sub
  join public.teachers t on t.teacher_id = sub.teacher_id
  where sub.subject_id = subject_students.subject_id and t.auth_user_id = (select auth.uid())
));

create policy "teacher reads attendance for own subjects" on public.attendance_logs
for select to authenticated
using (
  exists (select 1 from public.subjects sub join public.teachers t on t.teacher_id = sub.teacher_id
          where sub.subject_id = attendance_logs.subject_id and t.auth_user_id = (select auth.uid()))
  or exists (select 1 from public.students s
             where s.student_id = attendance_logs.student_id and s.auth_user_id = (select auth.uid()))
);
create policy "student reads own attendance" on public.attendance_logs
for select to authenticated
using (exists (
  select 1 from public.students s
  where s.student_id = attendance_logs.student_id and s.auth_user_id = (select auth.uid())
));
create policy "teacher records attendance for own subjects" on public.attendance_logs
for insert to authenticated
with check (exists (
  select 1 from public.subjects sub
  join public.teachers t on t.teacher_id = sub.teacher_id
  where sub.subject_id = attendance_logs.subject_id and t.auth_user_id = (select auth.uid())
));
create policy "teacher updates attendance for own subjects" on public.attendance_logs
for update to authenticated
using (exists (
  select 1 from public.subjects sub
  join public.teachers t on t.teacher_id = sub.teacher_id
  where sub.subject_id = attendance_logs.subject_id and t.auth_user_id = (select auth.uid())
))
with check (exists (
  select 1 from public.subjects sub
  join public.teachers t on t.teacher_id = sub.teacher_id
  where sub.subject_id = attendance_logs.subject_id and t.auth_user_id = (select auth.uid())
));

commit;
