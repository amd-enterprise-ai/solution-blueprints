# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import os
import time
import warnings
from pathlib import Path

import cv2
import gradio as gr
import matplotlib.pyplot as plt
import numpy as np
import requests
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from scipy import ndimage

warnings.filterwarnings("ignore")

llm: ChatOpenAI | None = None


def readiness_check():
    """Check if the OpenAI-compatible endpoint is available."""
    try:
        models_url = os.environ["OPENAI_API_BASE_URL"] + "/models"
        r = requests.get(models_url, timeout=2)
        if r.status_code == 200:
            return (r.json()["data"][0]["id"], 200)
        return (r.reason, r.status_code)
    except requests.exceptions.RequestException:
        return ("Error", 0)


def init_llm():
    """Initialize the LLM using an OpenAI-compatible endpoint."""
    global llm

    output, status_code = readiness_check()

    if status_code == 200:
        model_name = output
        llm = ChatOpenAI(
            model_name=model_name,
            openai_api_base=os.environ["OPENAI_API_BASE_URL"],
            openai_api_key="dummy",
            temperature=0.1,
        )
    else:
        raise gr.Error("Couldn't initialize LLM - vLLM service may not be ready.")


medical_analysis_prompt = PromptTemplate(
    input_variables=["image_type", "findings", "measurements", "patient_info", "technical_params"],
    template="""
You are a radiologist AI assistant analyzing MRI scans. Provide a professional medical analysis based on the following data.

Use Markdown formatting with clear section headings.

Image Type (user-provided context, may be incorrect): {image_type}
Technical Parameters: {technical_params}
Patient Information: {patient_info}

Quantitative Findings:
{findings}

Measurements:
{measurements}

Please provide:
1. **Clinical Impression**: Overall assessment
2. **Detailed Findings**: Systematic analysis
3. **Quantitative Analysis**: Interpretation of measurements/statistics
4. **Recommendations**: Follow-up / additional imaging suggestions
5. **Technical Quality**: Image quality and acquisition notes

Important: This is for educational/research purposes. All clinical decisions must be made by qualified medical professionals.
""",
)


def _dict_to_kv_table(data: dict | None) -> list[list[str]]:
    if not data:
        return []
    rows: list[list[str]] = []
    for key, value in data.items():
        rows.append([str(key), str(value)])
    return rows


def _tissue_stats_to_table(tissue_stats: dict | None) -> list[list[str]]:
    if not tissue_stats:
        return []
    rows: list[list[str]] = []
    for cluster_name, stats in tissue_stats.items():
        pixel_count = ""
        percentage = ""
        if isinstance(stats, dict):
            pixel_count = str(stats.get("pixel_count", ""))
            percentage = str(stats.get("percentage", ""))
        rows.append([str(cluster_name), pixel_count, percentage])
    return rows


