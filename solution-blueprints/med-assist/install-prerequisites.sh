#!/usr/bin/env bash
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT
# =============================================================================
# install-prerequisites.sh
#
# Installs (or uninstalls) cluster-level prerequisites (STUNner).
# Run this ONCE per cluster before deploying.
#
# Usage:
#   ./install-prerequisites.sh [--namespace <ns>] [--uninstall]
#
#   --namespace <ns>   Namespace for STUNner operator (default: stunner-system)
#   --uninstall        Remove STUNner operator instead of installing it
#
# Requirements:
#   - kubectl configured and pointing at your target cluster
#   - helm v3 installed
#   - cluster-admin or rights to create ClusterRole, ClusterRoleBinding, and CRDs.
# =============================================================================

set -euo pipefail

STUNNER_CHART_VERSION="1.1.0"
STUNNER_NAMESPACE="stunner-system"
UNINSTALL=false

# STUNner CRDs are sourced directly from the chart repository to avoid
# fragile awk-based YAML splitting. The URL matches STUNNER_CHART_VERSION.
STUNNER_CRDS_URL="https://raw.githubusercontent.com/l7mp/stunner-helm/4c6736ee334433636a6cfc08917a9ff1767657a8/helm/stunner/crds/stunner-crds.yaml"

STUNNER_CRD_NAMES=(
  dataplanes.stunner.l7mp.io
  gatewayconfigs.stunner.l7mp.io
  staticservices.stunner.l7mp.io
  udproutes.stunner.l7mp.io
)

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)
      STUNNER_NAMESPACE="$2"
      shift 2
      ;;
    --uninstall)
      UNINSTALL=true
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--namespace <ns>] [--uninstall]"
      exit 1
      ;;
  esac
done

# -----------------------------------------------------------------------------
# Common checks
# -----------------------------------------------------------------------------
echo "==> Checking prerequisites..."
echo -n "    - helm installed... "
if ! command -v helm &>/dev/null; then
  echo "FAILED"
  echo "ERROR: helm is not installed. See https://helm.sh/docs/intro/install/"
  exit 1
fi
echo "OK"

echo -n "    - kubectl installed... "
if ! command -v kubectl &>/dev/null; then
  echo "FAILED"
  echo "ERROR: kubectl is not installed."
  exit 1
fi
echo "OK"

echo -n "    - cluster access... "
if ! kubectl cluster-info &>/dev/null; then
  echo "FAILED"
  echo "ERROR: kubectl cannot reach the cluster. Check your kubeconfig."
  exit 1
fi
echo "OK"

echo -n "    - cluster-admin permissions... "
if ! kubectl auth can-i create clusterroles --all-namespaces &>/dev/null; then
  echo "FAILED"
  echo "ERROR: Insufficient permissions. Installing STUNner requires cluster-admin"
  echo "       or rights to create ClusterRole, ClusterRoleBinding, and CRDs."
  echo "       Contact your cluster administrator to run this script."
  exit 1
fi
echo "OK"

# -----------------------------------------------------------------------------
# UNINSTALL
# -----------------------------------------------------------------------------
if [ "$UNINSTALL" = true ]; then
  echo ""
  echo "==> Uninstalling STUNner from namespace '$STUNNER_NAMESPACE'..."

  echo -n "    - removing Helm release... "
  if helm status stunner -n "$STUNNER_NAMESPACE" &>/dev/null; then
    helm uninstall stunner -n "$STUNNER_NAMESPACE" &>/dev/null
    echo "OK"
  else
    echo "SKIPPED (not found)"
  fi

  echo -n "    - removing STUNner CRDs... "
  STUNNER_CRDS=$(kubectl get crd -o name 2>/dev/null | grep "stunner.l7mp.io" || true)
  if [ -n "$STUNNER_CRDS" ]; then
    echo "$STUNNER_CRDS" | xargs kubectl delete &>/dev/null
    echo "OK"
  else
    echo "SKIPPED (not found)"
  fi

  echo ""
  echo "==> STUNner uninstalled successfully."
  exit 0
fi

# -----------------------------------------------------------------------------
# Helm repo setup
# -----------------------------------------------------------------------------
echo ""
echo "==> Setting up Helm repository..."

echo -n "    - adding Helm repository... "
helm repo add stunner https://l7mp.io/stunner 2>/dev/null || true
echo "OK"

echo -n "    - updating Helm repository... "
helm repo update stunner &>/dev/null
echo "OK"

