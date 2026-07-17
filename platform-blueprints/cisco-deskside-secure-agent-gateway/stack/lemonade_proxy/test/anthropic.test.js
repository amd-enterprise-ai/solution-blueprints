// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";

import { extractRequest, extractResponseJson, parseAnthropicSSE } from "../src/anthropic.js";

test("extractRequest reads model/stream/messages and flattens prompt text", () => {
  const info = extractRequest({
    model: "Qwen3-8B-GGUF",
    stream: true,
    system: "you are helpful",
    messages: [
      { role: "user", content: "hello" },
      { role: "assistant", content: [{ type: "text", text: "hi there" }] },
      { role: "user", content: [{ type: "text", text: "run echo OK" }] },
    ],
  });
  assert.equal(info.model, "Qwen3-8B-GGUF");
  assert.equal(info.stream, true);
  assert.equal(info.messages, 3);
  assert.match(info.promptText, /you are helpful/);
  assert.match(info.promptText, /hello/);
  assert.match(info.promptText, /run echo OK/);
});

test("extractRequest tolerates a minimal body", () => {
  const info = extractRequest({});
  assert.equal(info.model, "unknown");
  assert.equal(info.stream, false);
  assert.equal(info.messages, 0);
  assert.equal(info.promptText, "");
});

test("extractResponseJson reads completion text + usage", () => {
  const r = extractResponseJson({
    content: [{ type: "text", text: "the answer" }],
    usage: { input_tokens: 11, output_tokens: 4 },
    stop_reason: "end_turn",
  });
  assert.equal(r.completionText, "the answer");
  assert.equal(r.promptTokens, 11);
  assert.equal(r.completionTokens, 4);
  assert.equal(r.stopReason, "end_turn");
});

test("parseAnthropicSSE accumulates text + usage across events", () => {
  const raw = [
    'event: message_start',
    'data: {"type":"message_start","message":{"usage":{"input_tokens":9,"output_tokens":0}}}',
    "",
    'event: content_block_delta',
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello "}}',
    "",
    'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"world"}}',
    "",
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":7}}',
    "",
    "data: [DONE]",
    "",
  ].join("\n");
  const r = parseAnthropicSSE(raw);
  assert.equal(r.completionText, "Hello world");
  assert.equal(r.promptTokens, 9);
  assert.equal(r.completionTokens, 7);
  assert.equal(r.stopReason, "end_turn");
});

test("parseAnthropicSSE skips garbled lines without throwing", () => {
  const raw = ["data: {not json", 'data: {"type":"content_block_delta","delta":{"text":"x"}}', ""].join("\n");
  const r = parseAnthropicSSE(raw);
  assert.equal(r.completionText, "x");
});

// --- OpenAI shape (client-side Lemonade speaks OpenAI, not Anthropic) ------
test("extractResponseJson reads the OpenAI chat/completions shape", () => {
  const r = extractResponseJson({
    choices: [{ message: { content: "ROCM_OK" }, finish_reason: "stop" }],
    usage: { prompt_tokens: 12, completion_tokens: 3 },
  });
  assert.equal(r.completionText, "ROCM_OK");
  assert.equal(r.promptTokens, 12);
  assert.equal(r.completionTokens, 3);
  assert.equal(r.stopReason, "stop");
});

test("extractResponseJson falls back to reasoning_content when content is empty (Qwen)", () => {
  const r = extractResponseJson({
    choices: [{ message: { content: "", reasoning_content: "thinking…" }, finish_reason: "length" }],
    usage: { prompt_tokens: 5, completion_tokens: 20 },
  });
  assert.equal(r.completionText, "thinking…");
  assert.equal(r.completionTokens, 20);
  assert.equal(r.stopReason, "length");
});

test("parseAnthropicSSE also parses an OpenAI-style delta stream", () => {
  const raw = [
    'data: {"choices":[{"delta":{"content":"Hel"}}]}',
    'data: {"choices":[{"delta":{"content":"lo"}}]}',
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":4,"completion_tokens":2}}',
    "data: [DONE]",
    "",
  ].join("\n");
  const r = parseAnthropicSSE(raw);
  assert.equal(r.completionText, "Hello");
  assert.equal(r.promptTokens, 4);
  assert.equal(r.completionTokens, 2);
  assert.equal(r.stopReason, "stop");
});
