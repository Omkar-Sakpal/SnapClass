# Deployment guide

## 1. Supabase
Your current project already has the base tables. In Supabase SQL Editor, review and run `database/supabase_auth_migration.sql`. It adds Auth-linked profile fields and policies without dropping tables.

Before students can register biometrics (Stage 2), execute `database/supabase_biometrics_migration.sql` in your Supabase SQL Editor. It creates the isolated `public.student_biometrics` table, check constraints, and RLS policies without altering existing attendance or profile tables. A clean rollback script is provided in `database/rollback_biometrics_migration.sql`.

In Supabase Authentication settings, configure email confirmation to match your demo needs. For a public demo, keep confirmation enabled if possible.

Copy the Project URL from Supabase Settings > API Keys / Data API. Copy the **publishable** key (starts `sb_publishable_`). Do not use `sb_secret_` or legacy `service_role` in Streamlit.

## 2. Streamlit Community Cloud
1. Ensure this branch (`stage2-backup` or `main`) is pushed to your GitHub repository.
2. In Streamlit Community Cloud, connect your repository, branch, and select `streamlit_app.py` as the entrypoint.
3. In App Settings > Secrets, add:
   ```toml
   SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
   SUPABASE_PUBLISHABLE_KEY = "sb_publishable_..."
   ```
4. Deploy and test with synthetic demo users only.

## 3. Landing site
Deploy `landing/app.py` to a Python host that supports Flask/Gunicorn. Set `SNAPCLASS_APP_URL` to the actual Streamlit URL. Add `gunicorn` to the host start command, e.g. `gunicorn landing.app:app` from the repository root (adjust module path to the host's working directory).

## 4. Smoke tests
- Sign up as a teacher and create a subject.
- Sign up as a student and enroll using that subject code.
- Record attendance as the teacher using manual checkboxes.
- Verify the student can see only their own attendance history.
- Verify student biometric registration in the student dashboard (consent, capture, and deletion).
- Test that a student cannot create or edit another teacher's subject.
- Never use real student biometric data until privacy, consent, retention and access controls have been reviewed.
