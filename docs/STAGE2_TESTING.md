# Stage 2: Student Biometric Registration — Testing & Verification Guide

This document describes how to test the student biometric registration workflow implemented in Stage 2.

---

## 1. Prerequisites & Environment Setup

1. **Working Directory**:
   Run all commands from the application root:
   ```bash
   cd SnapClass-cloud-starter
   ```

2. **Verify Dependencies**:
   Ensure dependencies from `requirements.txt` are installed:
   ```bash
   pip install -r requirements.txt
   ```
   *(On Windows, `dlib-bin` provides pre-compiled binaries; on Linux / Streamlit Cloud, `packages.txt` provides system libraries).*

3. **Verify Secrets**:
   Confirm `.streamlit/secrets.toml` contains your active Supabase URL and publishable key:
   ```toml
   SUPABASE_URL = "https://your-ref.supabase.co"
   SUPABASE_PUBLISHABLE_KEY = "your-publishable-key"
   ```

---

## 2. Automated Test Execution

Run the automated test suite covering face feature extraction, voice embedding, silence/short audio rejection, and auth verification:

```bash
python -m unittest tests/test_stage2_biometrics.py -v
```

**Expected Result**:
```text
test_dlib_models_available ... ok
test_extract_face_embedding_no_face ... ok
test_extract_face_embedding_success ... ok
test_face_comparison_identity ... ok
test_decode_wav_bytes ... ok
test_extract_voice_embedding_success ... ok
test_reject_silent_audio ... ok
test_reject_too_short_audio ... ok
test_voice_comparison_identity ... ok
test_unverified_student_rejected ... ok

----------------------------------------------------------------------
Ran 10 tests in ~2.9s

OK
```

---

## 3. Manual Local End-to-End Walkthrough

### Step 1: Launch the Application
```bash
streamlit run streamlit_app.py
```

### Step 2: Sign In as a Student
1. Open the local URL (e.g. `http://localhost:8501`).
2. If already logged in as a Teacher, click **Sign out** in the sidebar.
3. Sign in with an existing student account, or click **Create account**, choose **I am a: Student**, and complete registration.

### Step 3: Inspect the Student Dashboard
1. Notice the two tabs on the student dashboard:
   - **📊 My Attendance**: Displays existing subject join form and attendance logs (100% preserved).
   - **🧬 Biometric Registration**: The new Stage 2 biometric management interface.
2. Click **🧬 Biometric Registration**.
3. Notice the status badges:
   - `⚪ Face Profile: Not registered`
   - `⚪ Voice Profile: Not registered`
   - `⚪ Consent: Not provided`

### Step 4: Review and Provide Consent
1. Open the **📋 Biometric Privacy, Purpose & Retention Notice** expander.
2. Read the explanation regarding mathematical vectors, zero raw media storage, and manual attendance alternatives.
3. Check the consent box:
   `[x] I consent to the collection and storage of my facial and voice mathematical templates...`
4. Notice that the registration tabs unlock.

### Step 5: Register Face Profile
1. Navigate to the **📸 Face Registration** tab.
2. Grant browser camera permission when prompted.
3. Look directly at the camera in a well-lit setting and take a snapshot.
4. The system validates that exactly one face is present, extracts the 128-d descriptor, and saves it to `student_biometrics` via Supabase RLS.
5. Notice the confirmation balloon animation and the status update: `🟢 Face Profile: Registered`.

### Step 6: Register Voice Profile
1. Navigate to the **🎙️ Voice Registration** tab.
2. Grant microphone permission.
3. Read the standard prompt: *"I am present, my name is [Your Name]"*.
4. Click record, speak for 1–2 seconds, and stop recording.
5. The system validates speech duration and energy, computes the normalized voice vector, and updates `student_biometrics`.
6. Notice the status badge update: `🟢 Voice Profile: Registered`.

### Step 7: Test Profile Erasure (Revoke Consent)
1. Navigate to the **⚙️ Manage / Delete Profile** tab.
2. Review the Danger Zone notice.
3. Click **🗑️ Delete My Biometric Profile**.
4. The application executes a `DELETE` on `student_biometrics` using the student's authenticated RLS policy.
5. Observe the status badges immediately reset to `⚪ Not registered`.
6. Confirm that your student account, joined subjects, and past attendance records remain completely intact.
