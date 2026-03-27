# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

import gradio as gr
from mri_analysis import doctor_chat_with_history, process_mri_scan


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = rgb
    r_i = max(0, min(255, int(round(r))))
    g_i = max(0, min(255, int(round(g))))
    b_i = max(0, min(255, int(round(b))))
    return f"#{r_i:02X}{g_i:02X}{b_i:02X}"


def _mix_hex(a: str, b: str, t: float) -> str:
    """Mix hex color a toward b by factor t in [0,1]."""
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex((ar + (br - ar) * t, ag + (bg - ag) * t, ab + (bb - ab) * t))


def _make_gradio_color(name: str, base_hex: str) -> gr.themes.Color:
    """Create a Gradio Color palette (50..950) from a base hex color.

    Gradio themes expect a palette. We approximate by mixing toward white for
    lighter stops and toward black for darker stops.
    """
    white = "#FFFFFF"
    black = "#000000"

    return gr.themes.Color(
        c50=_mix_hex(base_hex, white, 0.90),
        c100=_mix_hex(base_hex, white, 0.80),
        c200=_mix_hex(base_hex, white, 0.65),
        c300=_mix_hex(base_hex, white, 0.50),
        c400=_mix_hex(base_hex, white, 0.30),
        c500=base_hex.upper(),
        c600=_mix_hex(base_hex, black, 0.15),
        c700=_mix_hex(base_hex, black, 0.30),
        c800=_mix_hex(base_hex, black, 0.45),
        c900=_mix_hex(base_hex, black, 0.60),
        c950=_mix_hex(base_hex, black, 0.72),
        name=name,
    )


