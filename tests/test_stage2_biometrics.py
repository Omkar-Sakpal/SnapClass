"""
Unit and integration tests for SnapClass Stage 2: Student Biometric Registration.
Uses standard library unittest for zero external test runner dependencies.
"""

import io
import os
import sys
import unittest
import wave
import numpy as np
from PIL import Image, ImageDraw

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ai.face_engine import extract_face_embedding, compare_faces, get_dlib_models
from src.ai.voice_engine import extract_voice_embedding, compare_voices, _decode_audio_bytes
from src.components.student_biometrics_ui import _verify_authenticated_student, delete_student_biometrics


def create_synthetic_face(has_face=True) -> Image.Image:
    """Helper to generate clean synthetic image with a recognizable face pattern."""
    img = Image.new("RGB", (200, 200), color=(200, 200, 200))
    if not has_face:
        return img

    draw = ImageDraw.Draw(img)
    # Head
    draw.ellipse([40, 30, 160, 170], fill=(230, 190, 160))
    # Eyes
    draw.ellipse([65, 75, 85, 95], fill=(50, 50, 50))
    draw.ellipse([115, 75, 135, 95], fill=(50, 50, 50))
    # Nose
    draw.polygon([(100, 95), (95, 120), (105, 120)], fill=(180, 140, 120))
    # Mouth
    draw.arc([75, 125, 125, 150], start=0, end=180, fill=(150, 50, 50), width=4)
    return img


