-- SnapClass Additive Biometrics Migration (Stage 1 - Final Verified)
--
-- PURPOSE:
-- Creates an isolated 'public.student_biometrics' table to hold mathematical templates
-- (128-d face descriptors and 256-d voice embeddings) with explicit consent tracking
-- and strict Row Level Security (RLS).
--
-- SAFETY & VERIFICATION GUARANTEES:
-- 1. Table Pre-Existence Check: If 'public.student_biometrics' already exists, aborts
--    immediately to prevent assuming an existing table has the required schema or constraints.
-- 2. Dynamic Live Type Resolution: Reads the actual live data type of 'public.students.student_id'
--    from information_schema.columns and creates the foreign key with the matching compatible type.
-- 3. Fail-Closed Policy Creation: If any policy with an expected name already exists,
--    aborts with an exception to prevent policy drift or silent replacement.
-- 4. Hard Consent Invariant: Check constraint enforces consent_given = true and
--    consent_timestamp IS NOT NULL on every row.
-- 5. Scope Isolation: Touches ONLY public.student_biometrics. ZERO alterations to
--    existing tables (teachers, students, subjects, subject_students, attendance_logs),
--    their permissions, or their policies.
-- 6. Least-Privilege Grants: REVOKES all from anon and PUBLIC; GRANTS only to authenticated.

begin;

-- Step 1: Pre-checks, live type detection, and safe table creation
do $$
declare
    v_data_type text;
    v_udt_name text;
    v_col_type text;
begin
    -- 1a. Fail safely if student_biometrics already exists
    if exists (
        select 1 from information_schema.tables
        where table_schema = 'public'
          and table_name = 'student_biometrics'
    ) then
        raise exception 'Table "public.student_biometrics" already exists. Migration aborted to prevent assuming its schema is valid. Review or run rollback first.';
    end if;

    -- 1b. Read the actual live type of public.students.student_id
    select data_type, udt_name into v_data_type, v_udt_name
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'students'
      and column_name = 'student_id';

    if v_data_type is null then
        raise exception 'Live schema check failed: table "public.students" or column "student_id" does not exist. Migration aborted.';
    end if;

    -- 1c. Determine the exact compatible type based on live metadata
    if v_udt_name = 'int8' or v_data_type = 'bigint' then
        v_col_type := 'bigint';
    elsif v_udt_name = 'int4' or v_data_type = 'integer' then
        v_col_type := 'integer';
    else
        raise exception 'Column public.students.student_id has unexpected live type "%" (udt: "%"). Cannot safely create foreign key. Migration aborted.', v_data_type, v_udt_name;
    end if;

    raise notice 'Live type of public.students.student_id is % (%). Creating public.student_biometrics with compatible % foreign key.', v_data_type, v_udt_name, v_col_type;

    -- 1d. Create table with dynamically matched foreign key type
    execute format('
        create table public.student_biometrics (
            student_id %s primary key references public.students(student_id) on delete cascade,
            face_embedding jsonb,
            voice_embedding jsonb,
            consent_given boolean not null default false,
            consent_timestamp timestamptz,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now(),
            constraint student_biometrics_consent_required check (
                consent_given = true and consent_timestamp is not null
            ),
            constraint student_biometrics_has_embedding check (
                face_embedding is not null or voice_embedding is not null
            )
        )', v_col_type);
end $$;

-- Step 2: Index foreign key reference for efficient joins
create index if not exists idx_student_biometrics_student_id
    on public.student_biometrics(student_id);

-- Step 3: Explicit Least-Privilege Grants (Applies ONLY to student_biometrics)
revoke all on table public.student_biometrics from public;
revoke all on table public.student_biometrics from anon;
grant select, insert, update, delete on table public.student_biometrics to authenticated;

-- Step 4: Enable Row Level Security explicitly on student_biometrics
alter table public.student_biometrics enable row level security;

-- Step 5: Fail-Closed Policy Creation
-- If a policy with the expected name already exists, abort migration to prevent drift.

-- 5a. Policy: student reads own biometrics (SELECT, authenticated)
do $$
begin
    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'student_biometrics'
          and policyname = 'student reads own biometrics'
    ) then
        raise exception 'Policy "student reads own biometrics" already exists on public.student_biometrics. Migration failed closed to prevent policy drift. Review or run rollback first.';
    else
        create policy "student reads own biometrics" on public.student_biometrics
        for select to authenticated
        using (exists (
            select 1 from public.students s
            where s.student_id = student_biometrics.student_id
              and s.auth_user_id = (select auth.uid())
        ));
        raise notice 'Policy "student reads own biometrics" created successfully.';
    end if;
