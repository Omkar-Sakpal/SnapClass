"""
SnapClass Student Biometrics Registration UI.

Provides secure, student-only biometric enrollment for face and voice profiles,
enforcing explicit consent, client-side camera/microphone capture, verified
identity checks against authenticated Supabase Auth, and profile deletion.
"""

from datetime import datetime, timezone
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
            ts = bio_record.get("consent_timestamp", "")[:19].replace("T", " ")
            st.success(f"🟢 Consent: Active ({ts} UTC)")
        else:
            st.warning("⚪ Consent: Not provided")

    st.write("")

    # 4. Biometric Notice & Consent Agreement
    with st.expander("📋 Biometric Privacy, Purpose & Retention Notice", expanded=not (has_face and has_voice)):
        st.markdown(
            """
            **How SnapClass uses your biometric data:**
            - **Mathematical Templates Only:** Your facial features and voice characteristics are converted into **numerical mathematical vectors** (128 numbers each).
            - **No Raw Media Storage:** Your raw webcam snapshots and voice audio recordings are processed in memory and **immediately discarded**. They are never saved to disk or Supabase storage.
            - **Purpose:** Exclusively used for classroom attendance verification by teachers of subjects you are actively enrolled in.
            - **Voluntary & Alternative:** Biometric attendance is voluntary. **Manual attendance by the teacher remains fully supported** for all classes.
            - **Right to Erasure:** You can delete your biometric profile at any time below, which permanently purges your templates from the database.
            """
        )

        consent_checked = st.checkbox(
            "I consent to the collection and storage of my facial and voice mathematical templates for automated classroom attendance verification.",
            value=has_consent,
            key="student_biometric_consent_checkbox",
        )

    if not consent_checked:
        st.info("👉 Check the consent box above to unlock face and voice registration.")
        if bio_record:
            st.caption("Unchecking consent will prevent updating biometrics until re-confirmed.")
        st.divider()

    # 5. Registration Tabs (Only active when consent is checked)
    tab_face, tab_voice, tab_manage = st.tabs(
        ["📸 Face Registration", "🎙️ Voice Registration", "⚙️ Manage / Delete Profile"]
    )

    with tab_face:
        st.markdown("##### Facial Profile Registration")
        st.write("Ensure your room is well-lit, look straight into the camera, and capture a single clear photo.")

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

                        client.table("student_biometrics").upsert(update_payload).execute()
                        st.success("✅ Face profile registered successfully!")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save face profile to database: {type(e).__name__}: {e}")

    with tab_voice:
        st.markdown("##### Voice Profile Registration")
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

                        client.table("student_biometrics").upsert(update_payload).execute()
                        st.success("✅ Voice profile registered successfully!")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save voice profile to database: {type(e).__name__}: {e}")

    with tab_manage:
        st.markdown("##### Profile Management & Revocation")
        st.write(
            "You may delete your biometric profile at any time. "
            "Deleting your profile immediately purges all mathematical templates and consent timestamps from Supabase."
        )

        if not bio_record:
            st.caption("No biometric profile is currently on file for your account.")
        else:
            with st.container(border=True):
                st.markdown("⚠️ **Danger Zone: Revoke Consent & Delete Biometrics**")
                st.write(
                    "This action will permanently delete your facial and voice embeddings. "
                    "Your general student account, class enrollments, and past attendance records remain unaffected."
                )
                confirm_delete = st.button("🗑️ Delete My Biometric Profile", type="primary", key="btn_delete_biometrics")

                if confirm_delete:
                    try:
                        client.table("student_biometrics").delete().eq("student_id", student_id).execute()
                        # Invalidate in-memory session biometrics
                        st.session_state.pop("cached_biometrics", None)
                        st.success("Your biometric profile has been permanently deleted from SnapClass.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not delete biometric profile: {type(e).__name__}: {e}")

    st.divider()
