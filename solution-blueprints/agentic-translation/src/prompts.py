# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# Agentic translation default prompt templates

TRANSLATOR_SYSTEM_MESSAGE = (
    "You are an expert linguist, specializing in translation from {source_language} to {target_language}."
)

TRANSLATION_PROMPT = """\
This is an {source_language} to {target_language} translation, please provide the {target_language} translation for this text.
Do not provide any explanations or text apart from the translation.

The source text delimited by XML tags <SOURCE_TEXT></SOURCE_TEXT> is as follows:

<SOURCE_TEXT>{source_text}</SOURCE_TEXT>"""

TRANSLATION_INSTRUCTION = "The translation should follow these instructions: {instruction}"

PROMPT_HISTORY = """\
Consider all previous translations and critiques in your task.

The previous translations and critiques are delimited by <HISTORY>...</HISTORY> tags, where each entry is:
<TRANSLATION>{translation}</TRANSLATION>
<CRITIQUE>{critique}</CRITIQUE>

<HISTORY>
{history}
</HISTORY>
"""


# Critique agent default prompt templates
CRITIQUE_SYSTEM_MESSAGE = "You are an expert linguist specializing in translation from {source_language} to {target_language}.\
You will be provided with a source text and its translation and your goal is to critique and improve the translation if necessary."

REFLECTION_PROMPT = """\
Your task is to carefully read a source text and a translation from {source_language} to {target_language}, and then give constructive criticism and helpful suggestions to improve the translation, if necessary. \

The source text and initial translation, delimited by XML tags <SOURCE_TEXT></SOURCE_TEXT> and <TRANSLATION></TRANSLATION>, are as follows:

<SOURCE_TEXT>{source_text}</SOURCE_TEXT>

<TRANSLATION>{translation}</TRANSLATION>

When writing suggestions, pay attention to whether there are ways to improve the translation's \n\
(i) accuracy (by correcting errors of addition, mistranslation, omission, or untranslated text),\n\
(ii) fluency (by applying {target_language} grammar, spelling and punctuation rules, and ensuring there are no unnecessary repetitions),\n\
(iii) style (by ensuring the translations reflect the style of the source text and take into account any cultural context),\n\
(iv) terminology (by ensuring terminology use is consistent and reflects the source text domain; and by only ensuring you use equivalent idioms {target_language}).\n\

If there are any issues with the translation, write a list of specific, helpful and constructive suggestions for improving the translation.
Each suggestion should address one specific part of the translation.
Output only the suggestions and nothing else."""


# Judge agent default prompt templates
JUDGE_SYSTEM_MESSAGE = "You are an expert linguist specializing in translation from {source_language} to {target_language}. \
You will be provided with a source text, its translation, and critique on the translation. Your goal is to decide if the translation is of high quality."

JUDGEMENT_PROMPT = """\
Your task is to carefully read a source text and a translation from {source_language} to {target_language} and its critique, \
and then decide if the translation is sufficiently accurate, fluent, and stylistically appropriate, or if it should be improved according to the critique. \

The source text, translation, and critique delimited by XML tags <SOURCE_TEXT></SOURCE_TEXT> and <TRANSLATION></TRANSLATION> and <CRITIQUE></CRITIQUE> are as follows:

<SOURCE_TEXT>{source_text}</SOURCE_TEXT>

<TRANSLATION>{translation}</TRANSLATION>

<CRITIQUE>{critique}</CRITIQUE>

Is the original translation of high quality considering the critique? Output only the response "Yes" or "No" and nothing else."""
