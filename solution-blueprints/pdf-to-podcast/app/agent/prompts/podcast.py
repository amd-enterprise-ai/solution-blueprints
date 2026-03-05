# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

SUMMARY_PROMPT = """
You are a careful reviewer. Produce a concise, comprehensive summary of the document below. Assume OCR/PDF artifacts may exist—interpret tables and numbers with context rather than copying noise.

<document>
{{text}}
</document>

Summarize with:
1) Key metadata:
   - Title/type
   - Organization/author
   - Provider/source
   - Covered date/time period
   - Relevant identifiers

2) Core substance:
   - Main findings and takeaways
   - Pivotal statistics or metrics
   - Recommendations or actions
   - Major shifts or trends
   - Risks or concerns
   - Material financial/quantitative details

3) Accuracy guardrails:
   - Keep numerical values exact
   - Preserve dates and timeframes
   - Maintain precise names and titles
   - Quote critical statements verbatim when appropriate

Use markdown with clear headers and lists. Prioritize essential information, keep the source tone/context, and avoid omitting critical details.
"""

# Template for synthesizing multiple document summaries into an outline
MULTI_PDF_OUTLINE_PROMPT = """
Build a podcast outline that weaves together the document summaries below. Total runtime: {{total_duration}} minutes. This should work for any domain—only assume a field when the content makes it explicit.

Focus Areas & Key Topics:
{% if focus_instructions %}
{{focus_instructions}}
{% else %}
Use your judgment to surface and rank the most important themes, findings, debates, and insights across all documents.
{% endif %}

Available Source Documents:
{{documents}}

Requirements:
1. Content strategy
  - Lead with Target Documents; use Context Documents for support or contrast
  - Highlight key themes, debates, and evidence (metrics where present)
  - Anticipate audience questions/concerns
  - Tie topics back to the stated focus areas

2. Structure
  - Establish a clear topic/section hierarchy
  - Allocate minutes per section based on priority
  - Cite sources via file paths
  - Keep transitions smooth for a coherent flow

3. Coverage
  - Be thorough on Target Documents
  - Integrate Context Documents to add depth
  - Support claims with evidence from across sources
  - Balance precision with engaging delivery

Deliver a cohesive outline that centers Target Documents and uses Context Documents to deepen the narrative.
"""

# Template for converting outline into structured JSON format
MULTI_PDF_STRUCTURED_OUTLINE_PROMPT = """
Translate the outline below into structured JSON. Mark the final segment as the conclusion.

<outline>
{{outline}}
</outline>

Output rules:
1) Every segment must contain:
   - section name
   - duration in minutes (length of the segment)
   - list of references (file paths)
   - list of topics; each topic has:
     - title
     - list of detailed points

2) Overall JSON must include:
   - podcast title
   - full list of segments

3) Notes:
   - References must come from: {{ valid_filenames }}
   - References only live in the segment "references" array (not as topics)
   - Duration is per-segment length, not a start timestamp
   - Each segment duration must be positive

The output must follow this JSON schema:
{{ schema }}
"""

# Template for generating transcript with source references
PROMPT_WITH_REFERENCES = """
Draft a transcript that incorporates details from the provided sources.

Source Text:
{{ text }}

Parameters:
- Duration: {{ duration }} minutes (~{{ (duration * 25) | int }} words)
- Topic: {{ topic }}
- Focus Areas: {{ angles }}

Requirements:
1) Content integration
  - Cite key quotes with speaker name and institution
  - Explain cited material in accessible language
  - Note where sources agree or disagree
  - Briefly assess the reasoning behind differing views

2) Presentation
  - Break down complex ideas for a general audience
  - Use apt analogies/examples
  - Address likely questions
  - Keep context visible throughout
  - Stay factually correct, especially with numbers
  - Cover all focus areas within the time budget
  - Maximize information density: convey maximum content with minimum words
  - Avoid redundant explanations or restating the same information in different words
  - Use concise, complete formulations that are direct and efficient
  - Eliminate unnecessary qualifiers, hedging phrases, or verbose elaborations

Deliver thorough coverage while keeping source accuracy and nuance intact. Prioritize brevity without sacrificing essential information.
"""

# Template for generating transcript without source references
NO_REFERENCES_PROMPT = """
Create a knowledge-driven transcript based on this outline.

Parameters:
- Duration: {{ duration }} minutes (~{{ (duration * 25) | int }} words)
- Topic: {{ topic }}
- Focus Areas: {{ angles }}

1) Knowledge scan
   - Map the landscape of known information
   - Identify core principles and frameworks
   - Note major debates and perspectives
   - List relevant examples and applications
   - Consider historical context and evolution

2) Content development
   - Draw from broad knowledge (no external quotes)
   - Present balanced viewpoints
   - Support claims with clear reasoning
   - Connect topics logically and progressively

3) Presentation
  - Make complex ideas accessible to a general audience
  - Use crisp analogies and examples
  - Anticipate and answer likely questions
  - Keep necessary context in view
  - Stay accurate, especially with numbers
  - Cover all focus areas within the time limit
  - Maximize information density: convey maximum content with minimum words
  - Avoid verbosity and unnecessary elaboration
  - Use concise, direct language while maintaining clarity
  - Eliminate redundant explanations and repetitive phrasing
  - Prioritize high information density without sacrificing completeness

Deliver a coherent exploration of the topic that is clear, accurate, and complete without external citations. Focus on brevity and efficiency in expression.
"""

