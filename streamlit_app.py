import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timezone, date, time
from src.components.student_biometrics_ui import render_student_biometrics_section
from src.ai.face_engine import (
    extract_face_embedding,
    compare_faces,
    is_sface_profile,
    is_legacy_profile,
)

st.set_page_config(
    page_title="SnapClass | Attendance",
    page_icon="🎓",
    layout="wide",
)


def make_client(url: str, key: str) -> Client:
    return create_client(url, key)


def get_client() -> Client:
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_PUBLISHABLE_KEY", "")
    if not url or not key or "YOUR_PROJECT_REF" in url or "REPLACE_ME" in key:
        st.error(
            "Supabase is not configured. Add SUPABASE_URL and "
            "SUPABASE_PUBLISHABLE_KEY in Streamlit secrets."
        )
        st.stop()
    return make_client(url, key)


def set_authenticated_session(client: Client, session) -> None:
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["user_id"] = session.user.id
    st.session_state["client"] = client


def active_client() -> Client:
    client = get_client()
    access = st.session_state.get("access_token")
    refresh = st.session_state.get("refresh_token")
    if access and refresh:
        try:
            client.auth.set_session(access, refresh)
        except Exception:
            for key in [
                "access_token", "refresh_token", "user_id", "role",
                "profile_id", "email", "display_name", "client",
            ]:
                st.session_state.pop(key, None)
    return client


def sign_out() -> None:
    try:
        client = st.session_state.get("client")
        if client:
            client.auth.sign_out()
    except Exception:
        pass
    for key in [
        "access_token", "refresh_token", "user_id", "role",
        "profile_id", "email", "display_name", "client",
    ]:
        st.session_state.pop(key, None)
    st.rerun()


def login_ui(client: Client) -> None:
    st.markdown("<div class='snap-auth-brand'>✦ SnapClass</div>", unsafe_allow_html=True)
    st.title("Welcome to SnapClass")
    st.caption("Sign in to continue to your attendance workspace, or create a new account.")
    if st.button("← Back to home", key="back_to_home"):
        st.session_state["snap_page"] = "home"
        st.rerun()
    login_tab, signup_tab = st.tabs(["Sign in", "Create account"])
    with login_tab:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Sign in", type="primary", use_container_width=True
            )
        if submitted:
            try:
                response = client.auth.sign_in_with_password(
                    {"email": email.strip(), "password": password}
                )
                if not response.session:
                    st.error(
                        "Sign-in did not return a session. Check whether "
                        "email confirmation is required."
                    )
                else:
                    set_authenticated_session(client, response.session)
                    st.session_state["email"] = email.strip()
                    st.rerun()
            except Exception as e:
                st.error(f"Sign-in failed: {type(e).__name__}: {e}")
    with signup_tab:
        with st.form("signup"):
            name = st.text_input("Full name")
            email = st.text_input("Email address", key="signup_email")
            password = st.text_input(
                "Password (at least 8 characters)", type="password",
                key="signup_password",
            )
            role = st.selectbox("I am a", ["Student", "Teacher"])
            submitted = st.form_submit_button(
                "Create account", type="primary", use_container_width=True
            )
        if submitted:
            if not name.strip() or not email.strip() or len(password) < 8:
                st.warning("Enter your name, email, and a password of at least 8 characters.")
                return
            try:
                response = client.auth.sign_up({"email": email.strip(), "password": password})
                user = getattr(response, "user", None)
                session = getattr(response, "session", None)
                if not user:
                    st.error("Supabase did not return a user for this signup.")
                    return
                if not session:
                    st.success(
                        "Account created. Verify your email if prompted, then sign in. "
                        "If no profile is created automatically, sign in and use the matching account/profile setup."
                    )
                    return
                set_authenticated_session(client, session)
                uid = user.id
                if role == "Teacher":
                    result = client.table("teachers").insert({
                        "username": email.strip(), "password": None,
                        "name": name.strip(), "auth_user_id": uid,
                    }).execute()
                    st.session_state["role"] = "Teacher"
                    st.session_state["profile_id"] = result.data[0]["teacher_id"]
                else:
                    result = client.table("students").insert({
                        "name": name.strip(), "email": email.strip(),
                        "auth_user_id": uid,
                    }).execute()
                    st.session_state["role"] = "Student"
                    st.session_state["profile_id"] = result.data[0]["student_id"]
                st.session_state["email"] = email.strip()
                st.session_state["display_name"] = name.strip()
                st.rerun()
            except Exception as e:
                st.error(f"Account creation failed: {type(e).__name__}: {e}")