# -----------------------------------------------------------------------------
# CRD handling
#
# Helm cannot selectively skip CRDs — --skip-crds skips ALL of them.
# The chart bundles two categories of CRDs:
#   1. STUNner CRDs    (*.stunner.l7mp.io)          — must be present before
#      the operator can start; applied from the canonical upstream URL.
#   2. Gateway API CRDs (*.gateway.networking.k8s.io) — often pre-installed
#      by ArgoCD or other controllers; applying via Helm SSA causes field-
#      manager conflicts. Skipped when already present in the cluster.
#
# After apply, we wait for all STUNner CRDs to reach Established status so
# that helm install does not race against API server registration.
# -----------------------------------------------------------------------------
echo ""
echo "==> Ensuring required CRDs are installed..."

echo -n "    - applying STUNner CRDs (stunner.l7mp.io)... "
if ! kubectl apply -f "$STUNNER_CRDS_URL" &>/tmp/stunner-crd-err; then
  echo "FAILED"
  cat /tmp/stunner-crd-err
  exit 1
fi
echo "OK"

echo -n "    - waiting for STUNner CRDs to be established... "
if ! kubectl wait --for=condition=established \
  "${STUNNER_CRD_NAMES[@]/#/crd/}" \
  --timeout=60s &>/dev/null; then
  echo "FAILED"
  echo "ERROR: STUNner CRDs did not become established in time."
  exit 1
fi
echo "OK"

echo -n "    - checking Gateway API CRDs... "
if kubectl get crd gateways.gateway.networking.k8s.io &>/dev/null; then
  echo "PRESENT (skipping to avoid conflicts)"
else
  echo "MISSING — installing from chart..."
  if ! helm show crds stunner/stunner --version "$STUNNER_CHART_VERSION" \
    | kubectl apply -f - &>/tmp/gwapi-crd-err; then
    echo "FAILED"
    cat /tmp/gwapi-crd-err
    exit 1
  fi
  echo "    - Gateway API CRDs installed."
fi

echo -n "    - checking for leftover STUNner ClusterRoles... "
LEFTOVER_CRS=$(kubectl get clusterrole -o name 2>/dev/null \
  | grep "stunner-gateway-operator" || true)
if [ -n "$LEFTOVER_CRS" ]; then
  echo "$LEFTOVER_CRS" | xargs kubectl delete &>/dev/null
  echo "REMOVED (will be recreated by Helm)"
else
  echo "NONE"
fi

echo -n "    - checking for leftover STUNner ClusterRoleBindings... "
LEFTOVER_CRBS=$(kubectl get clusterrolebinding -o name 2>/dev/null \
  | grep "stunner-gateway-operator" || true)
if [ -n "$LEFTOVER_CRBS" ]; then
  echo "$LEFTOVER_CRBS" | xargs kubectl delete &>/dev/null
  echo "REMOVED (will be recreated by Helm)"
else
  echo "NONE"
fi

# -----------------------------------------------------------------------------
# INSTALL
# STUNner Gateway Operator — cluster-scoped, install once per cluster.
# Manages TURN/STUN gateways for WebRTC media ingress.
# https://github.com/l7mp/stunner
# -----------------------------------------------------------------------------
echo ""
echo "==> Checking if STUNner is already installed in namespace '$STUNNER_NAMESPACE'..."

if helm status stunner -n "$STUNNER_NAMESPACE" &>/dev/null; then
  INSTALLED_VERSION=$(helm list -n "$STUNNER_NAMESPACE" -f '^stunner$' -o json \
    | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['chart'])" 2>/dev/null || echo "unknown")
  echo "    STUNner already installed: $INSTALLED_VERSION"
  echo "    Skipping. To upgrade, run:"
  echo "      helm upgrade stunner stunner/stunner -n $STUNNER_NAMESPACE --version $STUNNER_CHART_VERSION --skip-crds"
else
  echo "==> Installing STUNner v${STUNNER_CHART_VERSION} into namespace '$STUNNER_NAMESPACE'..."

  echo -n "    - installing STUNner operator... "
  if ! helm install stunner stunner/stunner \
    --version "$STUNNER_CHART_VERSION" \
    --create-namespace \
    --namespace "$STUNNER_NAMESPACE" \
    --skip-crds \
    --wait \
    --timeout 120s 2>/tmp/stunner-install-err; then
    echo "FAILED"
    echo "ERROR: helm install failed. Output:"
    cat /tmp/stunner-install-err
    exit 1
  fi
  echo "OK"
  echo "    STUNner installed successfully."
fi

# -----------------------------------------------------------------------------
# Verify operator is running
# -----------------------------------------------------------------------------
echo ""
echo -n "==> Verifying STUNner operator pod is running... "
if kubectl wait --for=condition=available deployment \
  -l "control-plane=stunner-gateway-operator-controller-manager" \
  -n "$STUNNER_NAMESPACE" \
  --timeout=60s &>/dev/null; then
  echo "OK"
else
  echo "FAILED"
  echo "    WARNING: operator pod did not become ready in time — check: kubectl get pods -n $STUNNER_NAMESPACE"
fi