class MRIProcessor:
    def __init__(self):
        pass

    @staticmethod
    def _normalize_to_uint8(image: np.ndarray | None) -> np.ndarray | None:
        if image is None:
            return None

        arr = np.asarray(image, dtype=np.float32)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

        vmin = float(np.min(arr))
        vmax = float(np.max(arr))
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            return np.zeros(arr.shape, dtype=np.uint8)

        scaled = (arr - vmin) / (vmax - vmin)
        scaled = np.clip(scaled, 0.0, 1.0)
        return (scaled * 255.0).astype(np.uint8)

    def load_dicom(self, dicom_path):
        """Load DICOM file."""
        try:
            import pydicom

            ds = pydicom.dcmread(dicom_path)
            image_data = ds.pixel_array.astype(np.float32)

            # Handle multi-frame DICOM by selecting a representative slice/frame
            if image_data.ndim == 3:
                mid = image_data.shape[0] // 2
                image_data = image_data[mid]
            elif image_data.ndim == 4:
                mid = image_data.shape[0] // 2
                image_data = image_data[mid, :, :, 0]

            image = self._normalize_to_uint8(image_data)

            metadata = {
                "patient_id": getattr(ds, "PatientID", "Unknown"),
                "study_date": getattr(ds, "StudyDate", "Unknown"),
                "modality": getattr(ds, "Modality", "Unknown"),
                "body_part": getattr(ds, "BodyPartExamined", "Unknown"),
                "slice_thickness": getattr(ds, "SliceThickness", "Unknown"),
                "pixel_spacing": getattr(ds, "PixelSpacing", "Unknown"),
            }

            return image, metadata
        except Exception as e:
            print(f"Error loading DICOM: {e}")
            return None, None

    def load_nifti(self, nifti_path):
        """Load NIfTI file."""
        try:
            import nibabel as nib

            img = nib.load(nifti_path)
            image_data = img.get_fdata(dtype=np.float32)
            original_shape = tuple(image_data.shape)

            slice_index = None
            time_index = None

            if image_data.ndim == 4:
                time_index = 0
                image_data = image_data[:, :, :, time_index]

            if image_data.ndim == 3:
                slice_index = image_data.shape[2] // 2
                image_data = image_data[:, :, slice_index]

            if image_data.ndim != 2:
                raise ValueError(f"Unsupported NIfTI image dimensionality: {image_data.ndim}D")

            image = self._normalize_to_uint8(image_data)

            metadata = {
                "shape": original_shape,
                "view_shape": tuple(image_data.shape),
                "affine": img.affine.tolist(),
                "header": str(img.header)[:200] + "...",
                "selected_slice_index": slice_index,
                "selected_time_index": time_index,
            }

            return image, metadata
        except Exception as e:
            print(f"Error loading NIfTI: {e}")
            return None, None

    def preprocess_image(self, image):
        """Preprocess MRI image."""
        if image is None:
            return None

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(image)
        filtered = cv2.GaussianBlur(enhanced, (3, 3), 0)
        return filtered

    def segment_brain_tissue(self, image):
        """Segment tissue using K-means clustering."""
        if image is None:
            return None, {}

        from sklearn.cluster import KMeans

        pixels = image.reshape((-1, 1))
        kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
        labels = kmeans.fit_predict(pixels)
        segmented = labels.reshape(image.shape)

        unique, counts = np.unique(labels, return_counts=True)
        total_pixels = len(pixels)

        tissue_stats = {}
        for cluster, count in zip(unique, counts):
            percentage = (count / total_pixels) * 100
            tissue_stats[f"Tissue_Cluster_{cluster}"] = {"pixel_count": int(count), "percentage": round(percentage, 2)}

        return segmented, tissue_stats

    def detect_anomalies(self, image):
        """Detect potential anomalies using a simple intensity threshold."""
        if image is None:
            return None, {}

        mean_intensity = float(np.mean(image))
        std_intensity = float(np.std(image))
        threshold = mean_intensity + 2.5 * std_intensity
        anomalies = image > threshold

        _, num_features = ndimage.label(anomalies)

        anomaly_stats = {
            "num_anomalous_regions": int(num_features),
            "anomalous_pixel_percentage": (float(np.sum(anomalies)) / float(image.size)) * 100.0,
            "mean_intensity": round(mean_intensity, 2),
            "std_intensity": round(std_intensity, 2),
            "intensity_threshold": round(float(threshold), 2),
        }

        return anomalies, anomaly_stats

    def calculate_measurements(self, image, pixel_spacing=None):
        """Calculate various measurements from the MRI."""
        if image is None:
            return {}

        measurements = {
            "image_dimensions": f"{image.shape[0]} x {image.shape[1]} pixels",
            "total_pixels": int(image.size),
            "mean_intensity": round(float(np.mean(image)), 2),
            "max_intensity": int(np.max(image)),
            "min_intensity": int(np.min(image)),
            "intensity_std": round(float(np.std(image)), 2),
            "signal_to_noise_ratio": round(float(np.mean(image)) / (float(np.std(image)) + 1e-8), 2),
        }

        if pixel_spacing and pixel_spacing != "Unknown":
            try:
                spacing = float(pixel_spacing[0]) if isinstance(pixel_spacing, list) else float(pixel_spacing)
                measurements["pixel_spacing_mm"] = spacing
                measurements["physical_width_mm"] = round(image.shape[1] * spacing, 2)
                measurements["physical_height_mm"] = round(image.shape[0] * spacing, 2)
            except (ValueError, TypeError):
                warnings.warn(
                    f"Failed to interpret pixel_spacing '{pixel_spacing}' as float; "
                    "physical size measurements will be omitted."
                )

        return measurements

    def generate_visualization(self, original, preprocessed, segmented, anomalies):
        """Generate a 2x2 visualization panel."""
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))

        axes[0, 0].imshow(original, cmap="gray")
        axes[0, 0].set_title("Original MRI", fontsize=14, fontweight="bold")
        axes[0, 0].axis("off")

        axes[0, 1].imshow(preprocessed, cmap="gray")
        axes[0, 1].set_title("Enhanced (CLAHE + Gaussian Filter)", fontsize=14, fontweight="bold")
        axes[0, 1].axis("off")

        axes[1, 0].imshow(segmented, cmap="viridis")
        axes[1, 0].set_title("Tissue Segmentation (K-means)", fontsize=14, fontweight="bold")
        axes[1, 0].axis("off")

        # Always render a meaningful view: show the preprocessed image, and overlay anomalies.
        axes[1, 1].imshow(preprocessed, cmap="gray")
        if anomalies is not None and np.any(anomalies):
            overlay = np.zeros_like(preprocessed, dtype=np.uint8)
            overlay[anomalies] = 255
            axes[1, 1].imshow(overlay, cmap="Reds", alpha=0.35)
            subtitle = "(overlay)"
        else:
            subtitle = "(none detected)"
        axes[1, 1].set_title(f"Anomaly Detection {subtitle}", fontsize=14, fontweight="bold")
        axes[1, 1].axis("off")

        plt.tight_layout()
        return fig


