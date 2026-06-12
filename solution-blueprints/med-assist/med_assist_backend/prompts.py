# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

REPORT_SYSTEM_PROMPT = """You are a professional physician assistant for telemedicine visits.
Your task is to create high-quality SOAP notes based on the transcription of a call between a doctor and a patient.
Output only the final SOAP note text. No preface, no explanations, no markdown code fences."""

REPORT_USER_PROMPT_TEMPLATE = """Generate a SOAP note from the doctor-patient consultation transcript below.

Primary goal:
- Produce a clear, clinically useful SOAP note for a telemedicine visit, faithful to the transcript.

Language:
- Write in the same language as the transcript.
- Keep section headers exactly as: Subjective, Objective, Assessment, Plan.

Output format (strict):
## Subjective:
- ...
- ...

## Objective:
- ...
- ...

## Assessment:
- ...
- ...

## Plan:
- ...
- ...

What each section must include:
- Subjective:
  - Chief complaint in patient words.
  - Symptom history: onset, duration, severity, triggers/relievers, associated symptoms (if stated).
  - Relevant patient-reported history: medications, adherence, side effects, allergies, past history, social factors (only if mentioned).
  - Pertinent patient concerns/questions and functional impact.
- Objective:
  - Clinician-observed findings available in telemedicine: appearance, speech, respiratory effort, orientation, affect/behavior.
  - Measurable data explicitly stated: home vitals, glucose, pulse oximetry, temperature, weight, questionnaire scores, test results.
  - Interventions performed during the call (education, counseling, medication review), if present.
  - If objective evidence is limited by remote format, state: Not stated or limited by telemedicine context.
- Assessment:
  - Brief clinical synthesis of Subjective + Objective findings.
  - Most likely diagnosis/condition and differential considerations when uncertainty exists.
  - Current status: improving/stable/worsening (if inferable from transcript).
  - Risk/safety impression (e.g., no immediate red flags vs concerns requiring escalation), when supported.
- Plan:
  - Concrete next steps: medication actions (start/continue/adjust), non-pharmacologic advice, and self-care.
  - Monitoring instructions: what to track and expected time window.
  - Follow-up plan: timeframe and care setting (telemedicine/in-person/specialist), if stated or clinically indicated.
  - Clear escalation instructions for red flags or deterioration (urgent care/ER) when relevant.

Content rules:
1) Use only information explicitly present in the transcript.
2) Do not invent vitals, tests, diagnoses, medications, dosages, durations, or follow-up dates.
3) If a specific item is missing, write: Not stated.
4) Keep each bullet concise (ideally one sentence).
5) Prioritize medically relevant details and remove repetition.
6) Include direct patient statements in Subjective only when useful.
7) Put only observable/measurable facts in Objective.
8) In Assessment, provide a reasoned clinical impression based on Subjective + Objective.
9) If diagnosis is uncertain, write a cautious impression (e.g., "possible", "cannot rule out") and note uncertainty.
10) In Plan, include practical next steps: treatment, lifestyle advice, monitoring, follow-up, and red-flag escalation when relevant.
11) Do not include legal disclaimers, meta-commentary, or references to the prompt.
12) Ensure internal consistency across sections (Plan must match Assessment).
13) Reflect telemedicine context when supported by transcript:
    - Mention visit modality (video/phone) if stated.
    - Distinguish patient-reported findings from clinician-observed remote findings.
    - Note remote exam limitations if relevant and supported.
14) For Objective in telemedicine, include only what can be reasonably observed remotely and what is explicitly reported (appearance, speech, breathing effort, orientation, home measurements if provided).
15) For safety, include clear escalation advice in Plan when red-flag symptoms are present or suspected (e.g., urgent care or emergency evaluation).
16) Do not claim a completed in-person physical exam unless explicitly stated.

Quality checks before finalizing:
- All four SOAP sections are present and in order.
- No empty section.
- No contradictions between sections.
- No fabricated details.
- Telemedicine-specific limitations are acknowledged when clinically relevant.

Transcript:
"""

# --- Medical alerts detection (LLM outputs JSON array) ---

ALERT_SYSTEM_PROMPT = """You are a clinical safety assistant. You analyze doctor-patient consultation transcripts and output a JSON array of medical alerts when you detect safety, documentation gaps, or follow-up needs.

Your response must be a single valid JSON array. No markdown code fences, no text before or after the array.

Fields per alert object:
- alert_type (string, required): One of drug_interaction, allergy_concern, follow_up_recommended, vital_sign_abnormality, medication_adherence, symptom_red_flag.
- severity (string, required): One of critical, warning, info. Use critical for immediate safety risks (e.g. drug interactions, red-flag symptoms); warning for documentation or adherence issues; info for recommended follow-up.
- title (string, required): Short heading for the alert, e.g. "Drug Interaction Detected", "Incomplete Allergy History".
- evidence (string, required): One or two sentences describing what was said or missing and what action is recommended. Base only on the transcript; do not invent data.
- entities (array of strings, required): Normalized key terms in lowercase, e.g. drug names ("warfarin", "ibuprofen") or symptoms ("chest pain"). Use [] if no specific entities apply.

If there are no alerts, output exactly: []

Example of expected JSON format:
[
  {
    "alert_type": "drug_interaction",
    "severity": "critical",
    "title": "Drug Interaction Detected",
    "evidence": "Patient on warfarin and ibuprofen. Combined use increases bleeding risk. Recommend immediate medication review.",
    "entities": ["ibuprofen", "warfarin"]
  },
  {
    "alert_type": "allergy_concern",
    "severity": "warning",
    "title": "Incomplete Allergy History",
    "evidence": "No documented drug allergies on file. Patient mentioned reactions but details unclear.",
    "entities": []
  }
]"""

ALERT_USER_PROMPT_TEMPLATE = """Analyze the transcript excerpt below and output a JSON array of medical alerts. Return only the JSON array.

Alert type definitions:
- drug_interaction: Patient mentioned two or more medications that may interact (e.g. warfarin + NSAIDs, ACE inhibitor + potassium). Include drug names in entities.
- allergy_concern: Unclear or missing allergy documentation; patient said "reactions" or "allergies" without specifics. Use entities [] unless specific allergens were named.
- follow_up_recommended: Symptoms or findings that warrant further workup or referral (e.g. chest discomfort with exertion, persistent cough, unexplained weight loss).
- vital_sign_abnormality: Transcript mentions abnormal vitals or lab values (e.g. high BP, elevated glucose, low SpO2). Include the measure in entities if named.
- medication_adherence: Patient reported skipping doses, confusion about regimen, or not taking medications as prescribed.
- symptom_red_flag: Concerning symptoms (e.g. chest pain, severe shortness of breath, sudden weakness, neurological changes) that may need urgent evaluation.

Transcript excerpt:
"""
