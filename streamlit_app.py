import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timezone, date, time

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

    st.subheader("Enrolled students")
    try:
        students = load_enrolled_students(client, subject_id)
    except Exception as e:
        st.error(f"Could not load enrolled students: {type(e).__name__}: {e}")
        return
    if not students:
        st.info("No students enrolled yet.")
        return

    tab_record, tab_update = st.tabs(["Record attendance", "Update attendance"])
    with tab_record:
        st.caption("Check the students who are present. Unchecked students will be recorded absent.")
        with st.form(f"record_attendance_{subject_id}"):
            present_ids = []
            for student in students:
                if st.checkbox(
                    f'{student["name"]} ({student.get("email") or "no email"})',
                    key=f'record_present_{subject_id}_{student["student_id"]}',
                ):
                    present_ids.append(student["student_id"])
            save = st.form_submit_button("Save attendance", type="primary")
        if save:
            timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            rows = [{
                "student_id": student["student_id"],
                "subject_id": subject_id,
                "timestamp": timestamp,
                "is_present": student["student_id"] in present_ids,
            } for student in students]
            try:
                client.table("attendance_logs").insert(rows).execute()
                st.success(f"Attendance saved for {len(rows)} students.")
                st.rerun()
            except Exception as e:
                st.error(f"Attendance could not be saved: {type(e).__name__}: {e}")

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
            for sid, records in by_student.items():
                student_name = next((s["name"] for s in students if s["student_id"] == sid), f"Student {sid}")
                for record in records:
                    label = f'{student_name} · {record["timestamp"]}'
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
    st.subheader("My attendance")
    student_id = st.session_state.get("profile_id")
    if student_id is None:
        st.error("Your student profile ID is missing. Sign out and sign in again.")
        return
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
            return
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
