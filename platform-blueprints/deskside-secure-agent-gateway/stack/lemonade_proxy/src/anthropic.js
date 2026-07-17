// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Parse the Anthropic Messages API request/response so the proxy can build a
// meaningful llm.request event WITHOUT altering the bytes it forwards.
//
// We only READ the payloads (for model/prompt/usage). The proxy always forwards
// the original request body and streams the original response bytes back
// verbatim — parsing is best-effort telemetry, never on the data path.

/** Flatten Anthropic content (string | array of blocks) to plain text. */
function contentToText(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((b) => {
        if (typeof b === "string") return b;
        if (b && typeof b.text === "string") return b.text;
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

/** Pull model/stream/message-count/prompt text out of a Messages request body.
 *  `promptText` is the whole flattened prompt (for telemetry char counts).
 *  `lastUserText` is just the final user turn's text — the task the agent is
 *  actually asking about — which is what the semantic router should classify.
 *  Classifying the full prompt would embed the agent's huge (~35KB) system
 *  harness on every call, which is slow (CPU embedding) and drowns the signal. */
export function extractRequest(body) {
  const out = {
    model: typeof body?.model === "string" ? body.model : "unknown",
    stream: Boolean(body?.stream),
    messages: Array.isArray(body?.messages) ? body.messages.length : 0,
    promptText: "",
    lastUserText: "",
  };
  const parts = [];
  if (body?.system) parts.push(contentToText(body.system));
  if (Array.isArray(body?.messages)) {
    for (const m of body.messages) parts.push(contentToText(m?.content));
    for (let i = body.messages.length - 1; i >= 0; i--) {
      if (body.messages[i]?.role === "user") {
        const t = contentToText(body.messages[i].content);
        if (t) { out.lastUserText = t; break; }
      }
    }
  }
  out.promptText = parts.filter(Boolean).join("\n");
  if (!out.lastUserText) out.lastUserText = out.promptText;
  return out;
}

/** Decide whether a Messages request represents a genuinely NEW user turn (a
 *  fresh human prompt) vs. an agent-loop continuation (the model being called
 *  again after a tool call, where the last message carries tool_result blocks).
 *
 *  The trace model groups one user prompt with all the LLM/tool calls it
 *  triggers until the next user prompt. The proxy uses this to mint a new trace
 *  only on a real user turn. Heuristic on the Anthropic Messages shape:
 *    - the LAST message must have role "user";
 *    - and it must NOT be a tool_result continuation (content contains a
 *      tool_result block), which is how Claude Code feeds a tool's output back.
 *  Robust to string content (always a human turn) and missing/garbled bodies
 *  (treated as a new turn so a trace always exists). */
export function isNewUserTurn(body) {
  const msgs = body?.messages;
  if (!Array.isArray(msgs) || msgs.length === 0) return true;
  const last = msgs[msgs.length - 1];
  if (!last || last.role !== "user") return false;
  const content = last.content;
  if (typeof content === "string") return true;
  if (Array.isArray(content)) {
    const hasToolResult = content.some(
      (b) => b && typeof b === "object" && b.type === "tool_result",
    );
    return !hasToolResult;
  }
  return true;
}

/** Pull completion text + token usage out of a non-streaming response body.
 *  Handles BOTH the Anthropic Messages shape (`content[]`, `usage.input_tokens`,
 *  `stop_reason`) AND the OpenAI Chat Completions shape (`choices[].message`,
 *  `usage.prompt_tokens`, `choices[].finish_reason`). The client-side Lemonade
 *  server speaks OpenAI; a frontier Anthropic gateway speaks Anthropic — the
 *  proxy forwards either verbatim, so telemetry parsing must read both. */
export function extractResponseJson(body) {
  // OpenAI chat/completions shape.
  if (Array.isArray(body?.choices)) {
    const choice = body.choices[0] || {};
    const msg = choice.message || choice.delta || {};
    let text = typeof msg.content === "string" ? msg.content : contentToText(msg.content);
    // Lemonade/Qwen may return only reasoning_content when the answer is empty.
    if (!text && typeof msg.reasoning_content === "string") text = msg.reasoning_content;
    if (!text && typeof choice.text === "string") text = choice.text; // legacy completions
    return {
      completionText: text || "",
      promptTokens: numOrNull(body?.usage?.prompt_tokens),
      completionTokens: numOrNull(body?.usage?.completion_tokens),
      stopReason: typeof choice.finish_reason === "string" ? choice.finish_reason : null,
    };
  }
  // Anthropic Messages shape.
  return {
    completionText: contentToText(body?.content),
    promptTokens: numOrNull(body?.usage?.input_tokens),
    completionTokens: numOrNull(body?.usage?.output_tokens),
    stopReason: typeof body?.stop_reason === "string" ? body.stop_reason : null,
  };
}

/** Accumulate completion text + token usage from a raw Anthropic SSE stream.
 *  Robust to partial/garbled lines: anything that doesn't parse is skipped. */
export function parseAnthropicSSE(raw) {
  const out = {
    completionText: "",
    promptTokens: null,
    completionTokens: null,
    stopReason: null,
  };
  const texts = [];
  for (const line of String(raw).split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) continue;
    const payload = trimmed.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    let evt;
    try {
      evt = JSON.parse(payload);
    } catch {
      continue;
    }
    // OpenAI stream chunk: { choices:[{ delta:{content}, finish_reason }], usage }
    if (Array.isArray(evt.choices)) {
      const ch = evt.choices[0] || {};
      const d = ch.delta || {};
      if (typeof d.content === "string") texts.push(d.content);
      else if (typeof d.reasoning_content === "string") texts.push(d.reasoning_content);
      if (ch.finish_reason) out.stopReason = ch.finish_reason;
      if (evt.usage) {
        out.promptTokens = numOrNull(evt.usage.prompt_tokens) ?? out.promptTokens;
        out.completionTokens = numOrNull(evt.usage.completion_tokens) ?? out.completionTokens;
      }
      continue;
    }
    // Anthropic stream events.
    switch (evt.type) {
      case "message_start": {
        const u = evt.message?.usage;
        if (u) {
          out.promptTokens = numOrNull(u.input_tokens) ?? out.promptTokens;
          out.completionTokens = numOrNull(u.output_tokens) ?? out.completionTokens;
        }
        break;
      }
      case "content_block_delta": {
        const t = evt.delta?.text;
        if (typeof t === "string") texts.push(t);
        break;
      }
      case "message_delta": {
        if (evt.usage) {
          out.completionTokens = numOrNull(evt.usage.output_tokens) ?? out.completionTokens;
        }
        if (evt.delta?.stop_reason) out.stopReason = evt.delta.stop_reason;
        break;
      }
      default:
        break;
    }
  }
  out.completionText = texts.join("");
  return out;
}

function numOrNull(v) {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