end $$;

-- 5b. Policy: student inserts own biometrics (INSERT, authenticated)
do $$
begin
    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'student_biometrics'
          and policyname = 'student inserts own biometrics'
    ) then
        raise exception 'Policy "student inserts own biometrics" already exists on public.student_biometrics. Migration failed closed to prevent policy drift. Review or run rollback first.';
    else
        create policy "student inserts own biometrics" on public.student_biometrics
        for insert to authenticated
        with check (exists (
            select 1 from public.students s
            where s.student_id = student_biometrics.student_id
              and s.auth_user_id = (select auth.uid())
        ));
        raise notice 'Policy "student inserts own biometrics" created successfully.';
    end if;
end $$;

-- 5c. Policy: student updates own biometrics (UPDATE, authenticated)
do $$
begin
    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'student_biometrics'
          and policyname = 'student updates own biometrics'
    ) then
        raise exception 'Policy "student updates own biometrics" already exists on public.student_biometrics. Migration failed closed to prevent policy drift. Review or run rollback first.';
    else
        create policy "student updates own biometrics" on public.student_biometrics
        for update to authenticated
        using (exists (
            select 1 from public.students s
            where s.student_id = student_biometrics.student_id
              and s.auth_user_id = (select auth.uid())
        ))
        with check (exists (
            select 1 from public.students s
            where s.student_id = student_biometrics.student_id
              and s.auth_user_id = (select auth.uid())
        ));
        raise notice 'Policy "student updates own biometrics" created successfully.';
    end if;
end $$;

-- 5d. Policy: student deletes own biometrics (DELETE, authenticated)
do $$
begin
    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'student_biometrics'
          and policyname = 'student deletes own biometrics'
    ) then
        raise exception 'Policy "student deletes own biometrics" already exists on public.student_biometrics. Migration failed closed to prevent policy drift. Review or run rollback first.';
    else
        create policy "student deletes own biometrics" on public.student_biometrics
        for delete to authenticated
        using (exists (
            select 1 from public.students s
            where s.student_id = student_biometrics.student_id
              and s.auth_user_id = (select auth.uid())
        ));
        raise notice 'Policy "student deletes own biometrics" created successfully.';
    end if;
end $$;

-- 5e. Policy: teacher reads enrolled student biometrics (SELECT, authenticated)
do $$
begin
    if exists (
        select 1 from pg_policies
        where schemaname = 'public'
          and tablename = 'student_biometrics'
          and policyname = 'teacher reads enrolled student biometrics'
    ) then
        raise exception 'Policy "teacher reads enrolled student biometrics" already exists on public.student_biometrics. Migration failed closed to prevent policy drift. Review or run rollback first.';
    else
        create policy "teacher reads enrolled student biometrics" on public.student_biometrics
        for select to authenticated
        using (exists (
            select 1 from public.subject_students ss
            join public.subjects sub on sub.subject_id = ss.subject_id
            join public.teachers t on t.teacher_id = sub.teacher_id
            where ss.student_id = student_biometrics.student_id
              and t.auth_user_id = (select auth.uid())
        ));
        raise notice 'Policy "teacher reads enrolled student biometrics" created successfully.';
    end if;
end $$;

commit;
