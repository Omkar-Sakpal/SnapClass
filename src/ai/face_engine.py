"""
SnapClass Face Recognition Engine.

Extracts 128-dimensional biometric face descriptors using dlib and
face_recognition_models ResNet. Employs lazy model loading and strict quality
checks (single face, clarity, lighting).
"""

from typing import Tuple, Optional, List
import io
import numpy as np
from PIL import Image
import streamlit as st


@st.cache_resource(show_spinner="Loading facial recognition models...")
def get_dlib_models():
    """Lazily load dlib frontal face detector, shape predictor, and face recognition ResNet."""
    try:
        import dlib
        import face_recognition_models

        detector = dlib.get_frontal_face_detector()
        predictor_path = face_recognition_models.pose_predictor_model_location()
        rec_model_path = face_recognition_models.face_recognition_model_location()

        shape_predictor = dlib.shape_predictor(predictor_path)
        face_encoder = dlib.face_recognition_model_v1(rec_model_path)
        return {
            "available": True,
            "detector": detector,
            "shape_predictor": shape_predictor,
            "face_encoder": face_encoder,
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "detector": None,
            "shape_predictor": None,
            "face_encoder": None,
            "error": f"{type(exc).__name__}: {str(exc)}",
        }


def extract_face_embedding(image_input) -> Tuple[Optional[List[float]], Optional[str]]:
    """
    Extracts a 128-dimensional face embedding from an input image.

    Args:
        image_input: PIL Image, BytesIO, or Streamlit UploadedFile.

    Returns:
        (embedding_list, error_message):
            - If successful: (list of 128 floats, None)
            - If quality check or model fails: (None, descriptive_error_str)
    """
    models = get_dlib_models()
    if not models["available"]:
        return (
            None,
            f"Face recognition engine is unavailable on this host: {models['error']}. "
            "Please contact the administrator or use manual attendance.",
        )

    # 1. Convert input to RGB numpy array
    try:
        if isinstance(image_input, (bytes, bytearray)):
            img = Image.open(io.BytesIO(image_input)).convert("RGB")
        elif hasattr(image_input, "read"):
            # UploadedFile or BytesIO
            image_input.seek(0)
            img = Image.open(image_input).convert("RGB")
        elif isinstance(image_input, Image.Image):
            img = image_input.convert("RGB")
        elif isinstance(image_input, np.ndarray):
            img = Image.fromarray(image_input).convert("RGB")
        else:
            return None, "Invalid image format received."

        # Downscale large images (max 1280px) to prevent memory spikes on Cloud
        max_dim = 1280
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        img_np = np.array(img)
    except Exception as exc:
        return None, f"Could not parse image: {type(exc).__name__}: {str(exc)}"

    # 2. Detect faces
    try:
        detector = models["detector"]
        faces = detector(img_np, 1)
    except Exception as exc:
        return None, f"Face detection failed: {type(exc).__name__}: {str(exc)}"

    # 3. Quality enforcement: Exactly ONE face must be present
    num_faces = len(faces)
    if num_faces == 0:
        return (
            None,
            "No face detected in the snapshot. Please look directly at the camera in a well-lit area.",
        )
    if num_faces > 1:
        return (
            None,
            f"Multiple faces ({num_faces}) detected. For biometric registration, ensure you are the only person in frame.",
        )

    # 4. Compute landmarks and 128-d descriptor
    try:
        shape_predictor = models["shape_predictor"]
        face_encoder = models["face_encoder"]

        shape = shape_predictor(img_np, faces[0])
        descriptor = face_encoder.compute_face_descriptor(img_np, shape, 1)

        embedding = [round(float(val), 6) for val in descriptor]
        if len(embedding) != 128:
            return None, f"Unexpected embedding dimension: {len(embedding)} (expected 128)."

        return embedding, None
    except Exception as exc:
        return None, f"Feature extraction failed: {type(exc).__name__}: {str(exc)}"


def compare_faces(emb1: List[float], emb2: List[float]) -> float:
    """
    Computes Euclidean distance between two 128-dimensional face embeddings.
    Lower distance = higher resemblance.
    Standard threshold: <= 0.55 indicates high match; <= 0.60 indicates possible match.
    """
    arr1 = np.asarray(emb1, dtype=np.float32)
    arr2 = np.asarray(emb2, dtype=np.float32)
    return float(np.linalg.norm(arr1 - arr2))