def create_interface():
    custom_css = """
    * { font-family: Arial, sans-serif !important; font-size: 16px; }

    /* AMD palette */
    :root {
        --amd-blue: #00C2DE;
        --amd-gray: #636466;
        --amd-orange: #E15310;
        --amd-black: #000000;
        --amd-white: #FFFFFF;
    }

    /* Primary button */
    .primary {
        background: var(--amd-blue) !important;
        border: none !important;
        color: var(--amd-white) !important;
        padding: 12px 24px !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }
    .primary:hover { opacity: 0.92 !important; }

    /* Tabs */
    .tab-nav button.selected {
        color: var(--amd-blue) !important;
        border-bottom: 2px solid var(--amd-blue) !important;
    }
    .tab-nav button:hover {
        border-color: var(--amd-blue) !important;
        color: var(--amd-blue) !important;
        background: rgba(0, 194, 222, 0.06) !important;
    }

    /* Typography: keep contrast in light/dark mode */
    h1, h2, h3 { font-weight: 700 !important; }

    @media (prefers-color-scheme: light) {
        h1, h2, h3 { color: var(--amd-black) !important; }
        .prose, .prose p, .prose li { color: var(--amd-black) !important; }
    }

    @media (prefers-color-scheme: dark) {
        h1, h2, h3 { color: var(--amd-white) !important; }
        .prose, .prose p, .prose li { color: var(--amd-white) !important; }
    }
    .amd-subtitle { color: rgba(255,255,255,0.92); font-weight: 600; }

    /* Inputs focus */
    input:focus, textarea:focus, select:focus {
        border-color: var(--amd-blue) !important;
        box-shadow: 0 0 0 2px rgba(0, 194, 222, 0.12) !important;
    }

    /* File upload */
    .gr-file {
        border: 2px dashed var(--amd-blue) !important;
        border-radius: 12px !important;
        padding: 16px !important;
    }

    /* Simple hover tooltip */
    .amd-tooltip { position: relative; display: inline-flex; align-items: center; gap: 6px; }
    .amd-tooltip-icon {
        display: inline-flex;
        width: 20px;
        height: 20px;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        border: 1px solid var(--amd-blue);
        color: var(--amd-blue);
        font-weight: 700;
        cursor: help;
        user-select: none;
        line-height: 1;
    }
    .amd-tooltip-text {
        visibility: hidden;
        opacity: 0;
        transition: opacity 0.12s ease;
        position: absolute;
        top: 28px;
        left: 0;
        z-index: 20;
        background: var(--amd-white);
        color: var(--amd-gray);
        border: 1px solid rgba(99, 100, 102, 0.25);
        border-left: 4px solid var(--amd-orange);
        border-radius: 10px;
        padding: 10px 12px;
        width: 280px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.08);
    }
    .amd-tooltip:hover .amd-tooltip-text { visibility: visible; opacity: 1; }
    """

    amd_blue = _make_gradio_color("amd-blue", "#00C2DE")
    amd_gray = _make_gradio_color("amd-gray", "#636466")
    theme = gr.themes.Soft(primary_hue=amd_blue, secondary_hue=amd_gray, neutral_hue=amd_gray)

    with gr.Blocks(title="Advanced MRI Analysis Tool", theme=theme, css=custom_css) as interface:
        report_state = gr.State("")
        gr.HTML(
            """
            <div style='position: relative; padding: 22px 24px; background: #00C2DE; border-radius: 15px; margin-bottom: 16px; color: white;'>
                <img src='https://upload.wikimedia.org/wikipedia/commons/7/7c/AMD_Logo.svg' alt='AMD Logo' style='position: absolute; top: 18px; right: 22px; height: 40px; width: auto;' />
                <div style='padding-right: 120px;'>
                    <h1 style='margin: 0; color: white; font-size: 2.25em; font-weight: 800;'>Advanced MRI Analysis Tool</h1>
                    <div class='amd-subtitle' style='margin-top: 8px; font-size: 1.05em;'>
                        Upload an MRI scan to generate visualizations, quantitative measurements, and an LLM-assisted draft report.
                    </div>
                </div>
            </div>
            """
        )

        gr.Markdown(
            """
### Usage Instructions

1. **Upload an MRI scan** (DICOM `.dcm`, NIfTI `.nii`/`.nii.gz`, or standard images `.png`/`.jpg`/`.jpeg`).
   - Example file: `src/abdomen_MRI.dcm` (bundled with the blueprint repository)
2. **Patient Information** (optional) improves report context.
3. **Image Type** is optional; it only guides how the AI report is phrased and does **not** change image processing.
4. Click **Analyze MRI Scan** and review the tabs.
"""
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Upload & Configuration")
                file_input = gr.File(
                    label="Upload MRI Scan",
                    file_types=[".dcm", ".nii", ".nii.gz", ".gz", ".png", ".jpg", ".jpeg"],
                    type="filepath",
                )
                patient_info = gr.Textbox(
                    label="Patient Information (Optional)",
                    info="Optional. Used only to add context to the AI report and chat; it does not change image processing or metrics.",
                    placeholder="Age: 45, Gender: Male, Clinical History: ...",
                    lines=3,
                )
                image_type = gr.Dropdown(
                    choices=["MRI Abdomen", "MRI Brain", "MRI Knee", "MRI Spine", "Other"],
                    label="Image Type (Optional)",
                    info="Optional. Used only to tailor the AI report language; processing/metrics are unchanged.",
                    value="MRI Abdomen",
                )

                analyze_btn = gr.Button("Analyze MRI Scan", variant="primary", size="lg")
                cancel_btn = gr.Button("Cancel", variant="secondary")
                gr.HTML(
                    """
                    <div class='amd-tooltip' style='margin-top:10px;margin-bottom:2px;'>
                        <span class='amd-tooltip-icon'>i</span>
                        <span style='color:#636466;font-weight:600;'>Large files</span>
                        <div class='amd-tooltip-text'>Files larger than 100MB can take a long time to process (upload + decoding + clustering).</div>
                    </div>
                    """
                )

            with gr.Column(scale=2):
                gr.Markdown("### Analysis Results")

                status_output = gr.Textbox(label="Status", interactive=False)

                with gr.Tabs():
                    with gr.TabItem("Visualizations"):
                        plot_output = gr.Plot(label="MRI Analysis Visualization")

                    with gr.TabItem("AI Medical Report"):
                        gr.Markdown("#### AI-Generated Medical Analysis")
                        ai_analysis_output = gr.Markdown()

                    with gr.TabItem("Technical Analysis"):
                        tissue_analysis_output = gr.Dataframe(
                            headers=["Cluster", "Pixel Count", "Percentage"],
                            label="Tissue Segmentation Results",
                            interactive=False,
                        )
                        anomaly_analysis_output = gr.Dataframe(
                            headers=["Metric", "Value"],
                            label="Anomaly Detection Results",
                            interactive=False,
                        )

                    with gr.TabItem("Summary Statistics"):
                        summary_output = gr.Dataframe(
                            headers=["Metric", "Value"],
                            label="Processing Summary",
                            interactive=False,
                        )

                gr.Markdown(
                    """
### Chat with AI Medical Assistant
Ask follow-up questions about your MRI report below.

**Disclaimer:** This chat is for educational/demo purposes only and is **not medical advice**.
"""
                )
                chatbot = gr.Chatbot(label="Chat with AI Medical Assistant")
                chat_input = gr.Textbox(
                    label="Your question to the AI Medical Assistant",
                    placeholder="Type your question here and press Enter...",
                    value="Can you summarize the key findings and suggest reasonable next steps?",
                    interactive=False,
                )

                def _normalize_history(history):
                    if not history:
                        return []
                    normalized = []
                    for msg in history:
                        if isinstance(msg, dict) and "role" in msg and "content" in msg:
                            normalized.append(msg)
                        elif isinstance(msg, (list, tuple)) and len(msg) == 2:
                            user, assistant = msg
                            normalized.append({"role": "user", "content": user})
                            normalized.append({"role": "assistant", "content": assistant})
                    return normalized

                def doctor_chat_ui(history, user_message, report):
                    normalized_history = _normalize_history(history)

                    report_text = report or ""

                    content = doctor_chat_with_history(
                        history=normalized_history,
                        report_markdown=report_text,
                        user_message=user_message,
                    )
                    normalized_history.append({"role": "user", "content": user_message})
                    normalized_history.append({"role": "assistant", "content": content})
                    return normalized_history, ""

                chat_input.submit(
                    fn=doctor_chat_ui,
                    inputs=[chatbot, chat_input, report_state],
                    outputs=[chatbot, chat_input],
                )

        def _on_analyze_start():
            # Clear chat and disable input while analysis is running.
            return [], gr.update(value="", interactive=False), ""

        def _on_analyze_done(report_md: str | None):
            report_text = report_md or ""
            seeded_history = [
                {
                    "role": "assistant",
                    "content": "Report generated. Ask a follow-up question when ready.\n\nNot medical advice.",
                }
            ]
            return seeded_history, gr.update(interactive=True), report_text

        start_event = analyze_btn.click(fn=_on_analyze_start, inputs=None, outputs=[chatbot, chat_input, report_state])

        analyze_event = start_event.then(
            fn=process_mri_scan,
            inputs=[file_input, patient_info, image_type],
            outputs=[
                plot_output,
                status_output,
                summary_output,
                ai_analysis_output,
                tissue_analysis_output,
                anomaly_analysis_output,
            ],
        )

        analyze_event.then(
            fn=_on_analyze_done, inputs=[ai_analysis_output], outputs=[chatbot, chat_input, report_state]
        )

        cancel_btn.click(fn=None, cancels=[analyze_event])

    return interface
