# SnapClass

SnapClass is a cloud-ready college attendance application built with **Streamlit** and **Supabase**, featuring authenticated teacher and student workspaces, subject enrollment, manual attendance recording, attendance history editing, and voluntary student biometric registration (**Stage 2**).

## Key Features

- **Supabase Authentication & RLS**: Role-based access control separating Teacher and Student dashboards with row-level security policies enforcing identity boundaries.
- **Teacher Workspace**: Create subjects, manage class codes, view enrolled rosters, record manual attendance (checkbox grid), and correct past attendance dates. Manual attendance remains the ground truth and is always supported.
- **Student Workspace**: Join classes using unique subject codes, view personal attendance logs and overall attendance rate.
- **Student Biometric Registration (Stage 2)**:
  - **Explicit Consent**: Students must review the privacy and data retention notice and check an agreement box before camera/mic captures unlock.
  - **Independent Modalities**: Separate registration tabs for facial descriptors and voice embeddings.
  - **Privacy & Storage**: Raw photos and audio clips are processed strictly in memory and discarded immediately. Only numerical mathematical vectors (128-d face descriptors, normalized voice embeddings) are stored in `public.student_biometrics`.
  - **Right to Erasure / Revocation**: Students can delete their biometric profile at any time via the "Manage / Delete Profile" tab, permanently purging their templates from the database via Supabase RLS.
  - **Manual Attendance Alternative**: Biometric enrollment is voluntary. Manual attendance by the teacher is always available as an alternative.

## Biometric Matching Reliability & Limitations

- **Face Recognition**: Uses `dlib` ResNet to extract 128-dimensional Euclidean descriptors. Suitable for comparing clean frontal student webcam captures against enrolled templates in good lighting. However, extreme angles, occlusions, and uneven illumination degrade resemblance scores.
- **Voice Recognition**: Supports Resemblyzer (256-d deep learning) when PyTorch is available. On resource-constrained hosts, it falls back to a calibrated 128-d spectral-temporal feature vector.
  > [!IMPORTANT]
  > **Voice Limitation**: The SciPy spectral-temporal fallback extracts acoustic frequency power distributions. **It is an acoustic signal descriptor, not a reliable method for identifying individual human speakers.** Biometric detections must always be treated as candidate suggestions requiring human teacher confirmation, never as automated identity determinations.

## Repository Contents

- `streamlit_app.py`: Streamlit entrypoint with Supabase Auth, teacher dashboard, and student dashboard with attendance history and biometric registration tabs.
- `src/ai/`: Face and voice feature extraction engines with lazy loading and error handling.
- `src/components/`: Modular UI components for student biometric consent, capture, and deletion.
- `database/`: SQL migrations and rollback scripts for Supabase Auth, base schema, and `student_biometrics`.
- `landing/app.py`: Lightweight Flask marketing landing page.
- `packages.txt`: System-level build packages (`cmake`, `build-essential`, `libopenblas-dev`, `ffmpeg`) for Linux cloud containers.
- `requirements.txt`: Python package specifications with pinned CPU-friendly dependencies.
- `docs/`: Deployment guide, testing instructions, and architecture references.
- `tests/`: Automated unit and integration test suite.

## Local Run

1. Create and activate a Python 3.12 virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and provide your Supabase URL and publishable key. Never place service-role keys or database passwords in Streamlit configuration.
4. Run migrations in Supabase SQL Editor (`database/supabase_auth_migration.sql` and `database/supabase_biometrics_migration.sql`).
5. Launch the application:
   ```bash
   streamlit run streamlit_app.py
   ```

## Deployment Status Note

This branch (`stage2-backup`) contains the verified Stage 2 implementation. Note that the live Streamlit Community Cloud deployment must be updated and built from this branch before Stage 2 features appear in production.
