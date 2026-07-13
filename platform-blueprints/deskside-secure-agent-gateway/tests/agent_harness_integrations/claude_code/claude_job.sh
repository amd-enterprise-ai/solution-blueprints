#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# claude_job.sh — launch real Claude Code to solve a SWE-bench instance, with its
# inference coming from the AMD LLM Gateway (claude-opus-4.8) and its ONLY tool
# being the CLIENT-SIDE axis MCP connector's `run`. Every command the model runs
# therefore funnels through DefenseClaw admission -> AXIS sandbox -> the Splunk
# event builder (shipping to the real Splunk HEC).
#
# Claude Code itself is NOT sandboxed; what is contained + audited is each command
# it runs via `run`. Built-in tools are disallowed so `run` is the only way the
# model can touch the machine.
#
# Args: $1 = path to .mcp.json, $2 = prompt file
# Env:  GATEWAY_KEY (required), GATEWAY_URL, MODEL, WORKDIR (repo cwd), TASKVENV
set -uo pipefail

MCP_JSON="${1:?mcp.json path required}"
PROMPT_FILE="${2:?prompt file required}"

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"

# Activate the task venv (flask + pytest) so commands the model runs inside the
# AXIS sandbox (e.g. `python -m pytest`) resolve. The MCP server is spawned as a
# child of this process and inherits this env; `axis run` passes it into the box.
if [ -n "${TASKVENV:-}" ] && [ -f "$TASKVENV/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$TASKVENV/bin/activate"
fi

# Inference plane. Two modes:
#   INFERENCE_MODE=anthropic -> Claude Code -> api.anthropic.com (x-api-key)
#   INFERENCE_MODE=gateway   -> Claude Code -> AMD LLM Gateway (subscription key) [default]
INFERENCE_MODE="${INFERENCE_MODE:-gateway}"
if [ "$INFERENCE_MODE" = "anthropic" ]; then
  export ANTHROPIC_BASE_URL="https://api.anthropic.com"
  export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY required}"
  unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_CUSTOM_HEADERS CLAUDE_CODE_USE_BEDROCK CLAUDE_CODE_USE_VERTEX
  MODEL="${MODEL:-claude-opus-4-8}"
else
  export ANTHROPIC_BASE_URL="${GATEWAY_URL:-https://<llm-gateway>/Anthropic}"
  export ANTHROPIC_API_KEY="dummy"
  export ANTHROPIC_AUTH_TOKEN="dummy"
  export ANTHROPIC_CUSTOM_HEADERS="Ocp-Apim-Subscription-Key: ${GATEWAY_KEY:?GATEWAY_KEY required}"
  MODEL="${MODEL:-claude-opus-4-8}"
fi
export ANTHROPIC_MODEL="$MODEL"
export ANTHROPIC_SMALL_FAST_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_OPUS_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_SONNET_MODEL="$MODEL"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="$MODEL"
export CLAUDE_CODE_ATTRIBUTION_HEADER=0
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192

MAXTURNS="${MAXTURNS:-20}"
PROMPT="$(cat "$PROMPT_FILE")"

[ -n "${WORKDIR:-}" ] && cd "$WORKDIR"

# Force Claude Code to use ANTHROPIC_API_KEY rather than session OAuth.
# Write a persistent settings file (not cleaned up before exec).
_CC_SETTINGS="/tmp/cc-settings-$$.json"
echo '{"apiKeyHelper":""}' > "$_CC_SETTINGS"

# Allow ONLY the connector's run tool; disallow every built-in (especially
# Task/Agent, which would spawn a subagent that bypasses the connector entirely).
exec timeout "${CC_TIMEOUT:-900}" claude -p "$PROMPT" \
  --bare \
  --settings "$_CC_SETTINGS" \
  --mcp-config "$MCP_JSON" \
  --allowedTools "mcp__axis__run" \
  --disallowedTools "Task,Agent,Bash,BashOutput,KillShell,Read,Write,Edit,MultiEdit,NotebookEdit,Glob,Grep,WebFetch,WebSearch,Skill,Workflow,CronCreate,CronDelete,CronList,EnterWorktree,ExitWorktree,ScheduleWakeup,SendMessage,TaskCreate,TaskGet,TaskList,TaskUpdate" \
  --max-turns "$MAXTURNS" \
  --output-format stream-json --verbose
