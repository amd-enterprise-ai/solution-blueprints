// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Anthropic Messages <-> OpenAI Chat Completions translation.
//
// Why this exists: Claude Code speaks the Anthropic Messages API (/v1/messages),
// but the client-side Lemonade build serves only the OpenAI Chat Completions API
// (/api/v1/chat/completions). When the router keeps a call on the LOCAL tier, the
// proxy must translate the Anthropic request into OpenAI, forward to Lemonade, and
// translate the OpenAI response (JSON or SSE) back into the Anthropic shape Claude
// Code expects. FRONTIER calls are already Anthropic (AMD gateway) and pass through
// byte-for-byte — this module is only used on the local tier.
//
// Scope: text, system prompt, multi-turn history, tool definitions, tool_use /
// tool_result blocks, and streaming. It is a pragmatic bridge for the tokenomics
// A/B, not a spec-complete gateway (no vision, no citations, no thinking blocks).

import { randomBytes } from "node:crypto";

function id(prefix) {
  return prefix + randomBytes(12).toString("hex");
}

/** Anthropic content (string | block[]) -> a plain text string (text blocks only). */
function blocksToText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((b) => b && b.type === "text" && typeof b.text === "string")
    .map((b) => b.text)
    .join("\n");
}

/** Ensure every node of a JSON Schema has a `type`. llama.cpp's OpenAI-tools
 *  grammar converter rejects a schema node that has only `description` (or other
 *  keywords) with no `type` — it 500s "Unrecognized schema", which returns an
 *  empty completion. Claude Code's built-in tools contain such nodes, so we
 *  default any typeless object/property to `{"type":"string"}` (harmless — the
 *  local model doesn't strictly enforce tool schemas). Recurses into properties,
 *  items, and the *-Of combinators. */
function sanitizeSchema(node) {
  if (node == null || typeof node !== "object") return node;
  if (Array.isArray(node)) return node.map(sanitizeSchema);
  const out = {};
  for (const [k, v] of Object.entries(node)) {
    if (k === "properties" && v && typeof v === "object") {
      out.properties = {};
      for (const [pk, pv] of Object.entries(v)) out.properties[pk] = sanitizeSchema(pv);
    } else if (k === "items") {
      out.items = sanitizeSchema(v);
    } else if (k === "anyOf" || k === "oneOf" || k === "allOf") {
      out[k] = Array.isArray(v) ? v.map(sanitizeSchema) : sanitizeSchema(v);
    } else {
      out[k] = v;
    }
  }
  // A node with no type and no combinator gets a default. Objects with properties
  // -> "object"; everything else -> "string" (the safe scalar default).
  const hasType = "type" in out;
  const hasCombinator = out.anyOf || out.oneOf || out.allOf || "$ref" in out || "enum" in out || "const" in out;
  if (!hasType && !hasCombinator) {
    out.type = out.properties ? "object" : "string";
  }
  return out;
}

// ---- request: Anthropic -> OpenAI ---------------------------------------

/** Convert an Anthropic Messages request body to an OpenAI Chat Completions body.
 *  Handles: system (string|blocks) -> a leading system message; user/assistant
 *  turns; tool_use blocks -> assistant.tool_calls; tool_result blocks -> role:tool
 *  messages; Anthropic `tools` -> OpenAI `tools` (function schema). */
export function anthropicToOpenAI(body, servedModel) {
  const messages = [];

  if (body?.system) {
    const sys = typeof body.system === "string" ? body.system : blocksToText(body.system);
    if (sys) messages.push({ role: "system", content: sys });
  }

  for (const m of body?.messages || []) {
    const role = m.role;
    const content = m.content;

    if (typeof content === "string") {
      messages.push({ role, content });
      continue;
    }
    if (!Array.isArray(content)) continue;

    if (role === "assistant") {
      // Assistant turn: text -> content, tool_use -> tool_calls.
      const text = blocksToText(content);
      const toolCalls = content
        .filter((b) => b && b.type === "tool_use")
        .map((b) => ({
          id: b.id,
          type: "function",
          function: { name: b.name, arguments: JSON.stringify(b.input ?? {}) },
        }));
      const msg = { role: "assistant", content: text || null };
      if (toolCalls.length) msg.tool_calls = toolCalls;
      messages.push(msg);
      continue;
    }

    // user turn: tool_result blocks -> role:tool messages; text -> user content.
    const toolResults = content.filter((b) => b && b.type === "tool_result");
    const textParts = content.filter((b) => b && b.type === "text");
    if (toolResults.length) {
      for (const tr of toolResults) {
        messages.push({
          role: "tool",
          tool_call_id: tr.tool_use_id,
          content: typeof tr.content === "string" ? tr.content : blocksToText(tr.content),
        });
      }
    }
    if (textParts.length || !toolResults.length) {
      const text = blocksToText(content);
      if (text) messages.push({ role: "user", content: text });
    }
  }

  const out = {
    model: servedModel || body?.model,
    messages,
    max_tokens: body?.max_tokens ?? 1024,
    stream: Boolean(body?.stream),
  };
  if (typeof body?.temperature === "number") out.temperature = body.temperature;
  if (Array.isArray(body?.tools) && body.tools.length) {
    out.tools = body.tools.map((t) => ({
      type: "function",
      function: {
        name: t.name,
        description: t.description || "",
        parameters: sanitizeSchema(t.input_schema) || { type: "object", properties: {} },
      },
    }));
  }
  if (out.stream) out.stream_options = { include_usage: true };
  return out;
}

