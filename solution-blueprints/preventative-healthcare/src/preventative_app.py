# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Some of the code in this file was generated using AI with GitHub CoPilot, and modified by the author.
# The code is a simulation of a healthcare system that uses AI agents to manage patient outreach
# Author: Benjamin Consolvo
# Originally created in 2025
# Heavily modified from original code by Mick Lynch:
# https://medium.com/@micklynch_6905/hospitalgpt-managing-a-patient-population-with-autogen-powered-by-gpt-4-mixtral-8x7b-ef9f54f275f1
# https://github.com/micklynch/hospitalgpt

import asyncio
import contextlib
import io
import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from openai import APIConnectionError, APIStatusError, OpenAI
from preventative_healthcare import (
    DOCTOR_CRITIC_PROMPT,
    EPIDEMIOLOGIST_PROMPT,
    OUTREACH_EMAIL_PROMPT_TEMPLATE,
    USER_PROXY_PROMPT,
    discover_model,
    find_patients,
    target_patients_outreach,
    write_outreach_emails,
)

asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# Streamlit app configuration
st.set_page_config(page_title="Preventative Healthcare Outreach", layout="wide")

# AMD branded header (matching MRI-Doc style)
st.markdown(
    """
    <div style='position: relative; padding: 25px; background: linear-gradient(135deg, #00C2DE 0%, #008AA8 100%); border-radius: 15px; margin-bottom: 25px; color: white;'>
        <img src='https://upload.wikimedia.org/wikipedia/commons/7/7c/AMD_Logo.svg' alt='AMD Logo' style='position: absolute; top: 20px; right: 25px; height: 40px; width: auto;' />
        <div style='padding-right: 120px;'>
            <h1 style='margin: 0; color: white; font-size: 2.5em; font-weight: 700;'>Preventative Healthcare Outreach</h1>
            <h3 style='margin: 10px 0 0 0; color: rgba(255,255,255,0.9); font-size: 1.3em; font-weight: 600;'>Cloud Native Agentic Workflows in Healthcare</h3>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    Welcome to your preventative healthcare outreach agentic system, built using the open-source framework [AutoGen](https://github.com/microsoft/autogen).

    To improve patient health outcomes, healthcare providers are looking for ways to reach out to patients who may be eligible for preventative screenings. This system is designed to help you automate the process of identifying patients who meet specific screening criteria and generating personalized emails to encourage them to schedule their screenings.

    The user provides a very broad screening criteria, and then the system uses AI agents to generate patient-specific criteria, filter patients from a given database, and ultimately write outreach emails to suggest to patients that they schedule a screening. To get the agents working, you can use the sidebar on the left of the UI to:
    1. Customize the prompts for the agents. They use natural language understanding to execute on a workflow. You can use the default ones to get started, and modify to your more specific needs.
    2. Select default (synthetically generated) patient data, or upload your own CSV file.
    3. Describe a medical screening task.
    4. Click on "Generate Outreach Emails" to create draft emails to patients (.txt files with email drafts).
    """
)

# Initialize session state for prompts if not already present
if "user_proxy_prompt" not in st.session_state:
    st.session_state.user_proxy_prompt = USER_PROXY_PROMPT
if "epidemiologist_prompt" not in st.session_state:
    st.session_state.epidemiologist_prompt = EPIDEMIOLOGIST_PROMPT
if "doctor_critic_prompt" not in st.session_state:
    st.session_state.doctor_critic_prompt = DOCTOR_CRITIC_PROMPT
if "outreach_email_prompt" not in st.session_state:
    st.session_state.outreach_email_prompt = OUTREACH_EMAIL_PROMPT_TEMPLATE

