"""
SnapClass Voice Recognition Engine.

Extracts normalized speaker embeddings from spoken audio samples.
Supports Resemblyzer (256-d deep learning) when available, and provides a
lightweight, calibrated spectral-temporal acoustic embedding (128-d) via SciPy
for resource-constrained environments (such as Streamlit Community Cloud).
"""

from typing import Tuple, Optional, List
import io
import wave
import numpy as np
import streamlit as st


@st.cache_resource(show_spinner=False)
def get_resemblyzer_encoder():
    """Attempt to lazily load Resemblyzer VoiceEncoder if available."""
    try:
        from resemblyzer import VoiceEncoder
        encoder = VoiceEncoder(device="cpu")
        return {"available": True, "encoder": encoder, "error": None}
    except Exception as exc:
        return {"available": False, "encoder": None, "error": str(exc)}


def _decode_audio_bytes(audio_bytes: bytes) -> Tuple[Optional[np.ndarray], Optional[int], Optional[str]]:
    """Decode raw audio bytes into mono float32 samples and sample rate."""
    if not audio_bytes or len(audio_bytes) < 100:
        return None, None, "Audio recording is empty or corrupt."

    # Try scipy.io.wavfile first
    try:
        from scipy.io import wavfile
        sr, data = wavfile.read(io.BytesIO(audio_bytes))
        if data.ndim > 1:
            data = data.mean(axis=1)
        if np.issubdtype(data.dtype, np.integer):
            max_val = float(np.iinfo(data.dtype).max)
            samples = data.astype(np.float32) / max_val
        else:
            samples = data.astype(np.float32)
        return samples, int(sr), None
    except Exception:
        pass

    # Try standard library wave module as fallback
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            frames = wf.readframes(n_frames)

            if sampwidth == 2:
                data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 1:
                data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            else:
                data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0

            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1)

            return data, sr, None
    except Exception as exc:
        return None, None, f"Could not decode audio format: {type(exc).__name__}: {str(exc)}"


def extract_voice_embedding(audio_input) -> Tuple[Optional[List[float]], Optional[str]]:
    """
    Extracts a normalized numerical speaker embedding from an audio recording.

    Args:
        audio_input: bytes, BytesIO, or Streamlit UploadedFile.

    Returns:
        (embedding_list, error_message):
            - If successful: (list of floats, None)
            - If validation or audio fails: (None, error_str)
    """
    try:
        if isinstance(audio_input, (bytes, bytearray)):
            audio_bytes = bytes(audio_input)
        elif hasattr(audio_input, "read"):
            audio_input.seek(0)
            audio_bytes = audio_input.read()
        else:
            return None, "Invalid audio input format."
    except Exception as exc:
        return None, f"Could not read audio data: {type(exc).__name__}: {str(exc)}"

    samples, sr, err = _decode_audio_bytes(audio_bytes)
    if err or samples is None or sr is None:
        return None, err or "Failed to decode audio."

    # 1. Duration check (must be at least 0.6 seconds of speech)
    duration = len(samples) / float(sr)
    if duration < 0.6:
        return (
            None,
            f"Recording is too short ({duration:.1f}s). Please speak the enrollment phrase clearly for at least 1-2 seconds.",
        )

    # 2. Silence / Energy check
    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < 0.008:
        return (
            None,
            "Audio recording is almost silent. Please ensure your microphone is unmuted and speak clearly.",
        )

    # 3. Check for Resemblyzer deep-learning encoder first
    resemblyzer_info = get_resemblyzer_encoder()
    if resemblyzer_info["available"]:
        try:
            from resemblyzer import preprocess_wav
            # Resemblyzer expects wav array
            wav = preprocess_wav(samples, source_sr=sr)
            raw_emb = resemblyzer_info["encoder"].embed_utterance(wav)
            embedding = [round(float(v), 6) for v in raw_emb]
            return embedding, None
        except Exception:
            # Fall through to calibrated acoustic spectral embedding
            pass

    # 4. Calibrated Spectral-Temporal Speaker Embedding (SciPy-based)
    # Extracts multi-band spectral centroids, power distribution, and statistical pooling
    try:
        from scipy import signal

        # Pre-emphasis
        if len(samples) > 1:
            emphasized = np.append(samples[0], samples[1:] - 0.97 * samples[:-1])
        else:
            emphasized = samples

        # Spectrogram
        nperseg = min(512, len(emphasized))
        noverlap = nperseg // 2
        f, t_spec, Sxx = signal.spectrogram(emphasized, fs=sr, nperseg=nperseg, noverlap=noverlap)
        log_S = np.log(Sxx + 1e-6)

        # Statistical features across frequency bands (mean, std, max, energy)
        mean_spec = np.mean(log_S, axis=1)
        std_spec = np.std(log_S, axis=1)
        max_spec = np.max(log_S, axis=1)

        combined = np.concatenate([mean_spec, std_spec, max_spec])

        # Standardize to 128 dimensions
        target_dim = 128
        if len(combined) >= target_dim:
            indices = np.linspace(0, len(combined) - 1, target_dim, dtype=int)
            vec = combined[indices]
        else:
            vec = np.pad(combined, (0, target_dim - len(combined)), mode="constant")

        # L2 unit normalization
        norm = float(np.linalg.norm(vec))
        if norm > 1e-8:
            vec = vec / norm

        embedding = [round(float(x), 6) for x in vec]
        return embedding, None
    except Exception as exc:
        return None, f"Voice feature extraction failed: {type(exc).__name__}: {str(exc)}"


def compare_voices(emb1: List[float], emb2: List[float]) -> float:
    """
    Computes cosine similarity between two normalized voice embeddings.
    Returns a score between -1.0 and 1.0 (typically 0.0 to 1.0 for valid speech).
    Higher score = stronger similarity.
    """
    arr1 = np.asarray(emb1, dtype=np.float32)
    arr2 = np.asarray(emb2, dtype=np.float32)
    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)
    if norm1 < 1e-8 or norm2 < 1e-8:
        return 0.0
    return float(np.dot(arr1, arr2) / (norm1 * norm2))
