// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { test } from "node:test";
import assert from "node:assert/strict";

import { anthropicToOpenAI, openAIToAnthropic, openAISSEtoAnthropic } from "../src/translate.js";

test("anthropicToOpenAI: system + user text -> OpenAI messages", () => {
  const oai = anthropicToOpenAI(
    { model: "claude", system: "be terse", max_tokens: 50, messages: [{ role: "user", content: "hi" }] },
    "Qwen3-Coder-30B-A3B-Instruct-GGUF",
  );
  assert.equal(oai.model, "Qwen3-Coder-30B-A3B-Instruct-GGUF");
  assert.equal(oai.messages[0].role, "system");
  assert.equal(oai.messages[0].content, "be terse");
  assert.equal(oai.messages[1].role, "user");
  assert.equal(oai.messages[1].content, "hi");
  assert.equal(oai.max_tokens, 50);
});

test("anthropicToOpenAI: system as block array is flattened", () => {
  const oai = anthropicToOpenAI(
    { system: [{ type: "text", text: "sys A" }, { type: "text", text: "sys B" }], messages: [{ role: "user", content: "x" }] },
    "m",
  );
  assert.equal(oai.messages[0].role, "system");
  assert.match(oai.messages[0].content, /sys A[\s\S]*sys B/);
});

test("anthropicToOpenAI: tools -> OpenAI function schema", () => {
  const oai = anthropicToOpenAI(
    {
      messages: [{ role: "user", content: "run ls" }],
      tools: [{ name: "run", description: "run a cmd", input_schema: { type: "object", properties: { cmd: { type: "string" } } } }],
    },
    "m",
  );
  assert.equal(oai.tools[0].type, "function");
  assert.equal(oai.tools[0].function.name, "run");
  assert.deepEqual(oai.tools[0].function.parameters.properties.cmd, { type: "string" });
});

test("anthropicToOpenAI: assistant tool_use -> tool_calls; tool_result -> role:tool", () => {
  const oai = anthropicToOpenAI(
    {
      messages: [
        { role: "user", content: "list" },
        { role: "assistant", content: [{ type: "tool_use", id: "tu1", name: "run", input: { cmd: "ls" } }] },
        { role: "user", content: [{ type: "tool_result", tool_use_id: "tu1", content: "a.txt" }] },
      ],
    },
    "m",
  );
  const asst = oai.messages.find((m) => m.role === "assistant");
  assert.equal(asst.tool_calls[0].id, "tu1");
  assert.equal(asst.tool_calls[0].function.name, "run");
  assert.equal(JSON.parse(asst.tool_calls[0].function.arguments).cmd, "ls");
  const toolMsg = oai.messages.find((m) => m.role === "tool");
  assert.equal(toolMsg.tool_call_id, "tu1");
  assert.equal(toolMsg.content, "a.txt");
});

test("anthropicToOpenAI: stream sets stream + include_usage", () => {
  const oai = anthropicToOpenAI({ stream: true, messages: [{ role: "user", content: "x" }] }, "m");
  assert.equal(oai.stream, true);
  assert.deepEqual(oai.stream_options, { include_usage: true });
});

test("openAIToAnthropic: text completion -> Anthropic message", () => {
  const a = openAIToAnthropic(
    { id: "o1", model: "q", choices: [{ finish_reason: "stop", message: { content: "hello" } }], usage: { prompt_tokens: 4, completion_tokens: 2 } },
    "claude",
  );
  assert.equal(a.type, "message");
  assert.equal(a.role, "assistant");
  assert.equal(a.model, "claude");
  assert.equal(a.content[0].type, "text");
  assert.equal(a.content[0].text, "hello");
  assert.equal(a.stop_reason, "end_turn");
  assert.equal(a.usage.input_tokens, 4);
  assert.equal(a.usage.output_tokens, 2);
});

test("openAIToAnthropic: tool_calls -> tool_use blocks + stop_reason tool_use", () => {
  const a = openAIToAnthropic(
    {
      choices: [{ finish_reason: "tool_calls", message: { content: "", tool_calls: [{ id: "c1", function: { name: "run", arguments: '{"cmd":"ls"}' } }] } }],
      usage: { prompt_tokens: 8, completion_tokens: 3 },
    },
    "claude",
  );
  assert.equal(a.stop_reason, "tool_use");
  const tu = a.content.find((b) => b.type === "tool_use");
  assert.equal(tu.name, "run");
  assert.deepEqual(tu.input, { cmd: "ls" });
});

test("openAIToAnthropic: length finish_reason -> max_tokens", () => {
  const a = openAIToAnthropic({ choices: [{ finish_reason: "length", message: { content: "partial" } }] }, "c");
  assert.equal(a.stop_reason, "max_tokens");
});

test("openAISSEtoAnthropic: text stream -> Anthropic SSE events", () => {
  const sse = [
    'data: {"id":"m1","choices":[{"delta":{"content":"Hel"}}]}',
    'data: {"choices":[{"delta":{"content":"lo"}}]}',
    'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":1}}',
    "data: [DONE]",
    "",
  ].join("\n");
  const out = openAISSEtoAnthropic(sse, "claude");
  assert.match(out, /event: message_start/);
  assert.match(out, /"model":"claude"/);
  assert.match(out, /"type":"text_delta","text":"Hello"/);
  assert.match(out, /event: message_delta/);
  assert.match(out, /"stop_reason":"end_turn"/);
  assert.match(out, /"output_tokens":1/);
  assert.match(out, /event: message_stop/);
});

test("openAISSEtoAnthropic: tool_call stream -> tool_use content block", () => {
  const sse = [
    'data: {"id":"m2","choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"run","arguments":"{\\"cmd\\":"}}]}}]}',
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"ls\\"}"}}]}}]}',
    'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":5,"completion_tokens":4}}',
    "data: [DONE]",
    "",
  ].join("\n");
  const out = openAISSEtoAnthropic(sse, "claude");
  assert.match(out, /"type":"tool_use","id":"c1","name":"run"/);
  assert.match(out, /input_json_delta/);
  assert.match(out, /"stop_reason":"tool_use"/);
});
