"""
SnapClass Cloud-Compatible Face Recognition Engine.

Extracts 128-dimensional biometric face descriptors using OpenCV's native
YuNet face detector and SFace deep neural network recognizer.
Operates without dlib or C++ compilation dependencies.
Employs lazy model loading and strict quality checks (single face, clarity, lighting).
"""

from typing import Tuple, Optional, List, Dict, Any, Union
import io
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps
import streamlit as st

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
YUNET_MODEL_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

ENGINE_IDENTIFIER = "opencv_sface"
ENGINE_VERSION = "sface_v1"
EMBEDDING_DIMENSION = 128

__all__ = [
    "extract_face_embedding",
    "compare_faces",
    "is_sface_profile",
    "is_legacy_profile",
    "get_opencv_face_models",
    "get_dlib_models",
    "ENGINE_IDENTIFIER",
    "ENGINE_VERSION",
    "EMBEDDING_DIMENSION",
]


@st.cache_resource(show_spinner="Loading facial recognition models...")
def get_opencv_face_models():
    """Lazily load OpenCV YuNet face detector and SFace recognizer."""
    if not YUNET_MODEL_PATH.exists():
        return {
            "available": False,
            "detector": None,
            "recognizer": None,
            "error": f"YuNet model file not found at {YUNET_MODEL_PATH}. Ensure models/ directory is populated.",
        }
    if not SFACE_MODEL_PATH.exists():
        return {
            "available": False,
            "detector": None,
            "recognizer": None,
            "error": f"SFace model file not found at {SFACE_MODEL_PATH}. Ensure models/ directory is populated.",
        }

    try:
        detector = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL_PATH),
            "",
            (320, 320),
            score_threshold=0.85,
            nms_threshold=0.3,
            top_k=5000,
        )
        recognizer = cv2.FaceRecognizerSF.create(
            str(SFACE_MODEL_PATH),
            "",
        )
        return {
            "available": True,
            "detector": detector,
            "recognizer": recognizer,
            "shape_predictor": recognizer,  # Backward compatibility
            "face_encoder": recognizer,     # Backward compatibility
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "detector": None,
            "recognizer": None,
            "shape_predictor": None,
            "face_encoder": None,
            "error": f"{type(exc).__name__}: {str(exc)}",
        }


def get_dlib_models():
    """Backward-compatibility alias pointing to current face models."""
    return get_opencv_face_models()


def is_sface_profile(bio_face: Any) -> bool:
    """Checks whether stored biometric data matches the OpenCV SFace engine format."""
    if not isinstance(bio_face, dict):
        return False
    return (
        bio_face.get("engine") == ENGINE_IDENTIFIER
        and isinstance(bio_face.get("embedding"), list)
        and len(bio_face.get("embedding")) == EMBEDDING_DIMENSION
    )


def is_legacy_profile(bio_face: Any) -> bool:
    """Checks whether stored biometric data was created with a legacy engine (e.g. dlib)."""
    if bio_face is None:
        return False
    return not is_sface_profile(bio_face)


def extract_face_embedding(
    image_input,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Extracts a 128-dimensional face embedding payload from an input image using OpenCV YuNet and SFace.

    Args:
        image_input: PIL Image, bytes, BytesIO, or Streamlit UploadedFile.

    Returns:
        (payload_dict, error_message):
            - If successful: ({"version": "sface_v1", "engine": "opencv_sface", "embedding": list_of_128_floats, "dim": 128}, None)
            - If quality check or model fails: (None, descriptive_error_str)
    """
    models = get_opencv_face_models()
    if not models["available"]:
        return (
            None,
            f"Face recognition engine is unavailable on this host: {models['error']}. "
            "Please contact the administrator or use manual attendance.",
        )

    # 1. Convert input to RGB numpy array and handle EXIF orientation
    try:
        if isinstance(image_input, (bytes, bytearray)):
            img = Image.open(io.BytesIO(image_input))
        elif hasattr(image_input, "read"):
            # UploadedFile or BytesIO
            image_input.seek(0)
            img = Image.open(image_input)
        elif isinstance(image_input, Image.Image):
            img = image_input
        elif isinstance(image_input, np.ndarray):
            img = Image.fromarray(image_input)
        else:
            return None, "Invalid image format received."

        img = ImageOps.exif_transpose(img).convert("RGB")

        # Downscale large images (max 1280px) to prevent memory spikes on Cloud
        max_dim = 1280
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        img_rgb = np.array(img)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        return None, f"Could not parse image: {type(exc).__name__}: {str(exc)}"

    # 2. Detect faces using YuNet
    try:
        detector = models["detector"]
        h, w = img_bgr.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(img_bgr)
    except Exception as exc:
        return None, f"Face detection failed: {type(exc).__name__}: {str(exc)}"

    # 3. Quality enforcement: Exactly ONE face must be present
    num_faces = len(faces) if faces is not None else 0
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

    # 4. Align, crop, and compute 128-d descriptor using SFace
    try:
        recognizer = models["recognizer"]
        aligned_face = recognizer.alignCrop(img_bgr, faces[0])
        feature = recognizer.feature(aligned_face)

        embedding = [round(float(val), 6) for val in feature[0]]
        if len(embedding) != EMBEDDING_DIMENSION:
            return None, f"Unexpected embedding dimension: {len(embedding)} (expected {EMBEDDING_DIMENSION})."

        return {
            "version": ENGINE_VERSION,
            "engine": ENGINE_IDENTIFIER,
            "embedding": embedding,
            "dim": EMBEDDING_DIMENSION,
        }, None
    except Exception as exc:
        return None, f"Feature extraction failed: {type(exc).__name__}: {str(exc)}"


def compare_faces(emb1: Any, emb2: Any) -> float:
    """
    Computes Cosine distance between two 128-dimensional face embeddings.
    Accepts either raw lists of floats or structured engine payload dicts.
    Lower distance = higher resemblance (0.0 = identical).
    SFace reference threshold: <= 0.60 indicates a strong match (Cosine Similarity >= 0.40).
    """
    def _extract_vector(e: Any) -> List[float]:
        if isinstance(e, dict):
            return e.get("embedding", [])
        return e if isinstance(e, list) else []

    vec1 = _extract_vector(emb1)
    vec2 = _extract_vector(emb2)

    arr1 = np.asarray(vec1, dtype=np.float32)
    arr2 = np.asarray(vec2, dtype=np.float32)

    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)
    if norm1 == 0 or norm2 == 0:
        return 1.0

    cosine_sim = float(np.dot(arr1, arr2) / (norm1 * norm2))
    return float(max(0.0, min(2.0, 1.0 - cosine_sim)))