def process_mri_scan(file_path, patient_info="Not provided", image_type="MRI Brain"):
    """Process an MRI scan and stream progress updates."""
    if file_path is None:
        yield None, "Please upload an MRI file", [], "", [], []
        return

    processor = MRIProcessor()
    start_time = time.time()

    try:
        yield None, "Loading image...", [], "", [], []
        file_path_str = str(file_path)

        file_path_lower = file_path_str.lower()
        if file_path_lower.endswith(".nii.gz"):
            file_extension = ".nii.gz"
        else:
            file_extension = Path(file_path_lower).suffix

        if file_extension == ".dcm":
            image, metadata = processor.load_dicom(file_path_str)
            pixel_spacing = metadata.get("pixel_spacing", None) if metadata else None
        elif file_extension in [".nii", ".nii.gz"]:
            image, metadata = processor.load_nifti(file_path_str)
            pixel_spacing = None
        else:
            image = cv2.imread(file_path_str, cv2.IMREAD_GRAYSCALE)
            metadata = {"file_type": "standard_image"}
            pixel_spacing = None

            if image is None:
                nifti_image, nifti_metadata = processor.load_nifti(file_path_str)
                if nifti_image is not None:
                    image, metadata = nifti_image, nifti_metadata
                    file_extension = ".nii.gz" if file_path_lower.endswith(".nii.gz") else ".nii"

        if image is None:
            yield None, "Error: Could not load the image file", [], "", [], []
            return

        yield None, "Preprocessing image...", [], "", [], []
        preprocessed = processor.preprocess_image(image)

        yield None, "Segmenting tissue...", [], "", [], []
        segmented, tissue_stats = processor.segment_brain_tissue(preprocessed)

        yield None, "Detecting anomalies...", [], "", [], []
        anomalies, anomaly_stats = processor.detect_anomalies(preprocessed)

        yield None, "Calculating measurements...", [], "", [], []
        measurements = processor.calculate_measurements(image, pixel_spacing)

        yield None, "Generating visualization...", [], "", [], []
        viz_fig = processor.generate_visualization(image, preprocessed, segmented, anomalies)

        findings_text = f"""
Tissue Segmentation Analysis:
{tissue_stats}

Anomaly Detection Results:
{anomaly_stats}

Image Metadata:
{metadata}
""".strip()

        measurements_text = f"""
Image Measurements:
{measurements}
""".strip()

        technical_params = f"File type: {file_extension}, Processing time: {time.time() - start_time:.2f}s"

        yield viz_fig, "Generating AI report...", [], "", [], []

        if llm is None:
            init_llm()

        assert llm is not None

        prompt = medical_analysis_prompt.format(
            image_type=image_type,
            findings=findings_text,
            measurements=measurements_text,
            patient_info=patient_info,
            technical_params=technical_params,
        )

        response = llm.invoke(prompt)
        ai_analysis = response.content if hasattr(response, "content") else str(response)

        summary_stats = {
            "Processing Time": f"{time.time() - start_time:.2f} seconds",
            "Image Dimensions": measurements.get("image_dimensions", "Unknown"),
            "Number of Tissue Clusters": str(len(tissue_stats)),
            "Anomalous Regions Detected": str(anomaly_stats.get("num_anomalous_regions", 0)),
            "Signal-to-Noise Ratio": str(measurements.get("signal_to_noise_ratio", "N/A")),
            "Mean Intensity": str(measurements.get("mean_intensity", "N/A")),
        }

        yield (
            viz_fig,
            "✅ MRI Analysis Completed Successfully",
            _dict_to_kv_table(summary_stats),
            ai_analysis,
            _tissue_stats_to_table(tissue_stats),
            _dict_to_kv_table(anomaly_stats),
        )
        return

    except Exception as e:
        yield None, f"❌ Error processing MRI: {str(e)}", [], "", [], []
        return


