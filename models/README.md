# SnapClass Pretrained Biometric Models

This directory contains the lightweight neural network models used for local, cloud-compatible face detection and face recognition in SnapClass.

## 1. YuNet Face Detection Model
- **Filename:** `face_detection_yunet_2023mar.onnx`
- **Architecture:** YuNet CNN
- **Task:** Fast face detection & 5-point facial landmark localization
- **Source:** [OpenCV Zoo - face_detection_yunet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
- **License:** [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- **File Size:** 232,589 bytes
- **SHA-256:** `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`

## 2. SFace Face Recognition Model
- **Filename:** `face_recognition_sface_2021dec.onnx`
- **Architecture:** SFace (Sigmoid-Constrained Hypersphere Loss)
- **Task:** 128-dimensional biometric facial feature representation
- **Source:** [OpenCV Zoo - face_recognition_sface](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface)
- **License:** [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- **File Size:** 38,696,353 bytes
- **SHA-256:** `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`

## Runtime Verification
These models are loaded via OpenCV's `cv2.FaceDetectorYN` and `cv2.FaceRecognizerSF` APIs in `src/ai/face_engine.py`. They operate entirely in CPU memory without requiring C++ toolchains, external GPU dependencies, or runtime downloads.
