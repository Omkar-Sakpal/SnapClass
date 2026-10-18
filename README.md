# SnapClass Cloud Starter

This is a **new cloud-ready starter scaffold**, not a copy of the original SnapClass AI/biometric application. The original app source ZIPs were not available in the current workspace, so face and voice recognition functionality has not been copied or claimed as preserved.

## Contents
- `streamlit_app.py`: Streamlit app with Supabase Auth, teacher subject creation, student enrollment, and attendance viewing/recording.
- `landing/app.py`: simple Flask landing page that links to the Streamlit app.
- `database/supabase_auth_migration.sql`: migration for the five tables already created in your Supabase project, enabling Supabase Auth and RLS policies.
- `requirements.txt`: Python dependencies.
- `.streamlit/secrets.toml.example`: placeholder secrets template.
- `docs/DEPLOYMENT.md`: deployment instructions.

## Important
Do not place a Supabase secret/service-role key in this app. Use the project URL and publishable key only. The migration is designed for the existing tables created from the earlier schema. Review it before running. It adds Auth-linked profile IDs and RLS policies.

## Local run
1. Create a virtual environment.
2. Install `requirements.txt`.
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in the Project URL and publishable key.
4. Run the migration in Supabase SQL Editor.
5. Run `streamlit run streamlit_app.py`.

For deployment, add the same secrets in Streamlit Community Cloud settings instead of committing `secrets.toml`.
