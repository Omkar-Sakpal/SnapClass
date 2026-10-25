# Deployment guide

## 1. Supabase
Your current project already has the five base tables. In Supabase SQL Editor, review and run `database/supabase_auth_migration.sql`. It adds Auth-linked profile fields and policies without dropping tables. If any statement errors, stop and share the error; do not keep rerunning partial edits blindly.

In Supabase Authentication settings, configure email confirmation to match your demo needs. For a public demo, keep confirmation enabled if possible.

Copy the Project URL from Supabase Settings > API Keys / Data API. Copy the **publishable** key (starts `sb_publishable_`). Do not use `sb_secret_` or legacy `service_role` in Streamlit.

## 2. Streamlit Community Cloud
1. Put this folder in a GitHub repository.
2. Create an app at Streamlit Community Cloud, selecting `streamlit_app.py`.
3. In App Settings > Secrets, add:
   `SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"`
   `SUPABASE_PUBLISHABLE_KEY = "sb_publishable_..."`
4. Deploy and test with synthetic demo users only.

## 3. Landing site
Deploy `landing/app.py` to a Python host that supports Flask/Gunicorn. Set `SNAPCLASS_APP_URL` to the actual Streamlit URL. Add `gunicorn` to the host start command, e.g. `gunicorn landing.app:app` from the repository root (adjust module path to the host's working directory).

## 4. Smoke tests
- Sign up as a teacher and create a subject.
- Sign up as a student and enroll using that subject code.
- Record attendance as the teacher.
- Verify the student can see only their own attendance.
- Test that a student cannot create or edit another teacher's subject.
- Never use real student biometric data until privacy, consent, retention and access controls have been reviewed.

## Scope limitation
This starter does not contain the original face-recognition or voice-recognition pipelines because the original app ZIP was not available in the current workspace. It provides a cloud-authenticated baseline to connect and test. Restore the original source before claiming those features are integrated.
