#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# claude_job.sh — launch real Claude Code with its inference routed THROUGH the
# lemonade telemetry proxy (which forwards to the local Lemonade 8B on CPU and
# emits an llm.request Splunk event per call).
#
# This stage exercises the INFERENCE plane only:
# no gateway key, no MCP tools — just prove Claude Code's LLM traffic flows
# through the proxy and lands audit events. The local 8B is weak, so the runner
# treats this stage as best-effort (SKIP) while the deterministic curl stage is
# the HARD proof.
#
# Args: $1 = prompt
# Env:  GATEWAY_URL = the proxy base URL (required), MODEL = local model id.
set -uo pipefail

PROMPT="${1:?prompt required}"

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"

# Inference plane: Claude Code -> telemetry proxy -> local Lemonade. Auth is a
# dummy (local, no gateway subscription key).
export ANTHROPIC_BASE_URL="${GATEWAY_URL:?proxy base URL required in GATEWAY_URL}"
export ANTHROPIC_API_KEY="dummy"
export ANTHROPIC_AUTH_TOKEN="dummy"
MODEL="${MODEL:-Qwen3-8B-GGUF}"
export ANTHROPIC_MODEL="$MODEL"
export ANTHROPIC_SMALL_FAST_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$MODEL"
export CLAUDE_CODE_ATTRIBUTION_HEADER=0
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

MAXTURNS="${MAXTURNS:-2}"

# Inference-only: disallow every tool so this is a pure completion (the point is
# the LLM traffic through the proxy, not tool use).
exec timeout "${CC_TIMEOUT:-300}" claude -p "$PROMPT" \
  --disallowedTools "Task,Agent,Bash,BashOutput,KillShell,Read,Write,Edit,MultiEdit,NotebookEdit,Glob,Grep,WebFetch,WebSearch,Skill,Workflow" \
  --max-turns "$MAXTURNS" \
  --output-format stream-json --verbose