def recover_profile(client: Client) -> bool:
    """Find the app profile for the signed-in Supabase Auth user."""
    uid = st.session_state.get("user_id")
    if not uid:
        return False
    for role, table, id_column in [
        ("Teacher", "teachers", "teacher_id"),
        ("Student", "students", "student_id"),
    ]:
        try:
            result = client.table(table).select("*").eq("auth_user_id", uid).limit(1).execute()
            if result.data:
                profile = result.data[0]
                st.session_state["role"] = role
                st.session_state["profile_id"] = profile[id_column]
                st.session_state["display_name"] = profile.get("name", "")
                st.session_state["email"] = profile.get("email") or st.session_state.get("email") or ""
                return True
        except Exception:
            continue
    return False


def load_teacher_subjects(client: Client):
    return (
        client.table("subjects").select("*")
        .eq("teacher_id", st.session_state["profile_id"])
        .order("subject_id", desc=True).execute().data
    )


def load_enrolled_students(client: Client, subject_id):
    enrollments = (
        client.table("subject_students").select("student_id")
        .eq("subject_id", subject_id).execute().data
    )
    student_ids = [row["student_id"] for row in enrollments]
    if not student_ids:
        return []
    return (
        client.table("students").select("student_id,name,email")
        .in_("student_id", student_ids).order("name").execute().data
    )


def get_active_session(subject_id: int):
    """Retrieve current active attendance session for the subject from session state."""
    session_key = f"active_session_{subject_id}"
    return st.session_state.get(session_key)


def start_attendance_session(client: Client, teacher_id: int, subject_id: int) -> dict:
    """Initialize a new active attendance session with a unique ID and UTC timestamp."""
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    session_id = f"SES-{subject_id}-{now_utc.strftime('%Y%m%d-%H%M%S')}"
    session_data = {
        "session_id": session_id,
        "subject_id": subject_id,
        "teacher_id": teacher_id,
        "timestamp": now_utc.isoformat(),
        "status": "active",
        "confirmed_student_ids": set(),
    }
    session_key = f"active_session_{subject_id}"
    st.session_state[session_key] = session_data

    # Optional persistence to attendance_sessions if migration was applied in Supabase
    try:
        client.table("attendance_sessions").insert({
            "session_id": session_id,
            "subject_id": subject_id,
            "teacher_id": teacher_id,
            "started_at": now_utc.isoformat(),
            "status": "active",
        }).execute()
    except Exception:
        pass

    return session_data


