"""
SnapClass Student Biometrics Registration UI.

Provides secure, student-only biometric enrollment for face and voice profiles,
enforcing explicit consent, client-side camera/microphone capture, verified
identity checks against authenticated Supabase Auth, and profile deletion.
"""

from datetime import datetime, timezone
from typing import Tuple, Optional
import streamlit as st
from supabase import Client

from src.ai.face_engine import extract_face_embedding
from src.ai.voice_engine import extract_voice_embedding


def _verify_authenticated_student(client: Client, student_id: int) -> bool:
    """
    Ensure the student_id strictly matches the authenticated Supabase user ID.
    Never trust unverified browser parameters.
    """
    auth_uid = st.session_state.get("user_id")
    if not auth_uid or not student_id:
        return False

    try:
        res = (
            client.table("students")
            .select("student_id")
            .eq("student_id", student_id)
            .eq("auth_user_id", auth_uid)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def load_student_biometrics(client: Client, student_id: int):
    """Fetch existing biometric registration record for the authenticated student."""
    try:
        res = (
            client.table("student_biometrics")
            .select("student_id, face_embedding, voice_embedding, consent_given, consent_timestamp, updated_at")
            .eq("student_id", student_id)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception as exc:
        st.warning(f"Could not load biometric status: {type(exc).__name__}: {exc}")
        return None


def delete_student_biometrics(client: Client, student_id: int) -> Tuple[bool, Optional[str]]:
    """
    Revokes consent and deletes the student's biometric record from public.student_biometrics.
    Verifies that the record is truly removed from the database before returning.

    Returns:
        (success: bool, error_message: Optional[str])
    """
    if not _verify_authenticated_student(client, student_id):
        return False, "Authentication security error: Cannot verify student identity."

    try:
        # 1. Execute delete operation under authenticated student RLS
        client.table("student_biometrics").delete().eq("student_id", student_id).execute()

        # 2. Verify that the record is truly absent
        check = (
            client.table("student_biometrics")
            .select("student_id")
            .eq("student_id", student_id)
            .maybe_single()
            .execute()
        )
        if check and check.data:
            return False, "Deletion could not be verified; the biometric profile is still present in the database."

        return True, None
    except Exception as exc:
        return False, f"Database error during profile deletion: {type(exc).__name__}: {str(exc)}"


def render_student_biometrics_section(client: Client, student_id: int) -> None:
    """
    Renders the Biometric Registration section on the student dashboard.
    """
    # 1. Security Check: Authenticate student identity
    if not _verify_authenticated_student(client, student_id):
        st.error("Authentication security error: Cannot verify student identity. Please sign in again.")
        return

    st.markdown("### 🧬 Biometric Registration (AI Attendance)")
    st.caption(
        "Register your face and voice profiles to participate in automated AI attendance. "
        "Participation is completely voluntary."
    )

    # 2. Query current profile state
    bio_record = load_student_biometrics(client, student_id)
    has_face = bool(bio_record and bio_record.get("face_embedding"))
    has_voice = bool(bio_record and bio_record.get("voice_embedding"))
    has_consent = bool(bio_record and bio_record.get("consent_given"))

    # 3. Status Badges
    st.markdown("#### Current Profile Status")
    col1, col2, col3 = st.columns(3)
    with col1:
        if has_face:
            st.success("🟢 Face Profile: Registered")
        else:
            st.info("⚪ Face Profile: Not registered")
    with col2:
        if has_voice:
            st.success("🟢 Voice Profile: Registered")
        else:
            st.info("⚪ Voice Profile: Not registered")
    with col3:
        if has_consent:
            ts = str(bio_record.get("consent_timestamp", ""))[:19].replace("T", " ")
            st.success(f"🟢 Consent: Active ({ts} UTC)")
        else:
            st.warning("⚪ Consent: Not provided")

    st.write("")

    # 4. Biometric Notice & Consent Agreement
    with st.expander("📋 Biometric Privacy, Purpose & Retention Notice", expanded=not (has_face and has_voice)):
        st.markdown(
            """
            **How SnapClass handles biometric data:**
            - **Mathematical Descriptors Only:** Your webcam snapshot and audio recording are processed by the application to compute numerical embedding vectors (128 numbers for face, normalized embedding for voice). Only these mathematical vectors and consent timestamps are stored in the database.
            - **No Raw Media in Database:** Raw photos and voice recordings are not stored in the database or Supabase storage buckets.
            - **Attendance Purpose Only:** Biometric data is used solely for classroom attendance verification for subjects in which you are enrolled.
            - **Voluntary Participation:** Biometric registration is completely optional. **Manual attendance by the teacher is always supported** as a standard alternative.
            - **Explicit Revocation:** You can revoke consent and delete your biometric descriptors at any time using the Manage / Delete Profile tab below.
            """
        )

        consent_checked = st.checkbox(
            "I consent to the collection and storage of my facial and voice mathematical templates for automated classroom attendance verification.",
            value=has_consent,
            key="student_biometric_consent_checkbox",
        )

    # Explicit handling of unchecking consent when a profile already exists
    if has_consent and not consent_checked:
        st.warning(
            "⚠️ **Note on Consent & Existing Templates:** You currently have an active biometric profile on file. "
            "Unchecking the box above prevents registering new templates, but does NOT revoke previously granted consent "
            "or delete your stored mathematical templates. To permanently revoke consent and delete your templates, "
            "use the explicit **Revoke Consent & Delete Biometrics** flow in the Manage / Delete tab below."
        )
    elif not consent_checked:
        st.info("👉 Check the consent box above to unlock face and voice registration.")
        st.divider()

    # 5. Registration Tabs
    tab_face, tab_voice, tab_manage = st.tabs(
        ["📸 Face Registration", "🎙️ Voice Registration", "⚙️ Manage / Delete Profile"]
    )

    with tab_face:
        st.markdown("##### Facial Profile Registration")
        st.write(
            "Captures a frontal webcam snapshot to extract a 128-dimensional facial descriptor using dlib ResNet. "
            "Ensure adequate frontal lighting, look straight into the camera, and ensure only one person is in frame."
        )

        if not consent_checked:
            st.warning("Please check the consent agreement above before capturing your face.")
        else:
            face_cam = st.camera_input("Capture face snapshot", key="face_registration_camera")
            if face_cam is not None:
                with st.spinner("Analyzing facial features and extracting 128-d descriptor..."):
                    embedding, error = extract_face_embedding(face_cam)

                if error:
                    st.error(f"❌ {error}")
                elif embedding:
                    now_utc = datetime.now(timezone.utc).isoformat()
                    try:
                        # Prepare row with consent guarantees enforced
                        update_payload = {
                            "student_id": student_id,
                            "face_embedding": embedding,
                            "consent_given": True,
                            "consent_timestamp": now_utc,
                            "updated_at": now_utc,
                        }
                        # If existing record had voice, preserve it
                        if bio_record and bio_record.get("voice_embedding"):
                            update_payload["voice_embedding"] = bio_record["voice_embedding"]

                        res = client.table("student_biometrics").upsert(update_payload).execute()
                        if res and res.data:
                            st.success("✅ Face profile registered successfully!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to verify that the face profile was saved. Please try again.")
                    except Exception as e:
                        st.error(f"Failed to save face profile to database: {type(e).__name__}: {e}")

    with tab_voice:
        st.markdown("##### Voice Profile Registration")
        st.warning(
            "⚠️ **Experimental Acoustic Fallback Notice:**\n\n"
            "On cloud environments without GPU acceleration, voice feature extraction uses a lightweight SciPy spectral fallback. "
            "This extracts acoustic frequency and energy distributions, but **is not suitable for reliable individual speaker identification**. "
            "Biometric attendance must always be reviewed and confirmed by the teacher."
        )
        student_display_name = st.session_state.get("display_name", "Student")
        st.info(f"**Standard enrollment phrase:** Please read aloud clearly:\n\n> *\"I am present, my name is {student_display_name}.\"*")

        if not consent_checked:
            st.warning("Please check the consent agreement above before recording your voice.")
        else:
            voice_audio = st.audio_input("Record your voice phrase", key="voice_registration_audio")
            if voice_audio is not None:
                with st.spinner("Analyzing vocal frequencies and extracting speaker embedding..."):
                    embedding, error = extract_voice_embedding(voice_audio)

                if error:
                    st.error(f"❌ {error}")
                elif embedding:
                    now_utc = datetime.now(timezone.utc).isoformat()
                    try:
                        update_payload = {
                            "student_id": student_id,
                            "voice_embedding": embedding,
                            "consent_given": True,
                            "consent_timestamp": now_utc,
                            "updated_at": now_utc,
                        }
                        # If existing record had face, preserve it
                        if bio_record and bio_record.get("face_embedding"):
                            update_payload["face_embedding"] = bio_record["face_embedding"]

                        res = client.table("student_biometrics").upsert(update_payload).execute()
                        if res and res.data:
                            st.success("✅ Voice profile registered successfully!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to verify that the voice profile was saved. Please try again.")
                    except Exception as e:
                        st.error(f"Failed to save voice profile to database: {type(e).__name__}: {e}")

    with tab_manage:
        st.markdown("##### Profile Management & Revocation")
        st.write(
            "You may revoke consent and delete your biometric profile at any time. "
            "Deleting your profile permanently removes all mathematical templates and consent timestamps from Supabase."
        )

        if not bio_record:
            st.caption("No biometric profile is currently on file for your account.")
        else:
            with st.container(border=True):
                st.markdown("⚠️ **Revoke Consent & Delete Biometric Profile**")
                st.write(
                    "This action permanently revokes your biometric consent and deletes your stored facial and "
                    "voice mathematical descriptors. Your student account, subject enrollments, and past attendance records are unaffected."
                )

                confirm_revoke = st.checkbox(
                    "I confirm that I want to revoke my consent and permanently delete my stored biometric templates.",
                    key="confirm_revoke_biometrics_checkbox",
                )

                if st.button("🗑️ Permanently Delete Biometric Profile", type="primary", disabled=not confirm_revoke, key="btn_delete_biometrics"):
                    with st.spinner("Deleting biometric profile and verifying database removal..."):
                        success, err = delete_student_biometrics(client, student_id)

                    if success:
                        st.session_state.pop("cached_biometrics", None)
                        st.success("✅ Your biometric profile and consent records have been permanently deleted.")
                        st.rerun()
                    else:
                        st.error(f"❌ Deletion failed: {err}")

    st.divider()