def create_synthetic_wav(duration=1.5, sr=16000, silent=False) -> bytes:
    """Helper to generate mono 16kHz WAV audio bytes."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    if silent:
        samples = np.zeros(len(t), dtype=np.float32)
    else:
        f0 = 160.0
        samples = (
            0.6 * np.sin(2 * np.pi * f0 * t) +
            0.3 * np.sin(2 * np.pi * 2 * f0 * t) +
            0.15 * np.sin(2 * np.pi * 3 * f0 * t)
        ).astype(np.float32)

    audio_int16 = (samples * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


class TestFaceEngine(unittest.TestCase):
    def test_dlib_models_available(self):
        models = get_dlib_models()
        self.assertTrue(models["available"], f"dlib models failed to load: {models['error']}")
        self.assertIsNotNone(models["detector"])
        self.assertIsNotNone(models["shape_predictor"])
        self.assertIsNotNone(models["face_encoder"])

    def test_extract_face_embedding_success(self):
        img = create_synthetic_face(has_face=True)
        emb, err = extract_face_embedding(img)
        self.assertIsNone(err)
        self.assertIsNotNone(emb)
        self.assertEqual(len(emb), 128)
        self.assertTrue(all(isinstance(x, float) for x in emb))

    def test_extract_face_embedding_no_face(self):
        img = create_synthetic_face(has_face=False)
        emb, err = extract_face_embedding(img)
        self.assertIsNone(emb)
        self.assertIsNotNone(err)
        self.assertIn("No face detected", err)

    def test_face_comparison_identity(self):
        img = create_synthetic_face(has_face=True)
        emb1, _ = extract_face_embedding(img)
        emb2, _ = extract_face_embedding(img)
        dist = compare_faces(emb1, emb2)
        self.assertLess(dist, 1e-4, f"Identical face distance should be ~0, got {dist}")

    def test_face_comparison_dissimilar_embeddings_rejected(self):
        """
        Verify that dissimilar embeddings are rejected by Euclidean distance thresholding.
        Face match requires distance <= 0.60. Dissimilar faces have distance > 0.60.
        """
        # Deterministic orthogonal unit vectors of 128 dimensions
        emb1 = [1.0] + [0.0] * 127
        emb2 = [0.0, 1.0] + [0.0] * 126
        dist = compare_faces(emb1, emb2)
        # Euclidean distance of orthogonal unit vectors: sqrt(1^2 + 1^2) = sqrt(2) ≈ 1.414
        self.assertGreater(dist, 0.60, f"Dissimilar faces should have distance > 0.60, got {dist}")

        # Opposite vectors: distance = 2.0
        emb_opp = [-1.0] + [0.0] * 127
        dist_opp = compare_faces(emb1, emb_opp)
        self.assertGreater(dist_opp, 1.0, f"Opposite vectors should have distance > 1.0, got {dist_opp}")


class TestVoiceEngine(unittest.TestCase):
    def test_decode_wav_bytes(self):
        wav_bytes = create_synthetic_wav(duration=1.0)
        samples, sr, err = _decode_audio_bytes(wav_bytes)
        self.assertIsNone(err)
        self.assertEqual(sr, 16000)
        self.assertEqual(len(samples), 16000)

    def test_extract_voice_embedding_success(self):
        wav_bytes = create_synthetic_wav(duration=1.5)
        emb, err = extract_voice_embedding(wav_bytes)
        self.assertIsNone(err)
        self.assertIsNotNone(emb)
        self.assertIn(len(emb), (128, 256))
        norm = np.linalg.norm(np.array(emb))
        self.assertAlmostEqual(norm, 1.0, places=2)

    def test_reject_silent_audio(self):
        wav_bytes = create_synthetic_wav(duration=1.5, silent=True)
        emb, err = extract_voice_embedding(wav_bytes)
        self.assertIsNone(emb)
        self.assertIsNotNone(err)
        self.assertIn("silent", err.lower())

    def test_reject_too_short_audio(self):
        wav_bytes = create_synthetic_wav(duration=0.2)
        emb, err = extract_voice_embedding(wav_bytes)
        self.assertIsNone(emb)
        self.assertIsNotNone(err)
        self.assertIn("too short", err.lower())

    def test_voice_comparison_identity(self):
        wav_bytes = create_synthetic_wav(duration=1.5)
        emb1, _ = extract_voice_embedding(wav_bytes)
        emb2, _ = extract_voice_embedding(wav_bytes)
        sim = compare_voices(emb1, emb2)
        self.assertGreater(sim, 0.99, f"Identical voice similarity should be ~1.0, got {sim}")

    def test_voice_comparison_dissimilar_embeddings(self):
        """
        Verify that dissimilar voice embeddings are rejected under cosine similarity comparison.
        Speaker match requires similarity >= 0.68.
        Orthogonal or unrelated vectors must yield low similarity (< 0.68).
        """
        # Deterministic orthogonal unit vectors
        emb1 = [1.0] + [0.0] * 127
        emb2 = [0.0, 1.0] + [0.0] * 126
        sim = compare_voices(emb1, emb2)
        self.assertAlmostEqual(sim, 0.0, places=4)
        self.assertLess(sim, 0.68, f"Orthogonal voice embeddings must have similarity < 0.68, got {sim}")

        # Opposite vectors
        emb_opp = [-1.0] + [0.0] * 127
        sim_opp = compare_voices(emb1, emb_opp)
        self.assertAlmostEqual(sim_opp, -1.0, places=4)
        self.assertLess(sim_opp, 0.68, f"Opposite voice embeddings must have similarity < 0.68, got {sim_opp}")

    def test_scipy_voice_fallback_limitation_documented(self):
        """
        Verify that SciPy spectral fallback limitations are explicitly documented in voice_engine.
        The spectral fallback extracts acoustic frequency power distributions and cannot reliably
        discriminate individual speakers without deep learning (e.g. Resemblyzer).
        """
        import src.ai.voice_engine as voice_engine

        doc = (voice_engine.__doc__ or "").lower()
        self.assertIn("spectral-temporal", doc)
        self.assertIn("scipy", doc)
        self.assertIn("not an identity-grade speaker discriminator", doc)


class TestStudentBiometricsSecurity(unittest.TestCase):
    def test_unverified_student_rejected(self):
        class MockTable:
            def select(self, *a, **kw):
                return self
            def eq(self, *a, **kw):
                return self
            def limit(self, *a, **kw):
                return self
            def execute(self):
                class Res:
                    data = []
                return Res()

        class MockClient:
            def table(self, name):
                return MockTable()

        import streamlit as st
        st.session_state["user_id"] = "fake-auth-id"
        verified = _verify_authenticated_student(MockClient(), student_id=999)
        self.assertFalse(verified)

    def test_delete_biometrics_success(self):
        class MockQuery:
            def __init__(self, table_name):
                self.table_name = table_name
            def select(self, *a, **kw):
                return self
            def eq(self, *a, **kw):
                return self
            def limit(self, *a, **kw):
                return self
            def maybe_single(self):
                return self
            def delete(self):
                return self
            def execute(self):
                class Res:
                    pass
                res = Res()
                if self.table_name == "students":
                    res.data = [{"student_id": 101}]
                elif self.table_name == "student_biometrics":
                    # Verification check returns None (row safely removed)
                    res.data = None
                return res

        class MockClient:
            def table(self, name):
                return MockQuery(name)

        import streamlit as st
        st.session_state["user_id"] = "auth-101"
        success, err = delete_student_biometrics(MockClient(), student_id=101)
        self.assertTrue(success)
        self.assertIsNone(err)

    def test_delete_biometrics_verification_failure(self):
        """If database record persists after delete (e.g. RLS blocked deletion), must report failure."""
        class MockQuery:
            def __init__(self, table_name):
                self.table_name = table_name
            def select(self, *a, **kw):
                return self
            def eq(self, *a, **kw):
                return self
            def limit(self, *a, **kw):
                return self
            def maybe_single(self):
                return self
            def delete(self):
                return self
            def execute(self):
                class Res:
                    pass
                res = Res()
                if self.table_name == "students":
                    res.data = [{"student_id": 101}]
                elif self.table_name == "student_biometrics":
                    # Record is still present!
                    res.data = {"student_id": 101, "face_embedding": [0.1]}
                return res

        class MockClient:
            def table(self, name):
                return MockQuery(name)

        import streamlit as st
        st.session_state["user_id"] = "auth-101"
        success, err = delete_student_biometrics(MockClient(), student_id=101)
        self.assertFalse(success)
        self.assertIn("still present", err)

    def test_delete_biometrics_database_exception(self):
        """If database throws an error during delete, it must be caught and reported safely."""
        class MockQuery:
            def __init__(self, table_name):
                self.table_name = table_name
            def select(self, *a, **kw):
                return self
            def eq(self, *a, **kw):
                return self
            def limit(self, *a, **kw):
                return self
            def maybe_single(self):
                return self
            def delete(self):
                raise RuntimeError("PostgREST connection failed")
            def execute(self):
                class Res:
                    pass
                res = Res()
                if self.table_name == "students":
                    res.data = [{"student_id": 101}]
                return res

        class MockClient:
            def table(self, name):
                return MockQuery(name)

        import streamlit as st
        st.session_state["user_id"] = "auth-101"
        success, err = delete_student_biometrics(MockClient(), student_id=101)
        self.assertFalse(success)
        self.assertIn("Database error during profile deletion", err)

    def test_delete_biometrics_unverified_student_blocked(self):
        """Unverified student should not be able to trigger biometric deletion."""
        class MockTable:
            def select(self, *a, **kw):
                return self
            def eq(self, *a, **kw):
                return self
            def limit(self, *a, **kw):
                return self
            def execute(self):
                class Res:
                    data = []
                return Res()

        class MockClient:
            def table(self, name):
                return MockTable()

        import streamlit as st
        st.session_state["user_id"] = "different-auth-id"
        success, err = delete_student_biometrics(MockClient(), student_id=999)
        self.assertFalse(success)
        self.assertIn("Cannot verify student identity", err)


if __name__ == "__main__":
    unittest.main()