def end_attendance_session(client: Client, subject_id: int):
    """End the current active attendance session and archive it."""
    session_key = f"active_session_{subject_id}"
    active = st.session_state.pop(session_key, None)
    if active:
        active["status"] = "completed"
        active["ended_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        st.session_state[f"last_completed_session_{subject_id}"] = active
        try:
            client.table("attendance_sessions").update({
                "status": "completed",
                "ended_at": active["ended_at"],
            }).eq("session_id", active["session_id"]).execute()
        except Exception:
            pass
    st.session_state.pop(f"candidate_match_{subject_id}", None)
    return active


def record_attendance_entry(
    client: Client, student_id: int, subject_id: int, timestamp: str, is_present: bool = True
) -> tuple[bool, str | None]:
    """
    Safely saves or updates an attendance record in attendance_logs,
    preventing duplicate entries for the same student, subject, and session timestamp.
    """
    try:
        existing = (
            client.table("attendance_logs")
            .select("attendance_id, is_present")
            .eq("student_id", student_id)
            .eq("subject_id", subject_id)
            .eq("timestamp", timestamp)
            .limit(1)
            .execute()
        )
        if existing and existing.data:
            att_id = existing.data[0]["attendance_id"]
            client.table("attendance_logs").update({
                "is_present": is_present
            }).eq("attendance_id", att_id).execute()
        else:
            client.table("attendance_logs").insert({
                "student_id": student_id,
                "subject_id": subject_id,
                "timestamp": timestamp,
                "is_present": is_present,
            }).execute()
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def record_batch_attendance(
    client: Client, student_statuses: list[dict], subject_id: int, timestamp: str
) -> tuple[int, list[str]]:
    """
    Records attendance for multiple students, preventing duplicate entries for the
    same student, subject, and session timestamp.
    """
    errors = []
    saved_count = 0
    try:
        existing_res = (
            client.table("attendance_logs")
            .select("attendance_id, student_id, is_present")
            .eq("subject_id", subject_id)
            .eq("timestamp", timestamp)
            .execute()
        )
        existing_map = {row["student_id"]: row for row in (existing_res.data or [])}
    except Exception:
        existing_map = {}

    to_insert = []
    for item in student_statuses:
        sid = item["student_id"]
        is_p = item["is_present"]
        if sid in existing_map:
            if existing_map[sid]["is_present"] != is_p:
                try:
                    client.table("attendance_logs").update({
                        "is_present": is_p
                    }).eq("attendance_id", existing_map[sid]["attendance_id"]).execute()
                    saved_count += 1
                except Exception as exc:
                    errors.append(f"Student {sid}: {type(exc).__name__}: {exc}")
            else:
                saved_count += 1
        else:
            to_insert.append({
                "student_id": sid,
                "subject_id": subject_id,
                "timestamp": timestamp,
                "is_present": is_p,
            })

    if to_insert:
        try:
            client.table("attendance_logs").insert(to_insert).execute()
            saved_count += len(to_insert)
        except Exception as exc:
            errors.append(f"Batch insert error: {type(exc).__name__}: {exc}")

    return saved_count, errors


def match_face_to_enrolled_students(
    client: Client, face_input, enrolled_students: list[dict], threshold: float = 0.60
) -> tuple[dict | None, float | None, str | None]:
    """
    Extracts face embedding from face_input and compares against registered,
    consented biometrics for students enrolled in the subject.
    Filters strictly for OpenCV SFace profiles and ignores incompatible legacy profiles.
    Returns (matched_student_dict, distance, error_message).
    Only returns candidate match if distance <= threshold.
    """
    if not enrolled_students:
        return None, None, "No students are enrolled in this subject."

    emb, err = extract_face_embedding(face_input)
    if err or not emb:
        return None, None, err or "Could not extract facial features."

    student_ids = [s["student_id"] for s in enrolled_students]
    try:
        bio_records = (
            client.table("student_biometrics")
            .select("student_id, face_embedding, consent_given")
            .in_("student_id", student_ids)
            .eq("consent_given", True)
            .execute()
            .data
        )
    except Exception as exc:
        return None, None, f"Could not load biometric profiles: {type(exc).__name__}: {exc}"

    if not bio_records:
        return None, None, "No enrolled students have registered a consented facial biometric profile."

    compatible_bios = [b for b in bio_records if is_sface_profile(b.get("face_embedding"))]
    legacy_bios = [b for b in bio_records if is_legacy_profile(b.get("face_embedding"))]

    if not compatible_bios:
        if legacy_bios:
            return (
                None,
                None,
                f"{len(legacy_bios)} enrolled student(s) have legacy face profiles and must re-register using the OpenCV SFace engine before face matching can identify them. Manual attendance remains available.",
            )
        return None, None, "No enrolled students have registered a compatible SFace facial biometric profile."

    best_match = None
    min_dist = float("inf")

    student_map = {s["student_id"]: s for s in enrolled_students}
    for bio in compatible_bios:
        profile_emb = bio.get("face_embedding")
        if not profile_emb:
            continue
        dist = compare_faces(emb, profile_emb)
        if dist < min_dist:
            min_dist = dist
            best_match = student_map.get(bio["student_id"])

    if best_match and min_dist <= threshold:
        return best_match, min_dist, None
    elif best_match:
        return None, min_dist, f"Nearest enrolled student ({best_match['name']}) had match distance {min_dist:.3f}, which exceeds threshold ({threshold})."
    else:
        return None, None, "No enrolled students with registered SFace embeddings found."


def teacher_dashboard(client: Client) -> None:
    st.title("Teacher dashboard")
    st.write("Create a subject, record attendance, and correct records for any previous date.")

    with st.expander("Create subject", expanded=True):
        with st.form("create_subject"):
            subject_name = st.text_input("Subject name")
            subject_code = st.text_input("Unique subject code", help="Choose a short code students can enter.")
            section = st.text_input("Section / class", value="A")
            create = st.form_submit_button("Create subject", type="primary")
        if create:
            if not subject_name.strip() or not subject_code.strip() or not section.strip():
                st.warning("Complete all fields.")
            else:
                try:
                    client.table("subjects").insert({
                        "name": subject_name.strip(),
                        "subject_code": subject_code.strip().upper(),
                        "section": section.strip(),
                        "teacher_id": st.session_state["profile_id"],
                    }).execute()
                    st.success("Subject created.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not create subject: {type(e).__name__}: {e}")

    try:
        subjects = load_teacher_subjects(client)
    except Exception as e:
        st.error(f"Could not load your subjects: {type(e).__name__}: {e}")
        return
    if not subjects:
        st.info("No subjects yet. Create one above.")
        return

    subject_map = {
        f'{subject["name"]} — {subject["section"]} ({subject["subject_code"]})': subject
        for subject in subjects
    }
    selected_label = st.selectbox("Choose a subject", list(subject_map), key="teacher_subject")
    subject = subject_map[selected_label]
    subject_id = subject["subject_id"]

    active_session = get_active_session(subject_id)

    st.markdown("#### ⏱️ Attendance Session")
    if not active_session:
        col_s1, col_s2 = st.columns([2, 3])
        with col_s1:
            if st.button("▶️ Start Attendance Session", type="primary", key=f"btn_start_session_{subject_id}"):
                sess = start_attendance_session(client, st.session_state["profile_id"], subject_id)
                st.success(f"Started attendance session: {sess['session_id']}")
                st.rerun()
        with col_s2:
            st.caption("Start an active session to coordinate manual and face-assisted attendance with unique timestamping.")
    else:
        with st.container(border=True):
            col_info, col_btn = st.columns([3, 1])
            with col_info:
                st.markdown(f"🟢 **Active Session:** `{active_session['session_id']}`")
                st.caption(f"Started: {active_session['timestamp']} UTC · Subject: {subject['name']} ({subject['section']})")
                num_confirmed = len(active_session.get("confirmed_student_ids", set()))
                if num_confirmed > 0:
                    st.info(f"Verified & recorded in this session: **{num_confirmed}** student(s)")
            with col_btn:
                if st.button("⏹️ End Attendance Session", type="secondary", key=f"btn_end_session_{subject_id}"):
                    ended = end_attendance_session(client, subject_id)
                    st.info(f"Attendance session {ended['session_id'] if ended else ''} ended.")
                    st.rerun()

    st.subheader("Enrolled students")
    try:
        students = load_enrolled_students(client, subject_id)
    except Exception as e:
        st.error(f"Could not load enrolled students: {type(e).__name__}: {e}")
        return
    if not students:
        st.info("No students enrolled yet.")
        return

    tab_record, tab_face, tab_update = st.tabs([
        "📝 Record attendance",
        "📸 Face-assisted attendance",
        "✏️ Update attendance"
    ])
    with tab_record:
        if active_session:
            st.caption(f"Recording for active session `{active_session['session_id']}`. Check the students who are present. Unchecked students will be recorded absent.")
        else:
            st.caption("Check the students who are present. Unchecked students will be recorded absent.")

        with st.form(f"record_attendance_{subject_id}"):
            present_ids = []
            confirmed_set = active_session.get("confirmed_student_ids", set()) if active_session else set()
            for student in students:
                is_prechecked = student["student_id"] in confirmed_set
                if st.checkbox(
                    f'{student["name"]} ({student.get("email") or "no email"})',
                    value=is_prechecked,
                    key=f'record_present_{subject_id}_{student["student_id"]}',
                ):
                    present_ids.append(student["student_id"])
            save = st.form_submit_button("Save attendance", type="primary")

        if save:
            if not active_session:
                active_session = start_attendance_session(client, st.session_state["profile_id"], subject_id)
            session_ts = active_session["timestamp"]

            student_statuses = [
                {"student_id": s["student_id"], "is_present": s["student_id"] in present_ids}
                for s in students
            ]
            saved_count, errors = record_batch_attendance(client, student_statuses, subject_id, session_ts)
            if errors:
                st.error("Some records could not be saved:\n" + "\n".join(errors))
            if saved_count:
                for s in students:
                    if s["student_id"] in present_ids and active_session:
                        active_session.setdefault("confirmed_student_ids", set()).add(s["student_id"])
                st.success(f"Attendance saved for {saved_count} students in session `{active_session['session_id']}`.")
                st.rerun()

    with tab_face:
        st.markdown("##### 📸 Face-Assisted Attendance (AI Verification)")
        st.write(
            "Quickly verify student attendance by comparing a webcam snapshot against registered, "
            "consented facial templates. **Attendance is never recorded automatically**; the teacher "
            "must confirm candidate matches."
        )

        if not active_session:
            st.info("👉 Please start an active attendance session above before using face-assisted attendance.")
        else:
            face_cam = st.camera_input("Capture student face", key=f"teacher_face_cam_{subject_id}")
            if face_cam is not None:
                if st.button("🔍 Identify Enrolled Student", type="primary", key=f"btn_identify_{subject_id}"):
                    with st.spinner("Comparing facial features against registered student profiles..."):
                        matched, dist, err = match_face_to_enrolled_students(client, face_cam, students, threshold=0.60)
                    if err:
                        st.warning(f"Identification notice: {err}")
                        st.session_state.pop(f"candidate_match_{subject_id}", None)
                    elif matched:
                        st.session_state[f"candidate_match_{subject_id}"] = {
                            "student": matched,
                            "distance": dist,
                        }
                        st.rerun()

            candidate_data = st.session_state.get(f"candidate_match_{subject_id}")
            if candidate_data:
                c_student = candidate_data["student"]
                c_dist = candidate_data["distance"]
                with st.container(border=True):
                    st.markdown(f"### 👤 Candidate Match: **{c_student['name']}**")
                    st.write(f"Email: `{c_student.get('email') or 'No email'}`")
                    st.write(f"Match distance (SFace Cosine): `{c_dist:.3f}` *(Threshold: ≤ 0.60, lower is closer)*")
                    st.warning("⚠️ **Human Review Required:** Biometric detection is an assistive suggestion only. Do not mark present without visual confirmation.")

                    col_conf, col_dismiss = st.columns(2)
                    with col_conf:
                        if st.button(f"✅ Confirm & Mark {c_student['name']} Present", type="primary", key=f"btn_confirm_{c_student['student_id']}"):
                            ok, err = record_attendance_entry(
                                client,
                                c_student["student_id"],
                                subject_id,
                                active_session["timestamp"],
                                is_present=True,
                            )
                            if ok:
                                active_session.setdefault("confirmed_student_ids", set()).add(c_student["student_id"])
                                st.session_state.pop(f"candidate_match_{subject_id}", None)
                                st.success(f"✅ Attendance confirmed and recorded for {c_student['name']}!")
                                st.rerun()
                            else:
                                st.error(f"Failed to record attendance: {err}")
                    with col_dismiss:
                        if st.button("❌ Dismiss / Not this student", key=f"btn_dismiss_{c_student['student_id']}"):
                            st.session_state.pop(f"candidate_match_{subject_id}", None)
                            st.info("Dismissed candidate match.")
                            st.rerun()

    with tab_update:
        st.write("Choose a past class date, review its saved attendance, and correct statuses.")
        class_date = st.date_input("Attendance date", value=date.today(), max_value=date.today(), key=f"edit_date_{subject_id}")
        start_utc = datetime.combine(class_date, time.min, tzinfo=timezone.utc).isoformat()
        end_utc = datetime.combine(date.fromordinal(class_date.toordinal() + 1), time.min, tzinfo=timezone.utc).isoformat()
        try:
            existing_rows = (
                client.table("attendance_logs")
                .select("attendance_id,student_id,subject_id,timestamp,is_present")
                .eq("subject_id", subject_id)
                .gte("timestamp", start_utc)
                .lt("timestamp", end_utc)
                .order("timestamp")
                .execute().data
            )
        except Exception as e:
            st.error(f"Could not load attendance for editing: {type(e).__name__}: {e}")
            existing_rows = []

        if not existing_rows:
            st.info("No attendance records were found for this subject and date.")
        else:
            by_student = {}
            for row in existing_rows:
                sid = row["student_id"]
                # If multiple sessions were recorded on the same date, preserve
                # each row and let the teacher choose which session to edit.
                by_student.setdefault(sid, []).append(row)
            session_options = {}
            active_ts = active_session["timestamp"] if active_session else None
            for sid, records in by_student.items():
                student_name = next((s["name"] for s in students if s["student_id"] == sid), f"Student {sid}")
                for record in records:
                    tag = " 🟢 [ACTIVE SESSION]" if active_ts and record["timestamp"] == active_ts else ""
                    label = f'{student_name} · {record["timestamp"]}{tag}'
                    session_options[label] = record

            selected_record_labels = st.multiselect(
                "Select attendance records to edit",
                options=list(session_options),
                default=list(session_options),
                key=f"selected_edit_records_{subject_id}_{class_date.isoformat()}",
            )
            if selected_record_labels:
                with st.form(f"update_attendance_{subject_id}_{class_date.isoformat()}"):
                    updates = []
                    for index, label in enumerate(selected_record_labels):
                        record = session_options[label]
                        student = next((s for s in students if s["student_id"] == record["student_id"]), None)
                        if student is None:
                            continue
                        current_status = bool(record["is_present"])
                        new_status = st.selectbox(
                            f'{student["name"]} — {record["timestamp"]}',
                            options=["Present", "Absent"],
                            index=0 if current_status else 1,
                            key=f'update_status_{record["attendance_id"]}',
                        )
                        updates.append((record, new_status == "Present"))
                    submit_updates = st.form_submit_button("Save attendance changes", type="primary")
                if submit_updates:
                    updated_count = 0
                    errors = []
                    for record, new_status in updates:
                        if bool(record["is_present"]) == new_status:
                            continue
                        try:
                            (
                                client.table("attendance_logs")
                                .update({"is_present": new_status})
                                .eq("attendance_id", record["attendance_id"])
                                .eq("subject_id", subject_id)
                                .eq("student_id", record["student_id"])
                                .execute()
                            )
                            updated_count += 1
                        except Exception as e:
                            errors.append(f'Record {record["attendance_id"]}: {type(e).__name__}: {e}')
                    if errors:
                        st.error("Some attendance records could not be updated:\n" + "\n".join(errors))
                    if updated_count:
                        st.success(f"Updated {updated_count} attendance record(s).")
                        st.rerun()
                    elif not errors:
                        st.info("No attendance statuses changed.")


def student_dashboard(client: Client) -> None:
    st.title("Student dashboard")
    with st.form("join_subject"):
        code = st.text_input("Subject code").strip().upper()
        join = st.form_submit_button("Join subject", type="primary")
    if join:
        if not code:
            st.warning("Enter a subject code.")
        else:
            try:
                matches = (
                    client.table("subjects").select("subject_id,name,subject_code,section")
                    .eq("subject_code", code).limit(1).execute().data
                )
                if not matches:
                    st.warning("No subject found with that code.")
                else:
                    subject = matches[0]
                    existing = (
                        client.table("subject_students").select("student_id")
                        .eq("student_id", st.session_state["profile_id"])
                        .eq("subject_id", subject["subject_id"]).limit(1).execute().data
                    )
                    if existing:
                        st.info(f'You have already joined {subject["name"]}.')
                    else:
                        client.table("subject_students").insert({
                            "student_id": st.session_state["profile_id"],
                            "subject_id": subject["subject_id"],
                        }).execute()
                        st.success(f'Joined {subject["name"]}.')
                        st.rerun()
            except Exception as e:
                st.error(f"Could not join subject: {type(e).__name__}: {e}")
    student_id = st.session_state.get("profile_id")
    if student_id is None:
        st.error("Your student profile ID is missing. Sign out and sign in again.")
        return

    tab_att, tab_bio = st.tabs(["📊 My Attendance", "🧬 Biometric Registration"])

    with tab_att:
        st.subheader("My attendance")
        try:
            rows = (
                client.table("attendance_logs").select("subject_id,timestamp,is_present")
                .eq("student_id", student_id).order("timestamp", desc=True).execute().data
            )
            if not rows:
                st.info(
                    "No attendance records were returned for your student profile. "
                    "If a teacher has marked attendance, check the attendance_logs "
                    "SELECT policy and confirm that your student_id matches the record in Supabase."
                )
            else:
                subject_ids = sorted({row["subject_id"] for row in rows})
                subjects = (
                    client.table("subjects").select("subject_id,name,subject_code")
                    .in_("subject_id", subject_ids).execute().data
                )
                subject_names = {
                    s["subject_id"]: f'{s["name"]} ({s["subject_code"]})' for s in subjects
                }
                df = pd.DataFrame(rows)
                df["subject"] = df["subject_id"].map(subject_names).fillna(
                    df["subject_id"].map(lambda value: f"Subject {value}")
                )
                df["status"] = df["is_present"].map({True: "Present", False: "Absent"}).fillna("Unknown")
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
                df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                st.dataframe(df[["subject", "timestamp", "status"]], use_container_width=True, hide_index=True)
                total = len(rows)
                present = sum(row.get("is_present") is True for row in rows)
                st.metric("Attendance rate", f"{present / total:.0%}" if total else "—")
        except Exception as e:
            st.error("Could not load attendance from Supabase. " f"Error: {type(e).__name__}: {e}")
            st.caption(
                "If the error mentions permission denied, inspect the SELECT RLS policies "
                "on attendance_logs and subjects. Do not disable RLS or use a service-role key in the app."
            )

    with tab_bio:
        render_student_biometrics_section(client, student_id)


def landing_page() -> None:
    """Public marketing landing page; auth and dashboards remain unchanged."""
    st.markdown(r"""
    <style>
      .stApp { background: #f6f8fc; }
      [data-testid="stHeader"] { background: rgba(246,248,252,.88); }
      .block-container { max-width: 1180px; padding-top: 1.5rem; padding-bottom: 3rem; }
      .snap-nav { display:flex; align-items:center; justify-content:space-between; padding: .35rem 0 1.8rem; }
      .snap-brand { font-size:1.35rem; font-weight:800; letter-spacing:-.04em; color:#14213d; }
      .snap-brand span { color:#4f46e5; }
      .snap-pill { display:inline-block; border:1px solid #dbe3f0; border-radius:999px; padding:.42rem .8rem; color:#394766; font-size:.82rem; background:#fff; }
      .snap-hero { background:linear-gradient(135deg,#111b3a 0%,#263b75 58%,#4f46e5 100%); border-radius:28px; padding:3.4rem 3rem; color:white; box-shadow:0 22px 55px rgba(31,45,91,.17); }
      .snap-eyebrow { color:#c7d2fe; text-transform:uppercase; letter-spacing:.16em; font-size:.75rem; font-weight:800; }
      .snap-hero h1 { color:#fff; font-size:clamp(2.4rem,5vw,4.3rem); line-height:1.04; letter-spacing:-.055em; margin:.8rem 0 1rem; }
      .snap-hero p { color:#e0e7ff; font-size:1.08rem; line-height:1.75; max-width:650px; }
      .snap-hero-card { border:1px solid rgba(255,255,255,.2); background:rgba(255,255,255,.09); border-radius:20px; padding:1.25rem; margin-top:1rem; }
      .snap-stat { color:white; font-size:1.65rem; font-weight:800; }
      .snap-muted { color:#dbe4ff; font-size:.85rem; }
      .snap-section { padding:3rem 0 .6rem; }
      .snap-section h2 { color:#15213d; font-size:2rem; letter-spacing:-.04em; }
      .snap-section p { color:#64708a; line-height:1.7; }
      .snap-feature { background:white; border:1px solid #e6eaf2; border-radius:18px; padding:1.25rem; min-height:170px; box-shadow:0 7px 22px rgba(26,40,74,.035); }
      .snap-feature-icon { font-size:1.5rem; }
      .snap-feature h3 { color:#17233e; font-size:1.08rem; margin:.7rem 0 .35rem; }
      .snap-feature p { font-size:.93rem; margin:0; }
      .snap-step { border-left:3px solid #818cf8; padding:.2rem 0 .2rem 1rem; margin:.65rem 0; }
      .snap-step strong { color:#17233e; }
      .snap-auth-brand { font-size:1.25rem; font-weight:800; color:#4f46e5; }
      .snap-footer { border-top:1px solid #e1e7f0; padding-top:1.3rem; margin-top:3rem; color:#77829a; font-size:.85rem; }
      @media(max-width:700px) { .snap-hero {padding:2rem 1.3rem;border-radius:20px;} }
    </style>
    <div class="snap-nav"><div class="snap-brand">✦ <span>Snap</span>Class</div><div class="snap-pill">CLOUD ATTENDANCE · COLLEGE DEMO</div></div>
    <div class="snap-hero">
      <div class="snap-eyebrow">A smarter classroom workflow</div>
      <h1>Attendance,<br>without the hassle.</h1>
      <p>One simple place for teachers to manage classes and record attendance, while students can join subjects and keep track of their attendance history.</p>
      <div class="snap-hero-card"><div class="snap-stat">Simple. Clear. Connected.</div><div class="snap-muted">A cloud-based attendance experience for classrooms.</div></div>
    </div>
    <div class="snap-section"><h2>Everything your class needs</h2><p>Purpose-built tools to make routine attendance easier to manage.</p></div>
    """, unsafe_allow_html=True)
    cols = st.columns(3, gap="medium")
    features = [
        ("🧑‍🏫", "Teacher workspace", "Create subjects, view enrolled students, and record attendance in one place."),
        ("🎓", "Student access", "Join a subject with its class code and view your own attendance records."),
        ("☁️", "Cloud-connected", "Access the app online with Supabase-backed authentication and data."),
    ]
    for col, (icon, title, body) in zip(cols, features):
        with col:
            st.markdown(
                f'<div class="snap-feature"><div class="snap-feature-icon">{icon}</div>'
                f'<h3>{title}</h3><p>{body}</p></div>',
                unsafe_allow_html=True,
            )
    st.markdown(r"""
    <div class="snap-section"><h2>Designed around a simple flow</h2><p>Get started in a few steps, whether you teach a class or attend one.</p>
      <div class="snap-step"><strong>01 · Create an account</strong><p>Choose the teacher or student role during registration.</p></div>
      <div class="snap-step"><strong>02 · Set up or join a subject</strong><p>Teachers create a subject and share its code; students use that code to join.</p></div>
      <div class="snap-step"><strong>03 · Record and review</strong><p>Teachers record attendance. Students review their own attendance history and rate.</p></div>
    </div>
    <div class="snap-footer">✦ SnapClass · Cloud-based student attendance <span style="float:right">Built for a college demonstration</span></div>
    """, unsafe_allow_html=True)
    st.write("")
    c1, c2, c3 = st.columns([1, 1, 3])
    with c1:
        if st.button("Sign in →", type="primary", use_container_width=True, key="home_signin"):
            st.session_state["snap_page"] = "auth"
            st.rerun()
    with c2:
        if st.button("Create account", use_container_width=True, key="home_signup"):
            st.session_state["snap_page"] = "auth"
            st.rerun()


def main() -> None:
    client = active_client()
    if not st.session_state.get("access_token"):
        if st.session_state.get("snap_page", "home") == "home":
            landing_page()
        else:
            login_ui(client)
        return
    client = active_client()
    if not recover_profile(client):
        st.warning(
            "Your Supabase login exists, but no SnapClass profile is linked. "
            "Sign out and sign in again. If the problem remains, check that a row exists "
            "in students or teachers with auth_user_id equal to your Supabase Auth user ID."
        )
        if st.button("Sign out"):
            sign_out()
        return
    with st.sidebar:
        st.markdown("### SnapClass")
        st.caption(st.session_state.get("email", "Signed in"))
        st.write(f'Role: **{st.session_state["role"]}**')
        if st.button("Sign out", use_container_width=True):
            sign_out()
    if st.session_state["role"] == "Teacher":
        teacher_dashboard(client)
    else:
        student_dashboard(client)


main()
