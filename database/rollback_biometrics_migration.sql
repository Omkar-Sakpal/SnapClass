-- SnapClass Biometrics Rollback Script (Stage 1 - Final Verified)
--
-- CAUTION / IMPACT:
-- Executing this script will PERMANENTLY DROP the 'public.student_biometrics' table,
-- including all stored biometric templates (face and voice embeddings), consent records,
-- and related policies.
--
-- Existing tables (teachers, students, subjects, subject_students, attendance_logs)
-- and their existing data and policies remain 100% UNTOUCHED and fully functional.

begin;

-- 1. Drop all RLS policies associated with student_biometrics
drop policy if exists "student reads own biometrics" on public.student_biometrics;
drop policy if exists "student inserts own biometrics" on public.student_biometrics;
drop policy if exists "student updates own biometrics" on public.student_biometrics;
drop policy if exists "student deletes own biometrics" on public.student_biometrics;
drop policy if exists "teacher reads enrolled student biometrics" on public.student_biometrics;

-- 2. Revoke table grants
revoke all on table public.student_biometrics from authenticated;
revoke all on table public.student_biometrics from anon;
revoke all on table public.student_biometrics from public;

-- 3. Drop the student_biometrics table
drop table if exists public.student_biometrics cascade;

commit;