def doctor_chat(
    report_markdown: str,
    user_message: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Answer a user follow-up question based on the generated report.

    Note: This is an educational demo and is not medical advice.
    """
    return doctor_chat_with_history(history=history, report_markdown=report_markdown, user_message=user_message)


def doctor_chat_with_history(
    history: list[dict[str, str]] | None,
    report_markdown: str,
    user_message: str,
    *,
    max_history_messages: int = 10,
) -> str:
    """Chat-style Q&A over the report using prior conversation context.

    The prompt is designed to:
    - Avoid re-stating the full report on every follow-up.
    - Avoid claims of being a medical professional.
    - Always include a clear non-medical-advice disclaimer.
    """
    if llm is None:
        init_llm()

    assert llm is not None

    def _content_to_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, dict):
            # Common shapes from chat UIs / multimodal payloads.
            for key in ("text", "value", "content"):
                inner = value.get(key)
                if isinstance(inner, str) and inner.strip():
                    return inner
            return str(value)
        if isinstance(value, (list, tuple)):
            parts: list[str] = []
            for item in value:
                text = _content_to_text(item)
                if text.strip():
                    parts.append(text)
            return "\n".join(parts)
        return str(value)

    trimmed_history = []
    if history:
        # Keep only the most recent messages to avoid huge prompts.
        trimmed_history = history[-max_history_messages:]

    history_text_lines: list[str] = []
    for msg in trimmed_history:
        role = (msg.get("role") or "").strip().lower()
        content = _content_to_text(msg.get("content")).strip()
        if not content:
            continue
        if role not in {"user", "assistant"}:
            role = "assistant" if role else "assistant"
        history_text_lines.append(f"{role.upper()}: {content}")
    history_text = "\n".join(history_text_lines).strip()

    prompt = (
        "You are an AI assistant for an MRI analysis demo. You are NOT a clinician and you must NOT claim to be a medical professional. "
        "Do not imply you are providing medical advice.\n\n"
        "Goal: answer the user's question conversationally and concisely, using the report as context. "
        "Do NOT repeat the full report unless the user explicitly asks for a full reprint. "
        "If the user asks follow-up questions, assume the report has already been discussed and respond appropriately.\n\n"
        "Style requirements:\n"
        "- Use Markdown.\n"
        "- Prefer 3-8 sentences unless the user asks for more detail.\n"
        "- If uncertain, say what you can infer from the report and what can't be determined.\n"
        "- End with: 'Not medical advice.'\n\n"
        "MRI REPORT (context):\n"
        f"{report_markdown.strip()}\n\n"
        "CONVERSATION SO FAR:\n"
        f"{history_text if history_text else '(no prior messages)'}\n\n"
        "USER QUESTION:\n"
        f"{user_message.strip()}\n"
    )
    response = llm.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)
