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

import argparse
import asyncio
import functools  # For wrapping synchronous functions in async
import json
import os
from typing import Any, Callable, Dict, List

import aiofiles  # type: ignore[import-untyped]  # For asynchronous file writing
import pandas as pd
from autogen import (
    AssistantAgent,
    GroupChat,
    GroupChatManager,
    UserProxyAgent,
)
from autogen.llm_config.utils import config_list_from_json
from openai import OpenAI
from prompts_healthcare.doctor_critic_prompt import DOCTOR_CRITIC_PROMPT
from prompts_healthcare.epidemiologist_prompt import EPIDEMIOLOGIST_PROMPT
from prompts_healthcare.outreach_email_prompt import OUTREACH_EMAIL_PROMPT_TEMPLATE
from prompts_healthcare.user_proxy_prompt import USER_PROXY_PROMPT

# Export the prompt variables for use in the app
__all__ = [
    "get_configs",
    "discover_model",
    "target_patients_outreach",
    "find_patients",
    "write_outreach_emails",
    "USER_PROXY_PROMPT",
    "EPIDEMIOLOGIST_PROMPT",
    "DOCTOR_CRITIC_PROMPT",
    "OUTREACH_EMAIL_PROMPT_TEMPLATE",
]


def discover_model(base_url: str, api_key: str = "") -> str:
    """Query the LLM backend's /v1/models and return the first available model id."""
    import requests

    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = url.rstrip("/") + "/v1"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = requests.get(f"{url}/models", headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        raise ValueError(f"No models found at {url}/models")
    return data[0]["id"]


def get_configs(env_or_file: str, filter_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Load configuration from a JSON file.

    Args:
        env_or_file (str): Path to the JSON file or environment variable name.
        filter_dict (Dict[str, Any]): Dictionary to filter the configuration file.

    Returns:
        List[Dict[str, Any]]: Filtered configuration list (list of model config dicts).
    """
    return config_list_from_json(env_or_file=env_or_file, filter_dict=filter_dict)


async def target_patients_outreach(
    target_screening: str,
    config_list_llama: List[Dict[str, Any]],
    log_fn=None,
    user_proxy_prompt=USER_PROXY_PROMPT,
    epidemiologist_prompt=EPIDEMIOLOGIST_PROMPT,
    doctor_critic_prompt=DOCTOR_CRITIC_PROMPT,
) -> str:
    """
    Determines the criteria for patient outreach based on a screening task.

    This function facilitates a conversation between a user, an epidemiologist,
    and a doctor critic to define the criteria for patient outreach. The output
    criteria from the doctor and epidemiologist include minimum age, maximum age,
    gender, and a possible previous condition.

    Example:

        criteria = asyncio.run(target_patients_outreach("Type 2 diabetes screening"))

    Args:
        target_screening (str): The type of screening task (e.g., "Type 2 diabetes screening").
        config_list_llama (List[Dict[str, Any]]): Configuration for the Llama model.
        log_fn (callable, optional): Function for logging messages.
        user_proxy_prompt (str, optional): Custom prompt for the user proxy agent.
        epidemiologist_prompt (str, optional): Custom prompt for the epidemiologist agent.
        doctor_critic_prompt (str, optional): Custom prompt for the doctor critic agent.

    Returns:
        str: The defined criteria for patient outreach.
    """
    llm_config_llama: Dict[str, Any] = {
        "cache_seed": 41,
        "temperature": 0,
        "config_list": config_list_llama,
        "timeout": 120,
    }

    user_proxy = UserProxyAgent(
        name="User",
        is_termination_msg=lambda x: (x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE")),
        human_input_mode="NEVER",
        description=user_proxy_prompt,  # Use custom prompt
        code_execution_config=False,
        max_consecutive_auto_reply=1,
    )

    epidemiologist = AssistantAgent(
        name="Epidemiologist",
        system_message=epidemiologist_prompt,  # Use custom prompt
        llm_config=llm_config_llama,
        code_execution_config=False,
        is_termination_msg=lambda x: (x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE")),
    )

    critic = AssistantAgent(
        name="DoctorCritic",
        system_message=doctor_critic_prompt,  # Use custom prompt
        llm_config=llm_config_llama,
        human_input_mode="NEVER",
        code_execution_config=False,
        is_termination_msg=lambda x: (x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE")),
    )

    groupchat = GroupChat(agents=[user_proxy, epidemiologist, critic], messages=[])
    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config_llama)

    user_proxy.initiate_chat(
        manager,
        message=target_screening,
    )
    if log_fn:
        log_fn("Agent conversation complete.")
    user_proxy.stop_reply_at_receive(manager)
    result = user_proxy.last_message()["content"]
    if log_fn:
        log_fn(f"Criteria result: {result}")
    return result


def get_patients_from_criteria(
    patients_file: str, min_age: int, max_age: int, criteria: str, gender: str
) -> pd.DataFrame:
    """
    Filters patient data from a CSV file based on specified criteria.

    This function reads patient data from a CSV file and filters it based on
    age range, gender, and a specific condition.

    Example:

        filtered_patients = get_patients_from_criteria(
            patients_file="data/patients.csv",
            min_age=40,
            max_age=70,
            criteria="Adenomatous Polyps",
            gender="None"
        )

    Args:
        patients_file (str): Path to the CSV file containing patient data.
        min_age (int): Minimum age for filtering.
        max_age (int): Maximum age for filtering.
        criteria (str): Condition to filter patients by.
        gender (str, optional): Gender to filter patients by. Defaults to None.

    Returns:
        pd.DataFrame: A DataFrame containing the filtered patient data.
    """
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

    # Support both file path (str) and file-like object (e.g., from Streamlit)
    if hasattr(patients_file, "read"):
        # Reset pointer in case it's been read before
        patients_file.seek(0)  # type: ignore[attr-defined]
        patients_df = pd.read_csv(patients_file)
    else:
        patients_df = pd.read_csv(patients_file)

    for column in required_columns:
        if column not in patients_df.columns:
            raise ValueError(f"Missing required column: {column}")

    # Ensure all text is lowercase for case-insensitive matching
    patients_df["condition"] = patients_df["condition"].str.lower()
    criteria = criteria.lower()

    # Filter by condition matching
    condition_filter = patients_df["condition"].str.contains(criteria, na=False)

    # Filter by age range
    age_filter = (patients_df["age"] >= min_age) & (patients_df["age"] <= max_age)

    # Combine filters with OR logic
    combined_filter = age_filter | condition_filter

    if gender in ["M", "F"]:
        gender_filter = patients_df["gender"].str.upper() == gender.upper()
        combined_filter = combined_filter & gender_filter

    return patients_df[combined_filter]


def register_function(
    assistant: AssistantAgent, user_proxy: UserProxyAgent, func: Callable, name: str, description: str
) -> None:
    """
    This function allows an assistant agent and a user proxy agent to execute
    a specified function.

    Example:
        register_function(
            assistant=assistant_agent,
            user_proxy=user_proxy_agent,
            func=my_function,
            name="my_function",
            description="This is a test function."
        )

    Args:
        assistant (AssistantAgent): The assistant agent to register the function.
        user_proxy (UserProxyAgent): The user proxy agent to register the function.
        func (Callable): The function to register.
        name (str): The name of the function.
        description (str): A description of the function.
    """

    assistant.register_for_llm(name=name, description=description)(func)

    user_proxy.register_for_execution(name=name)(func)

    return None


async def find_patients(
    criteria: str,
    config_list_llama: List[Dict[str, Any]],
    log_fn=None,
    patients_file_path=None,  # Can be a path or a file-like object
) -> pd.DataFrame:
    """
    Finds patients matching specific criteria using agents.

    This function uses a user proxy agent and a data analyst agent to filter
    patient data based on the provided criteria.

    Example:
        patients_df = asyncio.run(find_patients(criteria="Patients aged 40 to 70"))

    Args:
        criteria (str): The criteria for filtering patients.
        config_list_llama (List[Dict[str, Any]]): Configuration for the Llama model.
        log_fn (callable, optional): Function for logging messages.
        patients_file_path: Path to patient data file or file-like object.

    Returns:
        pd.DataFrame: A DataFrame containing the filtered patient data.
    """
    # Set up a temporary file path for the agent to use
    temp_file_path = None

    # If we have a file-like object (from Streamlit), save it to a temp file
    if patients_file_path is not None and hasattr(patients_file_path, "read"):
        try:
            # Create data directory if it doesn't exist
            os.makedirs("data", exist_ok=True)
            temp_file_path = os.path.join("data", "temp_patients.csv")

            # Reset the file pointer and read with pandas
            patients_file_path.seek(0)
            temp_df = pd.read_csv(patients_file_path)

            # Save to the temp location
            temp_df.to_csv(temp_file_path, index=False)

            if log_fn:
                log_fn(f"Saved uploaded file to temporary location: {temp_file_path}")

            # Update the criteria to include the file path
            criteria = f"The patient data is available at {temp_file_path}. " + criteria
        except Exception as e:
            if log_fn:
                log_fn(f"Error preparing patient file: {str(e)}")
            raise
    elif isinstance(patients_file_path, str):
        # It's a regular file path
        temp_file_path = patients_file_path
        criteria = f"The patient data is available at {temp_file_path}. " + criteria

    # Use a single LLM call (no tools) to get filter params, then call get_patients_from_criteria
    # so we avoid tool_choice which requires --enable-auto-tool-choice on the server.
    config = config_list_llama[0]
    base_url = config.get("base_url", "").rstrip("/")
    api_key = config.get("api_key") or os.environ.get("OPENAI_API_KEY") or ""
    model = config.get("model", "meta-llama/Llama-3.3-70B-Instruct")

    prompt = f"""The patient data file is at: {temp_file_path or 'data/patients.csv'}

The user has provided the following screening criteria. Extract the filter parameters and respond with ONLY a valid JSON object (no markdown, no explanation) with exactly these keys:
- "min_age" (integer)
- "max_age" (integer)
- "gender" (string: "None", "M", or "F")
- "criteria" (string: the condition/keyword to filter by, e.g. "adenomatous polyps" or "diabetes")

User criteria:
{criteria}

JSON:"""

    def _call_llm():
        client = OpenAI(api_key=api_key or "dummy", base_url=base_url)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0,
        )
        return (r.choices[0].message.content or "").strip()

    reply = await asyncio.get_event_loop().run_in_executor(None, _call_llm)
    if log_fn:
        log_fn("LLM response for filter parameters received.")

    # Parse JSON from reply — find the first { and last } to handle any surrounding text
    raw = reply.strip()
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        raw = raw[brace_start : brace_end + 1]
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError:
        # Try to repair truncated JSON (e.g. missing closing quote/brace)
        repaired = raw
        if not repaired.endswith("}"):
            open_quotes = repaired.count('"') % 2 == 1
            if open_quotes:
                repaired += '"'
            repaired += "}"
        try:
            arguments = json.loads(repaired)
        except json.JSONDecodeError:
            if log_fn:
                log_fn(f"Could not parse JSON from LLM reply: {reply[:400]}")
            raise ValueError(f"LLM did not return valid JSON for filter parameters. Raw reply: {reply[:400]}")

    for key in ("min_age", "max_age", "gender", "criteria"):
        if key not in arguments:
            raise ValueError(f"LLM JSON missing required key: {key}")
    arguments["patients_file"] = temp_file_path or arguments.get("patients_file", "data/patients.csv")
    arguments["min_age"] = int(arguments["min_age"])
    arguments["max_age"] = int(arguments["max_age"])

    filtered_df = get_patients_from_criteria(
        patients_file=arguments["patients_file"],
        min_age=arguments["min_age"],
        max_age=arguments["max_age"],
        criteria=arguments["criteria"],
        gender=str(arguments["gender"]),
    )
    if log_fn:
        log_fn(f"Filtered {len(filtered_df)} patients.")
    return filtered_df, arguments


async def generate_email(openai_client, patient, email_prompt, model):
    """
    Asynchronously generate an email using the OpenAI client.

    Args:
        openai_client (OpenAI): The OpenAI client instance.
        patient (dict): The patient data.
        email_prompt (str): The email prompt to send to the model.
        model (str): The model to use for generation.

    Returns:
        str: The generated email content.
    """
    # Wrap the synchronous `create` method in an async function
    create_completion = functools.partial(
        openai_client.chat.completions.create,
        model=model,  # Use model from the OpenAI client
        messages=[{"role": "user", "content": email_prompt}],
        stream=False,
        seed=42,
        temperature=0,  # Ensures a consistent output for email (limiting creativity)
    )
    chat_completion = await asyncio.get_event_loop().run_in_executor(None, create_completion)
    return chat_completion.choices[0].message.content


async def write_email_to_file(file_path, patient, email_content):
    """
    Asynchronously write an email to a file.

    Args:
        file_path (str): The path to the file.
        patient (dict): The patient data.
        email_content (str): The email content to write.

    Returns:
        None
    """
    async with aiofiles.open(file_path, "w") as f:
        await f.write(f"Name: {patient['First Name']} {patient['Last Name']}\n")
        await f.write(f"Patient ID: {patient['patient_id']}\n")
        await f.write(f"Email: {patient['Email']}\n")
        await f.write(email_content)
        await f.write("\n")
        await f.write("-----------------------------------------")


async def write_outreach_emails(
    patient_details: pd.DataFrame,
    user_proposal: str,
    arguments_criteria: Dict[str, Any],
    openai_client: OpenAI,
    model: str,
    phone: str = "123-456-7890",
    email: str = "doctor@doctor.com",
    name: str = "AMD Preventative Healthcare",
    log_fn=None,
    outreach_email_prompt_template=OUTREACH_EMAIL_PROMPT_TEMPLATE,
) -> None:
    """
    Asynchronously generates and writes outreach emails for patients.

    This function generates personalized emails for patients based on their
    details and the specified screening criteria. The emails are written to
    individual text files asynchronously.

    Args:
        patient_details (pd.DataFrame): DataFrame containing patient details.
        user_proposal (str): The type of screening task (e.g., "Colonoscopy screening").
        arguments_criteria (Dict[str, Any]): The criteria used for filtering patients.
        openai_client (OpenAI): The OpenAI client instance.
        model (str): Model name to use for generation.
        phone (str): Phone number to include in the outreach emails.
        email (str): Email address to include in the outreach emails.
        name (str): Name to include in the outreach emails.
        log_fn (callable, optional): Function for logging messages.
        outreach_email_prompt_template (str): Custom template for outreach emails.

    Returns:
        None
    """
    os.makedirs("data", exist_ok=True)
    if patient_details.empty:
        msg = "No patients found"
        print(msg)
        if log_fn:
            log_fn(msg)
        return

    async def process_patient(patient):
        # Ensure all required fields are present in the patient record
        required_fields = ["First Name", "Last Name", "patient_id", "Email"]
        for field in required_fields:
            if field not in patient or pd.isna(patient[field]):
                msg = f"Skipping patient record due to missing field: {field}"
                print(msg)
                if log_fn:
                    log_fn(msg)
                return

        # Validate the prompt template
        try:
            # Use the custom template instead of the default
            email_prompt = outreach_email_prompt_template.format(
                patient=patient.to_dict(),
                arguments_criteria=arguments_criteria,
                first_name=patient["First Name"],
                last_name=patient["Last Name"],
                user_proposal=user_proposal,
                name=name,
                phone=phone,
                email=email,
            )
        except KeyError as e:
            msg = f"Error formatting email prompt: Missing key {e}. Skipping patient."
            print(msg)
            if log_fn:
                log_fn(msg)
            return

        msg = f'Generating email for {patient["First Name"]} {patient["Last Name"]}'
        print(msg)
        if log_fn:
            log_fn(msg)
        email_content = await generate_email(openai_client, patient, email_prompt, model)

        file_path = f"data/{patient['First Name']}_{patient['Last Name']}_email.txt"
        await write_email_to_file(file_path, patient, email_content)
        if log_fn:
            log_fn(f"Wrote email to {file_path}")

    tasks = [process_patient(patient) for _, patient in patient_details.iterrows()]
    await asyncio.gather(*tasks)

    msg = "All emails have been written to the 'data/' directory."
    print(msg)
    if log_fn:
        log_fn(msg)


def parse_arguments():
    """
    Parse command-line arguments for the script.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Run the Preventative Healthcare Intel script.")
    parser.add_argument("--oai_config", type=str, required=True, help="Path to the OAI_CONFIG_LIST.json file.")
    parser.add_argument(
        "--target_screening",
        type=str,
        required=True,
        help="The type of screening task (e.g., 'Colonoscopy screening').",
    )
    parser.add_argument(
        "--patients_file",
        type=str,
        default="data/patients.csv",
        help="Path to the CSV file containing patient data. Default is 'data/patients.csv'.",
    )
    parser.add_argument(
        "--phone",
        type=str,
        default="123-456-7890",
        help="Phone number to include in the outreach emails. Default is '123-456-7890'.",
    )
    parser.add_argument(
        "--email",
        type=str,
        default="doctor@doctor.com",
        help="Email address to include in the outreach emails. Default is 'doctor@doctor.com'.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="AMD Blueprints team AI",
        help="Name to include in the outreach emails. Default is 'AMD Preventative Healthcare'.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command-line arguments
    args = parse_arguments()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    env_base_url = (os.environ.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
    if not env_base_url:
        raise SystemExit("OPENAI_BASE_URL is not set. Set it to your LLM endpoint (e.g. via Helm).")

    model_name = discover_model(env_base_url, api_key)
    config_list_llama = [{"model": model_name, "base_url": env_base_url, "api_key": api_key, "price": [0.0, 0.0]}]

    # Get the criteria for the target screening
    # The user provides the screening task.
    # The epidemiologist and doctor critic will then define the criteria for the outreach.
    filepath = os.path.join(os.getcwd(), args.patients_file)
    criteria = f"The patient data is located here: {filepath}."
    criteria += asyncio.run(target_patients_outreach(args.target_screening, config_list_llama, config_list_llama))

    # The user proxy agent and data analyst
    # will filter the patients based on the criteria defined by the epidemiologist and doctor critic.
    patients_df, arguments_criteria = asyncio.run(
        find_patients(criteria, config_list_llama, patients_file_path=filepath)
    )

    # Initialize OpenAI client
    openai_client = OpenAI(api_key=api_key, base_url=config_list_llama[0]["base_url"])

    # Use LLM to write the outreach emails to text files.
    asyncio.run(
        write_outreach_emails(
            patients_df,
            args.target_screening,
            arguments_criteria,
            openai_client,
            str(config_list_llama[0]["model"]),
            phone=args.phone,
            email=args.email,
            name=args.name,
        )
    )
