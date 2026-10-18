import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timezone

st.set_page_config(
    page_title="SnapClass | Attendance",
    page_icon="🎓",
    layout="wide",
)


# --------------------------------------------------
# SUPABASE CONNECTION
# --------------------------------------------------

def make_client(url: str, key: str) -> Client:
    return create_client(url, key)


def get_client() -> Client:
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_PUBLISHABLE_KEY", "")

    if not url or not key:
        st.error(
            "Supabase is not configured. Add SUPABASE_URL and "
            "SUPABASE_PUBLISHABLE_KEY to .streamlit/secrets.toml."
        )
        st.stop()

    return make_client(url, key)


def set_authenticated_session(client, session):
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["user_id"] = session.user.id
    st.session_state["client"] = client


def active_client():
    client = get_client()

    access = st.session_state.get("access_token")
    refresh = st.session_state.get("refresh_token")

    if access and refresh:
        try:
            client.auth.set_session(access, refresh)
        except Exception:
            for key in [
                "access_token",
                "refresh_token",
                "user_id",
                "role",
                "profile_id",
                "email",
                "display_name",
                "client",
            ]:
                st.session_state.pop(key, None)

    return client


def sign_out():
    try:
        client = st.session_state.get("client")
        if client:
            client.auth.sign_out()
    except Exception:
        pass

    for key in [
        "access_token",
        "refresh_token",
        "user_id",
        "role",
        "profile_id",
        "email",
        "display_name",
        "client",
    ]:
        st.session_state.pop(key, None)

    st.rerun()


# --------------------------------------------------
# LOGIN AND REGISTRATION
# --------------------------------------------------

