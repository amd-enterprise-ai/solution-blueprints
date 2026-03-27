<!--
Copyright © Advanced Micro Devices, Inc., or its affiliates.

SPDX-License-Identifier: MIT
-->

# MRI Analysis Tool

## AI-powered MRI analysis with deep learning and LLM insights

A medical imaging analysis tool that combines computer vision, deep learning, and large language model reporting to analyze MRI scans and provide structured findings.

## Features

- Multi-format support: DICOM (`.dcm`), NIfTI (`.nii`, `.nii.gz`), and standard images (`.png`, `.jpg`, `.jpeg`)
- Robust loading + normalization:
  - DICOM decoding (pydicom), NIfTI decoding (nibabel), image fallback (OpenCV)
  - Intensity normalization to 8-bit for consistent downstream processing
- Image preprocessing:
  - Contrast enhancement using CLAHE (OpenCV)
  - Noise reduction using Gaussian filtering (OpenCV)
- Tissue segmentation:
  - K-means clustering (scikit-learn) with per-cluster pixel distribution statistics
- Anomaly detection:
  - Simple statistical thresholding (mean + 2.5×std) with connected-component region counting (SciPy)
  - Visualization overlay to highlight detected regions when present
- Quantitative measurements:
  - Image dimensions, intensity statistics, and signal-to-noise ratio
  - Optional physical size estimates when pixel spacing metadata is available
- Gradio-based web interface for interactive analysis and result review
- LLM-assisted draft medical report (Markdown) and follow-up Q&A chat

## Architecture diagram
<picture>
  <source media="(prefers-color-scheme: light)" srcset="Architecture_Diagram_Enterprise_AI_Solution_Blueprints_Light.png">
  <source media="(prefers-color-scheme: dark)" srcset="Architecture_Diagram_Enterprise_AI_Solution_Blueprints_Dark.png">
  <img alt="The MRI Scan application runs inside a single container. It is served by an AIM LLM deployed beside it." src="architecture-diagram-light-scheme.png">
</picture>

## Usage

1. Upload an MRI scan file.
   - Supported formats: DICOM (`.dcm`), NIfTI (`.nii`, `.nii.gz`), and standard images (`.png`, `.jpg`, `.jpeg`).
2. Provide optional patient context.
3. Select the MRI type and run the analysis.
4. Review the visualization, metrics, and report output.

## Example MRI scans

If you need sample MRI scans to test with, these public resources are a good starting point (always review each dataset's license/terms and any access requirements):

- The Cancer Imaging Archive (TCIA): https://www.cancerimagingarchive.net/ (multiple MRI collections)
- OpenNeuro: https://openneuro.org/ (public neuroimaging datasets, often NIfTI)
- fastMRI (NYU/Facebook): https://fastmri.org/ (MRI dataset and tools; access may require agreement)

Additionally, an example abddomen MRI DICOM image `abdomen_MRI.dcm` is included under`./src` as well.

### Disclaimer

This tool is for research and educational use only. It is not intended for clinical diagnosis or treatment.

## Terms of Use

AMD Solution Blueprints are released under the MIT License, which governs the parts of the software and materials created by AMD. Third party software and materials used within the Solution Blueprints are governed by their respective licenses.
