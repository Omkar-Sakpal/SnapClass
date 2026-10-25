"""
Unit and integration tests for SnapClass Teacher Attendance Sessions & Face-Assisted Attendance.
Tests session creation/teardown, face matching against consented biometrics,
confirmation gating, duplicate entry prevention, and manual attendance fallback.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import streamlit as st

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from streamlit_app import (
    start_attendance_session,
    end_attendance_session,
    get_active_session,
    record_attendance_entry,
    record_batch_attendance,
    match_face_to_enrolled_students,
)


class MockTable:
    def __init__(self, name):
        self.name = name
        self.rows = []
        self.last_query = {}
        self.insert_calls = []
        self.update_calls = []

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self.last_query[col] = val
        return self

    def in_(self, col, vals):
        self.last_query[f"{col}__in"] = vals
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        class Res:
            pass
        res = Res()
        # Filter rows based on equality filters
        filtered = self.rows
        for col, val in self.last_query.items():
            if col.endswith("__in"):
                base_col = col[:-4]
                filtered = [r for r in filtered if r.get(base_col) in val]
            else:
                filtered = [r for r in filtered if r.get(col) == val]
        self.last_query = {}
        res.data = list(filtered)
        return res

    def insert(self, payload):
        self.insert_calls.append(payload)
        if isinstance(payload, list):
            for i, p in enumerate(payload):
                row = dict(p)
                row.setdefault("attendance_id", len(self.rows) + 1 + i)
                self.rows.append(row)
        else:
            row = dict(payload)
            row.setdefault("attendance_id", len(self.rows) + 1)
            self.rows.append(row)
        class Q:
            def execute(self):
                class Res:
                    pass
                r = Res()
                r.data = [payload] if not isinstance(payload, list) else payload
                return r
        return Q()

    def update(self, payload):
        self.update_calls.append(payload)
        # Apply update to rows matching last_query
        target_id = self.last_query.get("attendance_id")
        for r in self.rows:
            if target_id is None or r.get("attendance_id") == target_id:
                r.update(payload)
        class Q:
            def eq(s, col, val):
                self.last_query[col] = val
                return s
            def execute(s):
                class Res:
                    pass
                r = Res()
                r.data = [payload]
                return r
        return Q()


class MockClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = MockTable(name)
        return self.tables[name]


class TestTeacherAttendanceSessions(unittest.TestCase):
    def setUp(self):
        self.client = MockClient()
        # Clean up session state
        for key in list(st.session_state.keys()):
            if key.startswith("active_session_") or key.startswith("candidate_match_"):
                st.session_state.pop(key, None)

    def test_start_and_end_attendance_session(self):
        """Verifies session lifecycle: initialization, state tracking, and termination."""
        subject_id = 42
        teacher_id = 7

        # 1. Start session
        session = start_attendance_session(self.client, teacher_id, subject_id)
        self.assertIsNotNone(session)
        self.assertTrue(session["session_id"].startswith(f"SES-{subject_id}-"))
        self.assertEqual(session["subject_id"], subject_id)
        self.assertEqual(session["teacher_id"], teacher_id)
        self.assertEqual(session["status"], "active")
        self.assertIn("timestamp", session)

        # 2. Verify active session lookup
        active = get_active_session(subject_id)
        self.assertEqual(active["session_id"], session["session_id"])

        # 3. End session
        ended = end_attendance_session(self.client, subject_id)
        self.assertIsNotNone(ended)
        self.assertEqual(ended["status"], "completed")
        self.assertIn("ended_at", ended)
        self.assertIsNone(get_active_session(subject_id))

    def test_session_lifecycle_resilient_when_table_missing(self):
        """Verifies session lifecycle works even when attendance_sessions table does not exist in DB."""
        subject_id = 99
        teacher_id = 12

        # Configure mock table to simulate missing relation
        failing_client = MagicMock()
        failing_client.table.side_effect = Exception("PGRST205: relation 'attendance_sessions' does not exist")

        session = start_attendance_session(failing_client, teacher_id, subject_id)
        self.assertIsNotNone(session)
        self.assertEqual(session["status"], "active")
        self.assertEqual(get_active_session(subject_id)["session_id"], session["session_id"])

        ended = end_attendance_session(failing_client, subject_id)
        self.assertIsNotNone(ended)
        self.assertEqual(ended["status"], "completed")
        self.assertIsNone(get_active_session(subject_id))

    def test_face_assisted_matching_consented_student_success(self):
        """Verifies candidate face is correctly matched against registered consented student templates."""
        subject_id = 10
        enrolled_students = [
            {"student_id": 101, "name": "Alice Johnson", "email": "alice@example.com"},
            {"student_id": 102, "name": "Bob Smith", "email": "bob@example.com"},
        ]

        # Populate student_biometrics for Alice (consented, 128-d SFace vector)
        alice_vec = [0.1] * 128
        alice_payload = {
            "version": "sface_v1",
            "engine": "opencv_sface",
            "embedding": alice_vec,
            "dim": 128,
        }
        self.client.table("student_biometrics").rows = [
            {
                "student_id": 101,
                "face_embedding": alice_payload,
                "consent_given": True,
            }
        ]

        # Mock extract_face_embedding to return matching SFace payload
        with patch("streamlit_app.extract_face_embedding", return_value=(alice_payload, None)):
            matched, dist, err = match_face_to_enrolled_students(
                self.client, b"dummy_face_image", enrolled_students, threshold=0.60
            )
            self.assertIsNone(err)
            self.assertIsNotNone(matched)
            self.assertEqual(matched["student_id"], 101)
            self.assertEqual(matched["name"], "Alice Johnson")
            self.assertLess(dist, 1e-4)

    def test_face_assisted_matching_rejects_legacy_dlib_profile(self):
        """Verifies legacy dlib profiles are safely isolated and never compared against SFace vectors."""
        enrolled_students = [
            {"student_id": 101, "name": "Alice Johnson", "email": "alice@example.com"},
        ]
        # Legacy dlib profile is stored as a raw list of 128 floats
        self.client.table("student_biometrics").rows = [
            {
                "student_id": 101,
                "face_embedding": [0.1] * 128,
                "consent_given": True,
            }
        ]

        sface_payload = {
            "version": "sface_v1",
            "engine": "opencv_sface",
            "embedding": [0.1] * 128,
            "dim": 128,
        }
        with patch("streamlit_app.extract_face_embedding", return_value=(sface_payload, None)):
            matched, dist, err = match_face_to_enrolled_students(
                self.client, b"dummy_face_image", enrolled_students, threshold=0.60
            )
            self.assertIsNone(matched)
            self.assertIn("legacy face profiles", err)
            self.assertIn("re-register", err)

    def test_face_assisted_matching_rejects_unconsented_or_unregistered(self):
        """If no enrolled student has a consented biometric profile, no candidate match is returned."""
        enrolled_students = [
            {"student_id": 101, "name": "Alice Johnson", "email": "alice@example.com"},
        ]
        # Biometrics exist but consent_given is False
        sface_payload = {
            "version": "sface_v1",
            "engine": "opencv_sface",
            "embedding": [0.1] * 128,
            "dim": 128,
        }
        self.client.table("student_biometrics").rows = [
            {
                "student_id": 101,
                "face_embedding": sface_payload,
                "consent_given": False,
            }
        ]

        with patch("streamlit_app.extract_face_embedding", return_value=(sface_payload, None)):
            matched, dist, err = match_face_to_enrolled_students(
                self.client, b"dummy_face_image", enrolled_students, threshold=0.60
            )
            self.assertIsNone(matched)
            self.assertIn("No enrolled students have registered a consented", err)

    def test_face_assisted_matching_rejects_distant_face(self):
        """If facial distance exceeds threshold (0.60), match must be rejected."""
        enrolled_students = [
            {"student_id": 101, "name": "Alice Johnson", "email": "alice@example.com"},
        ]
        alice_vec = [1.0] + [0.0] * 127
        alice_payload = {
            "version": "sface_v1",
            "engine": "opencv_sface",
            "embedding": alice_vec,
            "dim": 128,
        }
        self.client.table("student_biometrics").rows = [
            {
                "student_id": 101,
                "face_embedding": alice_payload,
                "consent_given": True,
            }
        ]

        # Different person's face (orthogonal vector, cosine distance = 1.0)
        stranger_vec = [0.0, 1.0] + [0.0] * 126
        stranger_payload = {
            "version": "sface_v1",
            "engine": "opencv_sface",
            "embedding": stranger_vec,
            "dim": 128,
        }
        with patch("streamlit_app.extract_face_embedding", return_value=(stranger_payload, None)):
            matched, dist, err = match_face_to_enrolled_students(
                self.client, b"stranger_img", enrolled_students, threshold=0.60
            )
            self.assertIsNone(matched)
            self.assertGreater(dist, 0.60)
            self.assertIn("exceeds threshold", err)

    def test_biometric_profile_existence_does_not_auto_mark_present(self):
        """
        Gating test: Simply extracting and matching face biometrics must NOT
        write to attendance_logs. Attendance is recorded ONLY after teacher confirmation.
        """
        enrolled_students = [
            {"student_id": 101, "name": "Alice Johnson", "email": "alice@example.com"},
        ]
        sface_payload = {
            "version": "sface_v1",
            "engine": "opencv_sface",
            "embedding": [0.1] * 128,
            "dim": 128,
        }
        self.client.table("student_biometrics").rows = [
            {"student_id": 101, "face_embedding": sface_payload, "consent_given": True}
        ]

        with patch("streamlit_app.extract_face_embedding", return_value=(sface_payload, None)):
            matched, dist, err = match_face_to_enrolled_students(
                self.client, b"img", enrolled_students, threshold=0.60
            )
            self.assertIsNotNone(matched)

        # Confirm ZERO rows were written to attendance_logs
        self.assertEqual(len(self.client.table("attendance_logs").rows), 0)
        self.assertEqual(len(self.client.table("attendance_logs").insert_calls), 0)

    def test_attendance_saved_upon_explicit_confirmation(self):
        """When teacher explicitly confirms the candidate match, attendance is saved."""
        student_id = 101
        subject_id = 10
        ts = "2026-10-25T13:00:00+00:00"

        ok, err = record_attendance_entry(self.client, student_id, subject_id, ts, is_present=True)
        self.assertTrue(ok)
        self.assertIsNone(err)

        rows = self.client.table("attendance_logs").rows
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["student_id"], student_id)
        self.assertEqual(rows[0]["subject_id"], subject_id)
        self.assertEqual(rows[0]["timestamp"], ts)
        self.assertTrue(rows[0]["is_present"])

    def test_duplicate_attendance_prevention_single_entry(self):
        """Saving attendance repeatedly for same student, subject and session updates instead of duplicating."""
        student_id = 101
        subject_id = 10
        ts = "2026-10-25T13:00:00+00:00"

        # First entry: mark present
        record_attendance_entry(self.client, student_id, subject_id, ts, is_present=True)
        self.assertEqual(len(self.client.table("attendance_logs").rows), 1)

        # Duplicate call: update to absent
        record_attendance_entry(self.client, student_id, subject_id, ts, is_present=False)
        # Verify row count is STILL 1 (no duplicate row inserted)
        rows = self.client.table("attendance_logs").rows
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_present"])

    def test_batch_attendance_duplicate_prevention(self):
        """Batch manual attendance prevents duplicate rows for the same session timestamp."""
        subject_id = 10
        ts = "2026-10-25T13:00:00+00:00"
        statuses = [
            {"student_id": 101, "is_present": True},
            {"student_id": 102, "is_present": False},
        ]

        # First save
        count1, errs1 = record_batch_attendance(self.client, statuses, subject_id, ts)
        self.assertEqual(count1, 2)
        self.assertEqual(len(errs1), 0)
        self.assertEqual(len(self.client.table("attendance_logs").rows), 2)

        # Second save with modified status
        statuses[1]["is_present"] = True
        count2, errs2 = record_batch_attendance(self.client, statuses, subject_id, ts)
        self.assertEqual(count2, 2)
        self.assertEqual(len(errs2), 0)
        # Total rows in attendance_logs remains exactly 2!
        self.assertEqual(len(self.client.table("attendance_logs").rows), 2)
        self.assertTrue(self.client.table("attendance_logs").rows[1]["is_present"])


if __name__ == "__main__":
    unittest.main()
