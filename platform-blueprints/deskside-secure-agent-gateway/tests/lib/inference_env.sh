# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

# inference_env.sh — resolve how the client talks to an Anthropic-compatible
# inference endpoint, from standard Claude Code env vars. Bring your own access:
# there is NO built-in default endpoint. Source this and call
# `resolve_inference_access`; on success it exports both the Claude Code env
# (ANTHROPIC_BASE_URL + one auth mechanism) and helper vars for a preflight curl:
#
#   INFER_BASE_URL        — resolved base URL
#   INFER_AUTH_HEADER     — the single auth header line for a preflight curl
#   INFER_MODEL_DEFAULT   — a sensible default model id for the resolved endpoint
#
# Two ways to configure access (auto-detected):
#
#   Gateway with a custom auth header:
#        export GATEWAY_KEY=<your-key>        # sent as a custom auth header
#        export GATEWAY_URL=https://your-gateway   # required unless ANTHROPIC_BASE_URL is set
#
#   Anthropic standard — the API directly, or any Anthropic-compatible gateway:
#        export ANTHROPIC_API_KEY=sk-ant-...
#        # ...or a gateway:
#        export ANTHROPIC_BASE_URL=https://your-gateway
#        export ANTHROPIC_AUTH_TOKEN=your-token
#
# Advanced: a gateway with a non-standard auth header can be driven directly via
# ANTHROPIC_CUSTOM_HEADERS. `INFERENCE_MODE` is an optional override
# (`anthropic` / `gateway`).

_infer_usage() {
  cat >&2 <<'EOF'
FATAL: no inference access configured. Set ONE of these, then re-run:

  # Gateway with a custom auth header
  export GATEWAY_KEY=<your-gateway-key>

  # Anthropic standard — the API directly:
  export ANTHROPIC_API_KEY=sk-ant-...
  # ...or an Anthropic-compatible gateway:
  export ANTHROPIC_BASE_URL=https://your-gateway
  export ANTHROPIC_AUTH_TOKEN=your-token
EOF
}

# Map the GATEWAY_KEY/GATEWAY_URL alias onto the custom-header path.
_infer_gateway_alias() {
  export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-${GATEWAY_URL:?GATEWAY_URL required for the custom-header gateway}}"
  export ANTHROPIC_CUSTOM_HEADERS="${GATEWAY_AUTH_HEADER:-Ocp-Apim-Subscription-Key}: ${GATEWAY_KEY:?GATEWAY_KEY required for the custom-header gateway}"
  # Claude Code still expects these to be present even when a custom header carries auth.
  export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-dummy}"
  export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-dummy}"
  INFER_BASE_URL="$ANTHROPIC_BASE_URL"
  INFER_AUTH_HEADER="$ANTHROPIC_CUSTOM_HEADERS"
  INFER_MODEL_DEFAULT="claude-opus-4-8"
}

# Resolve inference access from the environment. Returns non-zero (after printing
# the how-to) if nothing is configured.
resolve_inference_access() {
  case "${INFERENCE_MODE:-}" in
    anthropic)
      export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
      : "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY required for INFERENCE_MODE=anthropic}"
      unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_CUSTOM_HEADERS
      INFER_BASE_URL="$ANTHROPIC_BASE_URL"
      INFER_AUTH_HEADER="x-api-key: $ANTHROPIC_API_KEY"
      INFER_MODEL_DEFAULT="claude-opus-4-8"
      return 0 ;;
    gateway)
      _infer_gateway_alias; return 0 ;;
  esac

  # Auto-detect (most specific first).
  if [ -n "${ANTHROPIC_CUSTOM_HEADERS:-}" ] && [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
    export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-dummy}"
    export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:-dummy}"
    INFER_BASE_URL="$ANTHROPIC_BASE_URL"
    INFER_AUTH_HEADER="$ANTHROPIC_CUSTOM_HEADERS"
    INFER_MODEL_DEFAULT="claude-opus-4-8"
    return 0
  fi
  if [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ] && [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
    unset ANTHROPIC_CUSTOM_HEADERS
    INFER_BASE_URL="$ANTHROPIC_BASE_URL"
    INFER_AUTH_HEADER="Authorization: Bearer $ANTHROPIC_AUTH_TOKEN"
    INFER_MODEL_DEFAULT="claude-opus-4-8"
    return 0
  fi
  if [ -n "${GATEWAY_KEY:-}" ]; then
    _infer_gateway_alias; return 0
  fi
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
    unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_CUSTOM_HEADERS
    INFER_BASE_URL="$ANTHROPIC_BASE_URL"
    INFER_AUTH_HEADER="x-api-key: $ANTHROPIC_API_KEY"
    INFER_MODEL_DEFAULT="claude-opus-4-8"
    return 0
  fi

  _infer_usage
  return 1
}