// ---- response: OpenAI -> Anthropic (non-streaming) ----------------------

const STOP_MAP = {
  stop: "end_turn",
  length: "max_tokens",
  tool_calls: "tool_use",
  function_call: "tool_use",
  content_filter: "end_turn",
};

/** Convert a non-streaming OpenAI chat completion into an Anthropic Messages
 *  response object (content blocks + usage + stop_reason). */
export function openAIToAnthropic(oai, requestedModel) {
  const choice = oai?.choices?.[0] || {};
  const msg = choice.message || {};
  const content = [];

  const text = typeof msg.content === "string" ? msg.content : "";
  if (text) content.push({ type: "text", text });

  for (const tc of msg.tool_calls || []) {
    let input = {};
    try {
      input = JSON.parse(tc.function?.arguments || "{}");
    } catch {
      input = { _raw: tc.function?.arguments };
    }
    content.push({ type: "tool_use", id: tc.id || id("toolu_"), name: tc.function?.name, input });
  }
  if (!content.length) content.push({ type: "text", text: "" });

  return {
    id: oai?.id || id("msg_"),
    type: "message",
    role: "assistant",
    model: requestedModel || oai?.model,
    content,
    stop_reason: STOP_MAP[choice.finish_reason] || "end_turn",
    stop_sequence: null,
    usage: {
      input_tokens: oai?.usage?.prompt_tokens ?? 0,
      output_tokens: oai?.usage?.completion_tokens ?? 0,
    },
  };
}

// ---- response: OpenAI SSE -> Anthropic SSE (streaming) ------------------

function sse(event, data) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Translate a full OpenAI SSE stream (as a string) into the Anthropic SSE event
 *  sequence Claude Code expects. Accumulates text + tool_call argument deltas and
 *  replays them as Anthropic content_block events. Returns the Anthropic SSE
 *  string. (Buffered translation: the proxy already tees the whole upstream body
 *  for telemetry, so we translate after collection rather than mid-flight — simpler
 *  and correct for the A/B; latency is unaffected because Lemonade is the bottleneck.) */
export function openAISSEtoAnthropic(raw, requestedModel) {
  let text = "";
  const toolCalls = []; // {id,name,args}
  let promptTokens = 0;
  let completionTokens = 0;
  let finish = "stop";
  let msgId = id("msg_");

  for (const line of String(raw).split("\n")) {
    const t = line.trim();
    if (!t.startsWith("data:")) continue;
    const payload = t.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    let evt;
    try {
      evt = JSON.parse(payload);
    } catch {
      continue;
    }
    if (evt.id) msgId = evt.id;
    if (evt.usage) {
      promptTokens = evt.usage.prompt_tokens ?? promptTokens;
      completionTokens = evt.usage.completion_tokens ?? completionTokens;
    }
    const delta = evt.choices?.[0]?.delta || {};
    if (typeof delta.content === "string") text += delta.content;
    if (evt.choices?.[0]?.finish_reason) finish = evt.choices[0].finish_reason;
    for (const tc of delta.tool_calls || []) {
      const idx = tc.index ?? 0;
      if (!toolCalls[idx]) toolCalls[idx] = { id: tc.id || id("toolu_"), name: "", args: "" };
      if (tc.id) toolCalls[idx].id = tc.id;
      if (tc.function?.name) toolCalls[idx].name += tc.function.name;
      if (tc.function?.arguments) toolCalls[idx].args += tc.function.arguments;
    }
  }

  // Build the Anthropic SSE event sequence.
  let out = "";
  out += sse("message_start", {
    type: "message_start",
    message: {
      id: msgId,
      type: "message",
      role: "assistant",
      model: requestedModel,
      content: [],
      stop_reason: null,
      stop_sequence: null,
      usage: { input_tokens: promptTokens, output_tokens: 0 },
    },
  });

  let blockIndex = 0;
  if (text) {
    out += sse("content_block_start", { type: "content_block_start", index: blockIndex, content_block: { type: "text", text: "" } });
    out += sse("content_block_delta", { type: "content_block_delta", index: blockIndex, delta: { type: "text_delta", text } });
    out += sse("content_block_stop", { type: "content_block_stop", index: blockIndex });
    blockIndex++;
  }
  for (const tc of toolCalls) {
    if (!tc) continue;
    out += sse("content_block_start", {
      type: "content_block_start",
      index: blockIndex,
      content_block: { type: "tool_use", id: tc.id, name: tc.name, input: {} },
    });
    out += sse("content_block_delta", {
      type: "content_block_delta",
      index: blockIndex,
      delta: { type: "input_json_delta", partial_json: tc.args || "{}" },
    });
    out += sse("content_block_stop", { type: "content_block_stop", index: blockIndex });
    blockIndex++;
  }

  out += sse("message_delta", {
    type: "message_delta",
    delta: { stop_reason: STOP_MAP[finish] || "end_turn", stop_sequence: null },
    usage: { output_tokens: completionTokens },
  });
  out += sse("message_stop", { type: "message_stop" });
  return out;
}