# --- Test LLM connection (simple question to verify backend) ---
with st.expander("Ask something to the AI Doctor", expanded=False):
    st.caption("Send a test question to the AI and see the raw answer.")
    test_question = st.text_input("question about symptoms", value="What are the symptoms", key="ai_dr_question")
    if st.button("Ask LLM", key="llm_test_btn"):
        base_url = (st.secrets.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
        api_key = (st.secrets.get("OPENAI_API_KEY") or "").strip()
        if not base_url:
            st.error("OPENAI_BASE_URL is not set. Configure the LLM endpoint (e.g. via Helm).")
        else:
            with st.spinner("Calling LLM..."):
                try:
                    client = OpenAI(api_key=api_key or "dummy", base_url=base_url)
                    test_model = discover_model(base_url, api_key)
                    r = client.chat.completions.create(
                        model=test_model,
                        messages=[{"role": "user", "content": test_question}],
                        max_tokens=256,
                        temperature=0,
                    )
                    answer = r.choices[0].message.content if r.choices else "(no content)"
                    st.success("AI doctor responded:")
                    st.text_area("Answer", value=answer, height=200, disabled=True, key="llm_test_answer")
                except APIStatusError as e:
                    st.error(f"LLM API error (HTTP {e.status_code}): {getattr(e, 'message', str(e))}")
                except APIConnectionError as e:
                    st.error(f"Cannot reach LLM: {e}")

# --- Activity/log screen for agent communication ---
st.markdown("### Activity Log")
log_container = st.container()
with log_container:
    with st.expander("Real-time Log", expanded=True):
        log_placeholder = st.empty()

# --- Move user inputs, instructions, and CSV column info to sidebar ---
with st.sidebar:
    # Add a section for customizing prompts at the top of the sidebar
    st.markdown("### Customize Agent Prompts")
    st.caption(
        "The agents use LLMs and natural language understanding (NLU) to organize the tasks they need to accomplish. You can modify the prompts for each agent below; these prompts are given to the agents so that they can work together to produce the final outreach emails for the preventative healthcare task at hand."
    )

    # User Proxy Prompt
    with st.expander("User Proxy Prompt"):
        user_prompt = st.text_area(
            "User Proxy Prompt",
            value=st.session_state.user_proxy_prompt,
            height=300,
            key="user_proxy_input",
            label_visibility="hidden",
            # Add these style properties to preserve whitespace formatting
            help="",
            placeholder="",
            disabled=False,
            # Use CSS to preserve whitespace formatting
            max_chars=None,
        )
        st.session_state.user_proxy_prompt = user_prompt

    # Epidemiologist Prompt
    with st.expander("Epidemiologist Prompt"):
        epi_prompt = st.text_area(
            "Epidemiologist Prompt",
            value=st.session_state.epidemiologist_prompt,
            height=300,
            key="epidemiologist_input",
            label_visibility="hidden",
            help="",
            placeholder="",
            disabled=False,
            max_chars=None,
        )
        st.session_state.epidemiologist_prompt = epi_prompt

    # Doctor Critic Prompt
    with st.expander("Doctor Critic Prompt"):
        doc_prompt = st.text_area(
            "Doctor Critic Prompt",
            value=st.session_state.doctor_critic_prompt,
            height=300,
            key="doctor_critic_input",
            label_visibility="hidden",
            help="",
            placeholder="",
            disabled=False,
            max_chars=None,
        )
        st.session_state.doctor_critic_prompt = doc_prompt

    # Outreach Email Prompt Template
    with st.expander("Email Template Prompt"):
        email_prompt = st.text_area(
            "Email Template Prompt",
            value=st.session_state.outreach_email_prompt,
            height=300,
            key="email_template_input",
            label_visibility="hidden",
            help="",
            placeholder="",
            disabled=False,
            max_chars=None,
        )
        st.session_state.outreach_email_prompt = email_prompt

    # Add custom CSS to preserve whitespace in text areas while ensuring content fits
    st.markdown(
        """
        <style>
        .stTextArea textarea {
            font-family: monospace;
            white-space: pre-wrap !important;  /* Use pre-wrap to preserve whitespace but allow wrapping */
            word-wrap: break-word !important;  /* Ensure words break to next line if needed */
            line-height: 1.4;
            tab-size: 2;                       /* Reduce tab size to save space */
            padding: 8px;
            font-size: 0.9em;                  /* Slightly smaller font to fit more content */
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Reset prompts button
    if st.button("Reset Prompts to Default"):
        st.session_state.user_proxy_prompt = USER_PROXY_PROMPT
        st.session_state.epidemiologist_prompt = EPIDEMIOLOGIST_PROMPT
        st.session_state.doctor_critic_prompt = DOCTOR_CRITIC_PROMPT
        st.session_state.outreach_email_prompt = OUTREACH_EMAIL_PROMPT_TEMPLATE
        st.rerun()

    st.markdown("---")

    # Now add the "Get started" section after the prompts
    st.header("Patient Data and Screening Task")

    st.caption(
        "Required CSV columns: patient_id, First Name, Last Name, Email, Patient diagnosis summary, age, gender, condition"
    )

    # Create a container for the default dataset option to control its appearance
    default_dataset_container = st.container()

    # Add the file upload option after the default dataset option
    uploaded_file = st.file_uploader("Upload your own CSV file with patient data", type=["csv"])

    # If a file is uploaded, show a message and disable the default checkbox
    if uploaded_file is not None:
        # Visual indication that custom data is being used
        st.success("✅ Using your uploaded file")

        # Disable the default dataset option with clear visual feedback
        with default_dataset_container:
            st.markdown(
                """
                <div style="opacity: 0.5; pointer-events: none;">
                    <input type="checkbox" disabled> Use default dataset (data/patients.csv)
                    <div style="font-size: 0.8em; color: #999; font-style: italic;">
                        Disabled because custom file is uploaded
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Set use_default to False when a file is uploaded
        use_default = False
    else:
        # No file uploaded, show normal checkbox
        with default_dataset_container:
            use_default = st.checkbox("Use default dataset (data/patients.csv)", value=True)

    st.markdown("For more information about medical screening tasks, you can visit the website below.")
    st.link_button(
        "U.S. Preventive Services Task Force",
        "https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics/uspstf-a-and-b-recommendations",
    )
    screening_task = st.text_input(
        "Enter the medical screening task (e.g., 'Colonoscopy screening').", "Colonoscopy screening"
    )

    # Add contact information section
    st.markdown("---")
    st.subheader("Healthcare Provider Contact Information")
    st.caption("This information will appear in the emails sent to patients")

    # Create three columns for contact info fields
    col1, col2, col3 = st.columns(3)

    with col1:
        provider_name = st.text_input("Provider Name", "AMD, Blueprints team AI ")

    with col2:
        provider_email = st.text_input("Provider Email", "doctor@doctor.com")

    with col3:
        provider_phone = st.text_input("Provider Phone", "123-456-7890")

    # Validate input fields before enabling the button
    required_fields_empty = (
        screening_task.strip() == ""
        or provider_name.strip() == ""
        or provider_email.strip() == ""
        or provider_phone.strip() == ""
    )

    if required_fields_empty:
        st.warning("Please fill in all required fields before proceeding.")
    st.markdown("---")
    # Move the button to the sidebar - disabled if required fields are empty
    generate = st.button("Generate Outreach Emails", disabled=required_fields_empty)

# Explicitly set environment variable to avoid TTY errors
os.environ["PYTHONUNBUFFERED"] = "1"

if generate:
    api_key = st.secrets["OPENAI_API_KEY"]
    base_url = (st.secrets.get("OPENAI_BASE_URL") or "").strip().rstrip("/")

    log_messages = []

    def log(msg):
        log_messages.append(msg)
        log_placeholder.markdown(
            f"""
            <div style="height: 400px; overflow-y: auto; border: 1px solid #cccccc;
                 padding: 15px; border-radius: 5px; background-color: rgba(240, 242, 246, 0.4);
                 color: inherit; font-family: monospace;">
                {"<br>".join(log_messages)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        if not screening_task:
            st.error("Please enter a medical screening task.")
        elif not uploaded_file and not use_default:
            st.error("Please upload a CSV file or select the default dataset.")
        else:
            if uploaded_file:
                patients_file = uploaded_file
            else:
                patients_file = os.path.join(os.path.dirname(__file__), "data/patients.csv")

            try:
                patients_df = pd.read_csv(patients_file)
            except Exception as e:
                st.error(f"Error reading the CSV file: {e}")
                st.stop()

            required_columns = [
                "patient_id",
                "First Name",
                "Last Name",
                "Email",
                "Patient diagnosis summary",
                "age",
                "gender",
                "condition",
            ]
            if not all(col in patients_df.columns for col in required_columns):
                st.error(f"The uploaded CSV file is missing required columns: {required_columns}")
                st.stop()

            env_base_url = (
                (st.secrets.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
            )
            if not env_base_url:
                st.error("OPENAI_BASE_URL is not set. Configure the LLM endpoint (e.g. via Helm).")
                st.stop()

            try:
                model_name = discover_model(env_base_url, api_key)
            except Exception as e:
                st.error(f"Could not discover model from {env_base_url}: {e}")
                st.stop()

            config_list_llama = [
                {"model": model_name, "base_url": env_base_url, "api_key": api_key, "price": [0.0, 0.0]}
            ]
            # config_list_deepseek = list(config_list_llama)

            try:
                log(" <b>Starting agent workflow...</b>")
                log("🧑‍⚕️ <b>Screening task:</b> " + screening_task)
                log("📄 <b>Loaded patient data:</b> {} records".format(len(patients_df)))

                log("🤖 <b>Agent (AIMS LLM model):</b> Generating outreach criteria...")
                criteria = asyncio.run(
                    target_patients_outreach(
                        screening_task,
                        config_list_llama,
                        log_fn=log if "log_fn" in target_patients_outreach.__code__.co_varnames else None,
                        user_proxy_prompt=st.session_state.user_proxy_prompt,
                        epidemiologist_prompt=st.session_state.epidemiologist_prompt,
                        doctor_critic_prompt=st.session_state.doctor_critic_prompt,
                    )
                )
                log("✅ <b>Criteria generated.</b>")

                log(" <b>Agent (AIMS LLM model):</b> Filtering patients based on criteria...")
                filtered_patients, arguments_criteria = asyncio.run(
                    find_patients(
                        criteria,
                        config_list_llama,
                        log_fn=log if "log_fn" in find_patients.__code__.co_varnames else None,
                        patients_file_path=patients_file,
                    )
                )
                log("✅ <b>Patients filtered.</b>")

                if filtered_patients.empty:
                    log(" <b>No patients matched the criteria.</b>")
                    st.warning("No patients matched the criteria.")
                else:
                    openai_client = OpenAI(api_key=api_key, base_url=base_url)

                    log("🤖 <b>Agent (Secretary):</b> Generating outreach emails...")
                    asyncio.run(
                        write_outreach_emails(
                            filtered_patients,
                            screening_task,
                            arguments_criteria,
                            openai_client,
                            config_list_llama[0]["model"],
                            phone=provider_phone,
                            email=provider_email,
                            name=provider_name,
                            log_fn=log if "log_fn" in write_outreach_emails.__code__.co_varnames else None,
                            outreach_email_prompt_template=st.session_state.outreach_email_prompt,
                        )
                    )

                    data_dir = os.path.join(os.path.dirname(__file__), "data")
                    os.makedirs(data_dir, exist_ok=True)

                    expected_email_files = []
                    for _, patient in filtered_patients.iterrows():
                        firstname = patient["First Name"]
                        lastname = patient["Last Name"]
                        filename = f"{firstname}_{lastname}_email.txt"
                        if os.path.exists(os.path.join(data_dir, filename)):
                            expected_email_files.append(filename)

                    email_files = expected_email_files

                    if email_files:
                        log(
                            "✅ <b>Outreach emails generated successfully:</b> {} emails created".format(
                                len(email_files)
                            )
                        )
                        st.success(f"{len(email_files)} outreach emails have been generated!")

                        st.markdown("### Download Generated Emails")

                        if "email_contents" not in st.session_state:
                            st.session_state.email_contents = {}
                            for email_file in email_files:
                                with open(os.path.join(data_dir, email_file), "r") as f:
                                    st.session_state.email_contents[email_file] = f.read()

                        if "zip_buffer" not in st.session_state:
                            import zipfile

                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                                for email_file, content in st.session_state.email_contents.items():
                                    zip_file.writestr(email_file, content)
                            st.session_state.zip_buffer = zip_buffer.getvalue()

                        import base64

                        b64_zip = base64.b64encode(st.session_state.zip_buffer).decode()

                        zip_html = f"""
                        <div style="margin-bottom: 20px;">
                            <a href="data:application/zip;base64,{b64_zip}"
                               download="patient_emails.zip"
                               style="text-decoration: none; display: inline-block; padding: 12px 18px;
                               border: 1px solid #ddd; border-radius: 4px; background-color: #4CAF50;
                               color: white; font-size: 16px; font-weight: bold; text-align: center;">
                                📦 Download All Emails as ZIP
                            </a>
                        </div>
                        """

                        components.html(zip_html, height=70)

                        st.markdown("---")
                        st.markdown("#### Individual Email Downloads")

                        individual_html = """
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                        """

                        for i, email_file in enumerate(email_files):
                            file_content = st.session_state.email_contents.get(email_file, "")
                            b64_content = base64.b64encode(file_content.encode()).decode()

                            name_parts = email_file.split("_")[:2]
                            display_name = " ".join(name_parts)

                            individual_html += f"""
                            <a href="data:text/plain;base64,{b64_content}"
                               download="{email_file}"
                               style="text-decoration: none; display: inline-block; margin: 4px; padding: 8px 12px;
                               border: 1px solid #ddd; border-radius: 4px; background-color: #f0f2f6;
                               color: #262730; font-size: 14px; text-align: center; min-width: 120px;">
                                {display_name}
                            </a>
                            """

                        individual_html += """
                        </div>
                        """

                        components.html(individual_html, height=100 + (len(email_files) // 4) * 60)

                    else:
                        log(" <b>Email generation process completed but no email files were found.</b>")
                        st.warning(
                            "The email generation process completed but no email files were found in the data directory. This might indicate an issue with the email generation or file saving process."
                        )

            except APIStatusError as e:
                status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", "?")
                msg = getattr(e, "message", None) or str(e)
                err_body = ""
                if hasattr(e, "response") and e.response is not None:
                    err_body = getattr(e.response, "text", None) or getattr(e.response, "body", "") or ""
                log(f"❌ <b>LLM API error (HTTP {status}):</b> {msg}")
                if err_body:
                    log(f"<b>Response:</b> {str(err_body)[:500]}")
                st.error(f"LLM API error: HTTP {status}. Check base URL and model name. Details: {msg}")
            except APIConnectionError as e:
                log(f"❌ <b>Cannot reach LLM:</b> {e!s}")
                st.error("Cannot reach LLM at base URL. Check that the service is running and reachable.")

    std_output = stdout_buffer.getvalue()
    std_error = stderr_buffer.getvalue()

    if std_output:
        log_messages.append("<b>Terminal Output:</b>")
        for line in std_output.splitlines():
            if line.strip():
                log_messages.append(line)
        log_placeholder.markdown(
            f"""
            <div style="height: 400px; overflow-y: auto; border: 1px solid #cccccc;
                 padding: 15px; border-radius: 5px; background-color: rgba(240, 242, 246, 0.4);
                 color: inherit; font-family: monospace;">
                {"<br>".join(log_messages)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    if std_error:
        log_messages.append("<b style='color:#ff6b6b;'>Terminal Error:</b>")
        for line in std_error.splitlines():
            if line.strip():
                log_messages.append(f"<span style='color:#ff6b6b;'>{line}</span>")
        log_placeholder.markdown(
            f"""
            <div style="height: 400px; overflow-y: auto; border: 1px solid #cccccc;
                 padding: 15px; border-radius: 5px; background-color: rgba(240, 242, 246, 0.4);
                 color: inherit; font-family: monospace;">
                {"<br>".join(log_messages)}
            </div>
            """,
            unsafe_allow_html=True,
        )