def login_ui(client):
    st.title("🎓 SnapClass")
    st.caption("Cloud student attendance — demo starter")

    login_tab, signup_tab = st.tabs(
        ["Sign in", "Create account"]
    )

    with login_tab:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input(
                "Password",
                type="password",
            )

            submitted = st.form_submit_button(
                "Sign in",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            try:
                response = client.auth.sign_in_with_password(
                    {
                        "email": email.strip(),
                        "password": password,
                    }
                )

                if not response.session:
                    st.error(
                        "Sign-in did not return a session. "
                        "Check whether email confirmation is required."
                    )
                else:
                    set_authenticated_session(
                        client,
                        response.session,
                    )
                    st.session_state["email"] = email.strip()
                    st.rerun()

            except Exception as e:
                st.error(
                    f"Sign-in failed: {type(e).__name__}: {e}"
                )

    with signup_tab:
        with st.form("signup"):
            name = st.text_input("Full name")

            email = st.text_input(
                "Email address",
                key="signup_email",
            )

            password = st.text_input(
                "Password (at least 8 characters)",
                type="password",
                key="signup_password",
            )

            role = st.selectbox(
                "I am a",
                ["Student", "Teacher"],
            )

            submitted = st.form_submit_button(
                "Create account",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            if (
                not name.strip()
                or not email.strip()
                or len(password) < 8
            ):
                st.warning(
                    "Enter your name, email, and a password "
                    "of at least 8 characters."
                )
                return

            try:
                response = client.auth.sign_up(
                    {
                        "email": email.strip(),
                        "password": password,
                    }
                )

                user = getattr(response, "user", None)
                session = getattr(response, "session", None)

                if not user:
                    st.error(
                        "Supabase did not return a user."
                    )
                    return

                if not session:
                    st.success(
                        "Account created. Verify your email if "
                        "required, then sign in. If the profile "
                        "was not created, check the database setup."
                    )
                    return

                set_authenticated_session(client, session)

                uid = user.id

                if role == "Teacher":
                    result = (
                        client.table("teachers")
                        .insert(
                            {
                                "username": email.strip(),
                                "password": None,
                                "name": name.strip(),
                                "auth_user_id": uid,
                            }
                        )
                        .execute()
                    )

                    st.session_state["role"] = "Teacher"
                    st.session_state["profile_id"] = (
                        result.data[0]["teacher_id"]
                    )

                else:
                    result = (
                        client.table("students")
                        .insert(
                            {
                                "name": name.strip(),
                                "email": email.strip(),
                                "auth_user_id": uid,
                            }
                        )
                        .execute()
                    )

                    st.session_state["role"] = "Student"
                    st.session_state["profile_id"] = (
                        result.data[0]["student_id"]
                    )

                st.session_state["email"] = email.strip()
                st.session_state["display_name"] = name.strip()

                st.rerun()

            except Exception as e:
                st.error(
                    f"Account creation failed: {type(e).__name__}: {e}"
                )


# --------------------------------------------------
# FIND THE SIGNED-IN USER'S PROFILE
# --------------------------------------------------

def recover_profile(client):
    uid = st.session_state.get("user_id")

    if not uid:
        return False

    profiles = [
        ("Teacher", "teachers", "teacher_id"),
        ("Student", "students", "student_id"),
    ]

    for role, table, id_column in profiles:
        try:
            result = (
                client.table(table)
                .select("*")
                .eq("auth_user_id", uid)
                .limit(1)
                .execute()
            )

            if result.data:
                profile = result.data[0]

                st.session_state["role"] = role
                st.session_state["profile_id"] = (
                    profile[id_column]
                )

                st.session_state["display_name"] = (
                    profile.get("name", "")
                )

                st.session_state["email"] = (
                    profile.get("email")
                    or st.session_state.get("email", "")
                )

                return True

        except Exception:
            continue

    return False


# --------------------------------------------------
# TEACHER DASHBOARD
# --------------------------------------------------

def teacher_dashboard(client):
    st.title("Teacher dashboard")

    st.write(
        "Create a subject, then record attendance "
        "for enrolled students."
    )

    with st.expander("Create subject", expanded=True):
        with st.form("create_subject"):
            subject_name = st.text_input("Subject name")

            subject_code = st.text_input(
                "Unique subject code",
                help="Choose a short code students can enter.",
            )

            section = st.text_input(
                "Section / class",
                value="A",
            )

            create = st.form_submit_button(
                "Create subject",
                type="primary",
            )

        if create:
            if (
                not subject_name.strip()
                or not subject_code.strip()
                or not section.strip()
            ):
                st.warning("Complete all fields.")

            else:
                try:
                    (
                        client.table("subjects")
                        .insert(
                            {
                                "name": subject_name.strip(),
                                "subject_code": (
                                    subject_code.strip().upper()
                                ),
                                "section": section.strip(),
                                "teacher_id": (
                                    st.session_state["profile_id"]
                                ),
                            }
                        )
                        .execute()
                    )

                    st.success("Subject created.")
                    st.rerun()

                except Exception as e:
                    st.error(
                        f"Could not create subject: "
                        f"{type(e).__name__}: {e}"
                    )

    try:
        subjects = (
            client.table("subjects")
            .select("*")
            .eq(
                "teacher_id",
                st.session_state["profile_id"],
            )
            .order("subject_id", desc=True)
            .execute()
            .data
        )

    except Exception as e:
        st.error(
            f"Could not load subjects: {type(e).__name__}: {e}"
        )
        return

    if not subjects:
        st.info("No subjects yet. Create one above.")
        return

    subject_map = {
        (
            f'{s["name"]} — {s["section"]} '
            f'({s["subject_code"]})'
        ): s
        for s in subjects
    }

    selected_label = st.selectbox(
        "Choose a subject",
        list(subject_map.keys()),
    )

    subject = subject_map[selected_label]

    st.subheader("Enrolled students")

    try:
        enrollments = (
            client.table("subject_students")
            .select("student_id")
            .eq("subject_id", subject["subject_id"])
            .execute()
            .data
        )

        student_ids = [
            row["student_id"]
            for row in enrollments
        ]

        if student_ids:
            students = (
                client.table("students")
                .select("student_id,name,email")
                .in_("student_id", student_ids)
                .execute()
                .data
            )
        else:
            students = []

    except Exception as e:
        st.error(
            f"Could not load enrolled students: "
            f"{type(e).__name__}: {e}"
        )
        return

    if not students:
        st.info("No students enrolled yet.")
        return

    with st.form("record_attendance"):
        st.caption(
            "Check the students who are present. "
            "Unchecked students will be recorded absent."
        )

        present_ids = []

        for student in students:
            checked = st.checkbox(
                (
                    f'{student["name"]} '
                    f'({student.get("email") or "no email"})'
                ),
                key=(
                    f'present_{subject["subject_id"]}_'
                    f'{student["student_id"]}'
                ),
            )

            if checked:
                present_ids.append(student["student_id"])

        save = st.form_submit_button(
            "Save attendance",
            type="primary",
        )

    if save:
        timestamp = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        )

        rows = [
            {
                "student_id": student["student_id"],
                "subject_id": subject["subject_id"],
                "timestamp": timestamp,
                "is_present": (
                    student["student_id"] in present_ids
                ),
            }
            for student in students
        ]

        try:
            (
                client.table("attendance_logs")
                .insert(rows)
                .execute()
            )

            st.success(
                f"Attendance saved for {len(rows)} students."
            )

        except Exception as e:
            st.error(
                f"Attendance could not be saved: "
                f"{type(e).__name__}: {e}"
            )


# --------------------------------------------------
# STUDENT DASHBOARD
# --------------------------------------------------

def student_dashboard(client):
    st.title("Student dashboard")

    with st.form("join_subject"):
        code = st.text_input("Subject code").strip().upper()

        join = st.form_submit_button(
            "Join subject",
            type="primary",
        )

    if join:
        if not code:
            st.warning("Enter a subject code.")

        else:
            try:
                matches = (
                    client.table("subjects")
                    .select(
                        "subject_id,name,subject_code,section"
                    )
                    .eq("subject_code", code)
                    .limit(1)
                    .execute()
                    .data
                )

                if not matches:
                    st.warning("No subject found with that code.")

                else:
                    subject = matches[0]
                    student_id = st.session_state["profile_id"]

                    existing = (
                        client.table("subject_students")
                        .select("student_id")
                        .eq("student_id", student_id)
                        .eq(
                            "subject_id",
                            subject["subject_id"],
                        )
                        .limit(1)
                        .execute()
                        .data
                    )

                    if existing:
                        st.info(
                            f'You have already joined {subject["name"]}.'
                        )

                    else:
                        (
                            client.table("subject_students")
                            .insert(
                                {
                                    "student_id": student_id,
                                    "subject_id": subject["subject_id"],
                                }
                            )
                            .execute()
                        )

                        st.success(
                            f'Joined {subject["name"]}.'
                        )
                        st.rerun()

            except Exception as e:
                st.error(
                    f"Could not join subject: "
                    f"{type(e).__name__}: {e}"
                )

    st.subheader("My attendance")

    # IMPORTANT:
    # profile_id must be students.student_id,
    # not the Supabase Auth UUID.
    student_id = st.session_state.get("profile_id")

    if student_id is None:
        st.error(
            "Student profile ID is missing. "
            "Sign out and sign in again."
        )
        return

    try:
        rows = (
            client.table("attendance_logs")
            .select("subject_id,timestamp,is_present")
            .eq("student_id", student_id)
            .order("timestamp", desc=True)
            .execute()
            .data
        )

        if not rows:
            st.info(
                "No attendance records were returned for your profile. "
                "If your teacher has marked attendance, verify the "
                "student_id and the attendance_logs SELECT policy "
                "in Supabase."
            )
            return

        subject_ids = list(
            {row["subject_id"] for row in rows}
        )

        subjects = (
            client.table("subjects")
            .select("subject_id,name,subject_code")
            .in_("subject_id", subject_ids)
            .execute()
            .data
        )

        subject_names = {
            subject["subject_id"]: (
                f'{subject["name"]} '
                f'({subject["subject_code"]})'
            )
            for subject in subjects
        }

        df = pd.DataFrame(rows)

        df["subject"] = (
            df["subject_id"]
            .map(subject_names)
            .fillna(
                df["subject_id"].map(
                    lambda value: f"Subject {value}"
                )
            )
        )

        df["status"] = (
            df["is_present"]
            .map(
                {
                    True: "Present",
                    False: "Absent",
                }
            )
            .fillna("Unknown")
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            errors="coerce",
            utc=True,
        ).dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        st.dataframe(
            df[["subject", "timestamp", "status"]],
            use_container_width=True,
            hide_index=True,
        )

        total = len(rows)

        present = sum(
            row.get("is_present") is True
            for row in rows
        )

        attendance_rate = (
            f"{present / total:.0%}"
            if total
            else "—"
        )

        st.metric(
            "Attendance rate",
            attendance_rate,
        )

    except Exception as e:
        st.error(
            "Could not load attendance from Supabase. "
            f"Error: {type(e).__name__}: {e}"
        )

        st.caption(
            "If the error mentions permission denied, inspect "
            "the SELECT RLS policies on attendance_logs and subjects. "
            "Do not disable RLS or use a service-role key."
        )


# --------------------------------------------------
# MAIN APPLICATION
# --------------------------------------------------

def main():
    client = active_client()

    if not st.session_state.get("access_token"):
        login_ui(client)
        return

    client = active_client()

    if not recover_profile(client):
        st.warning(
            "Your Supabase login exists, but no SnapClass profile "
            "is linked. Sign out and sign in again. If the problem "
            "continues, check that a row exists in students or "
            "teachers with auth_user_id matching your Supabase "
            "Auth user ID."
        )

        if st.button("Sign out"):
            sign_out()

        return

    with st.sidebar:
        st.markdown("### SnapClass")

        st.caption(
            st.session_state.get("email", "Signed in")
        )

        st.write(
            f'Role: **{st.session_state["role"]}**'
        )

        if st.button(
            "Sign out",
            use_container_width=True,
        ):
            sign_out()

    if st.session_state["role"] == "Teacher":
        teacher_dashboard(client)
    else:
        student_dashboard(client)


main()