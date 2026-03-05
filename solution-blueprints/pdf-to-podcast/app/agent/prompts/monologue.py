# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

SUMMARY_PROMPT = """
You are a skilled analyst. Deliver a concise, goal-driven analysis of the document below, focusing on: {{ focus }}.
This must function across any domain (finance, literature, science, programming, etc.). Keep instructions domain-neutral and only infer a field when the text clearly signals it.

<document>
{{text}}
</document>

Analysis requirements:
1. Core Information:
  - Crucial metrics, evidence, or data points
  - Major trends or themes
  - Salient patterns or arguments
  - Forward-looking implications
  - Central/strategic takeaways

2. Context of the Document:
  - Type and intent of the document
  - Key entities, topics, or characters
  - Timeframe or scope
  - Primary stakeholders or audience

3. Domain Sensitivity:
  - Match tone/terms to the field
  - If technical/code: outline purpose, logic, and notable trade-offs
  - If narrative: capture plot, themes, and voice
  - If scientific: call out method, results, and limitations
  - Do not inject domain assumptions not supported by the text

4. Fidelity:
  - Keep numbers exact
  - Preserve dates
  - Maintain precise terminology
  - Quote key disclosures verbatim when relevant

5. Speech-Friendly Text Rules:
  - Numbers in words (e.g., "one billion" not "1B")
  - Currency as "[amount] [unit]" (e.g., "fifty million dollars")
  - Percentages in spoken form (e.g., "twenty five percent")
  - Math operations spelled out (e.g., "increased by" not "+")
  - Use proper Unicode characters

Write in markdown with clear headings and bullets. Be concise and pointed. Compress into audio-ready points without overloading numbers; stress the most important ideas, growth areas, or implications for the domain. Speak in first person with an engaging, accessible tone for an informed audience.
"""

# Template for synthesizing multiple document summaries into an outline
MULTI_DOC_SYNTHESIS_PROMPT = """
Produce a structured outline for a monologue that merges the following document summaries. Target runtime: 30-45 seconds. The instructions must work across domains (finance, literature, science, programming, etc.). Keep guidance domain-neutral; infer a field only when the content warrants it.

Focus Areas & Key Topics:
{% if focus_instructions %}
{{focus_instructions}}
{% else %}
Use your judgment to surface and rank the most important themes, evidence, metrics, or arguments across all documents.
{% endif %}

Available Source Documents:
{{documents}}

Requirements:
1. Content Strategy
   - Lead with Target Documents; use Context Documents for support or contrast
   - Elevate key metrics/evidence (or plot points/arguments/themes in non-quant domains)
   - Call out trends, implications, and ties to the focus areas
   - Keep terminology and nuance appropriate to the domain

2. Structure
   - Build a clean narrative flow with coherent transitions
   - Balance depth and breadth by importance
   - Keep the outline compact enough for 30-45 seconds

3. Domain Awareness
   - If technical/code: note intent, main components, and trade-offs
   - If narrative: note plot movement, themes, and tone/voice
   - If scientific: note methodology, key results, and limitations
   - Avoid domain assumptions unless the documents explicitly justify them

4. Text Formatting (for speech-friendly delivery):
   - Convert numeric values to their verbal equivalents
   - Present monetary amounts as spoken text with amount followed by currency unit
   - Transform percentage symbols into verbal expressions
   - Spell out mathematical symbols and operators in words

Output a concise, bullet-style outline that synthesizes insights across all documents, giving emphasis to Target Documents and using Context Documents as support."""

# Template for generating the actual monologue transcript
TRANSCRIPT_PROMPT = """
Craft a focused update using this outline and the source documents. The instructions must apply to any domain (finance, literature, science, programming, etc.). Keep the rules domain-neutral and only lean on a field if the content clearly indicates it.

Outline:
{{ raw_outline }}

Available Source Documents:
{% for doc in documents %}
<document>
<type>{% if doc.type == "target" %}Target Document{% else %}Context Document{% endif %}</type>
<path>{{doc.filename}}</path>
<summary>
{{doc.summary}}
</summary>
</document>
{% endfor %}

Focus Areas: {{ focus }}

Parameters:
- Duration: 30 seconds (~90 words)
- Speaker: {{ speaker_1_name }}
- Structure: Follow the outline while maintaining:
  * Opening (5-7 words)
  * Key points from outline (60-70 words)
  * Supporting evidence (15-20 words)
  * Conclusion (10-15 words)

Requirements:
1. Speech Pattern
   - Use broadcast-style delivery
   - Natural pauses and emphasis
   - Professional but conversational tone
   - Clear source attribution
   - Match tone/terms to the document’s field without adding unsupported domain assumptions

2. Content Structure
   - Give primary emphasis to findings from Target Documents
   - Supplement with Context Documents when appropriate
   - Ensure coherent progression between ideas
   - Conclude with a definitive summary point
   - If technical/code: summarize intent, key components, and trade-offs
   - If narrative: convey plot movement, themes, and voice
   - If scientific: capture methodology, key results, and limitations

3. Text Formatting:
   - Express all numeric values verbally
   - Format monetary amounts as spoken text with amount followed by currency unit
   - Render percentages as verbal descriptions
   - Write out all mathematical symbols and operators in words

Create a concise, engaging monologue that follows the outline while delivering essential information for the given domain, without inventing unstated context."""

# Template for converting monologue to structured dialogue format
DIALOGUE_PROMPT = """You need to convert a monologue into a structured JSON format. The instructions must suit any domain (finance, literature, science, programming, etc.). Keep rules domain-neutral; only infer a field if the content makes it explicit. You have:

1. Speaker information:
   - Speaker: {{ speaker_1_name }} (mapped to "speaker-1")

2. The original monologue:
{{ text }}

3. Required output schema:
{{ schema }}

Your task is to:
- Convert the monologue exactly into the specified JSON format
- Preserve all content without any omissions
- Map all content to "speaker-1"
- Maintain data accuracy across domains (financial, technical, narrative, scientific, etc.)

You absolutely must, without exception:
- Employ Unicode characters in their native form (e.g., use ' rather than \\u2019)
- Format all apostrophes, quotation marks, and special characters correctly
- Avoid escaping Unicode characters in the final output
- Convert all numbers and symbols to spoken form:
  * Numbers should be spelled out (e.g., "one billion" instead of "1B")
  * Currency should be expressed as "[amount] [unit of currency]" (e.g., "fifty million dollars" instead of "$50M")
  * Mathematical symbols should be spoken (e.g., "increased by" instead of "+")
  * Percentages should be spoken as "percent" (e.g., "twenty five percent" instead of "25%")

Please output the JSON using the provided schema, keeping all details and formatting correct for the given domain. Use proper Unicode characters directly (no escapes). Output only the JSON."""

# Dictionary mapping template names to prompt content
MONOLOGUE_PROMPTS: dict[str, str] = {
    "summary_prompt": SUMMARY_PROMPT,
    "multi_doc_synthesis_prompt": MULTI_DOC_SYNTHESIS_PROMPT,
    "transcript_prompt": TRANSCRIPT_PROMPT,
    "dialogue_prompt": DIALOGUE_PROMPT,
}