# Template for converting transcript to dialogue format
TRANSCRIPT_TO_DIALOGUE_PROMPT = """
Convert the input transcript into an engaging, informative podcast dialogue.

Speakers:
- **Host**: {{ speaker_1_name }} (host)
- **Guest**: {{ speaker_2_name }} (subject-matter expert)

Guidelines:
Content
  - Present information clearly and accurately
  - Explain complex ideas in simple language
  - Discuss key points, insights, and perspectives from the transcript
  - Include the guest’s analysis/insight on the topic
  - Keep relevant quotes, anecdotes, and examples
  - Address common questions or concerns
  - Allow for disagreement or tension, but land on a conclusion

Tone and flow
  - Professional yet conversational; concise wording
  - Natural speech patterns (light fillers used sparingly)
  - Smooth, real-life conversational flow
  - Lively pacing with serious and lighter moments
  - Use rhetorical questions/hypotheticals to engage
  - Allow natural interruptions and back-and-forth
  - Maximize information density: convey maximum content with minimum words
  - Avoid redundant phrases, unnecessary qualifiers, or verbose expressions
  - Use direct, efficient language while maintaining naturalness
  - Eliminate repetition of the same information across turns

Additional
  - Occasionally mention speaker names for naturalness
  - Guest responses must be grounded in the transcript (no unsupported claims)
  - Avoid long monologues; break into exchanges
  - Dialogue tags for emotion are allowed (e.g., "she replied thoughtfully") to aid voice synthesis
  - Aim for authenticity: genuine curiosity, brief pauses to think, appropriate humor, short personal anecdotes within transcript bounds
  - Do not invent information; do not drop details from the transcript
  - Prioritize brevity: use shorter, more impactful sentences that convey the same meaning
  - Remove filler words, hedging phrases, and unnecessary elaboration
  - Consolidate related points into single, well-crafted statements rather than multiple verbose turns
  - Ensure each speaker turn adds unique value—avoid restating what was just said

Segment details:
- Duration: about {{ duration }} minutes (~{{ (duration * 25) | int }} words)
- Topic: {{ descriptions }}

Keep all analogies, stories, examples, and quotes from the transcript.

Transcript:

{{ text }}

Return only the full dialogue transcript, nothing else (no time budget or section labels).
"""

# Template for combining multiple dialogue sections
COMBINE_DIALOGUES_PROMPT = """You are polishing a podcast transcript to keep it engaging while preserving content and structure. You have three inputs:

1. Podcast outline
<outline>
{{ outline }}
</outline>

2. Current dialogue transcript
<dialogue>
{{ dialogue_transcript }}
</dialogue>

3. Next section to integrate
<next_section>
{{ next_section }}
</next_section>

Current section: {{ current_section }}

Do the following:
- Seamlessly merge the next section into the existing dialogue
- Keep all important information from both sections
- Aggressively trim redundancy while maintaining high information density
- Actively reduce word count by removing unnecessary words, phrases, and repetitive content
- Break long monologues into natural back-and-forth
- Limit each speaker turn to at most 3 sentences
- Keep the conversation flowing smoothly between topics
- Consolidate overlapping information: if both sections cover the same point, merge into a single concise statement

Guidelines:
- Avoid explicit transitions like "Welcome back" or "Now let's discuss"
- Do not insert mid-conversation intros or conclusions
- Do not announce section changes inside the dialogue
- Merge related topics per the outline
- Maintain a natural conversational tone
- Remove redundant transitional phrases and filler words when combining sections
- Eliminate duplicate information: if a point appears in both sections, present it only once in the most concise form
- Prioritize unique information from each section and remove any repeated concepts or explanations
- Aim to reduce the combined length by 15-25% compared to simply concatenating the sections, while preserving all essential content

Output the full revised dialogue transcript from the start, with the next section already integrated."""

# Template for converting dialogue to JSON format
DIALOGUE_PROMPT = """Convert a podcast transcript into structured JSON. You have:

1) Speakers:
   - Speaker 1: {{ speaker_1_name }}
   - Speaker 2: {{ speaker_2_name }}

2) Transcript:
{{ text }}

3) Required output schema:
{{ schema }}

Do:
- Convert the transcript exactly into the JSON format
- Preserve all dialogue content
- Map {{ speaker_1_name }} to "speaker-1"
- Map {{ speaker_2_name }} to "speaker-2"

Must, without exception:
- Use proper Unicode characters directly (e.g., use ' instead of \\u2019)
- Ensure apostrophes/quotes/special characters are formatted correctly
- Do not escape Unicode characters

Also must:
- Render numbers and symbols in spoken form:
  * Numbers spelled out (e.g., "one thousand" not "1000")
  * Currency as "[amount] [unit of currency]" (e.g., "one thousand dollars" not "$1000")
  * Math symbols spoken (e.g., "equals" not "=", "plus" not "+")
  * Percentages as "percent" (e.g., "fifty percent" not "50%")

Output only the JSON following the provided schema, keeping all conversational detail and speaker attributions. Use proper Unicode directly, no escaped sequences."""

# Dictionary mapping prompt names to their prompt strings
PODCAST_PROMPTS: dict[str, str] = {
    "summary_prompt": SUMMARY_PROMPT,
    "multi_pdf_outline_prompt": MULTI_PDF_OUTLINE_PROMPT,
    "multi_pdf_structured_outline_prompt": MULTI_PDF_STRUCTURED_OUTLINE_PROMPT,
    "prompt_with_references": PROMPT_WITH_REFERENCES,
    "no_references_prompt": NO_REFERENCES_PROMPT,
    "transcript_to_dialogue_prompt": TRANSCRIPT_TO_DIALOGUE_PROMPT,
    "combine_dialogues_prompt": COMBINE_DIALOGUES_PROMPT,
    "dialogue_prompt": DIALOGUE_PROMPT,
}
