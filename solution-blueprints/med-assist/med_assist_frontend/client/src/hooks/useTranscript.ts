// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useCallback, useRef } from "react";
import { useDataChannel } from "@livekit/components-react";
import type { ReceivedDataMessage } from "@livekit/components-core";

export interface TranscriptLine {
  id: string;
  who: "doctor" | "patient";
  text: string;
  timestamp: string;
}

export interface Alert {
  id: string;
  severity: "critical" | "warning" | "info";
  title: string;
  evidence: string;
  time: string;
  status: "active" | "acknowledged" | "dismissed";
  acknowledgedAt?: string;
  dismissedAt?: string;
}

// Internal state for a pending report request
interface PendingReport {
  transcriptText: string;
  resolve: (report: string) => void;
  timeoutHandle: ReturnType<typeof setTimeout>;
  attempt: number;
}

const REPORT_TIMEOUT_MS = 30_000;
const REPORT_MAX_ATTEMPTS = 3;

// ---------------------------------------------------------------------------
// Remote logging — sends log entries to POST /api/log so they appear in the
// container stdout. Errors are silently ignored so logging never breaks the app.
// ---------------------------------------------------------------------------
type LogLevel = "debug" | "info" | "warn" | "error";

function remoteLog(level: LogLevel, message: string, context?: Record<string, unknown>): void {
  fetch("/api/log", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ level, message, context: context ?? null }),
  }).catch(() => {
    /* ignore network errors — logging must never break the app */
  });
}


function formatTime(isoOrMs: string | number): string {
  const d = new Date(isoOrMs);
  if (isNaN(d.getTime())) return "";
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function formatAlertTime(isoString: string): string {
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

export function useTranscript() {
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [report, setReport] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const transcriptPausedRef = useRef(false);

  // Holds the current pending report keyed by request_id
  const pendingReportRef = useRef<Map<string, PendingReport>>(new Map());

  // We store the send function in a ref so retry callbacks always have the latest version
  const sendRef = useRef<((data: Uint8Array, opts: { reliable: boolean; topic: string }) => void) | null>(null);

  const setTranscriptPaused = useCallback((paused: boolean) => {
    transcriptPausedRef.current = paused;
  }, []);

  // ----- core send helper -----
  const sendReportRequest = useCallback((requestId: string, transcriptText: string, attempt: number) => {
    if (!sendRef.current) {
      remoteLog("warn", `[report] sendRef not ready, cannot send request_id=${requestId} (attempt ${attempt}/${REPORT_MAX_ATTEMPTS})`);
      return;
    }
    const payload = JSON.stringify({
      type: "request_report",
      transcript: transcriptText,
      request_id: requestId,
    });
    remoteLog("info", `[report] sending request request_id=${requestId} (attempt ${attempt}/${REPORT_MAX_ATTEMPTS}) transcript_len=${transcriptText.length}`);
    sendRef.current(new TextEncoder().encode(payload), { reliable: true, topic: "report_request" });
  }, []);

  // ----- schedule a retry for an existing request_id -----
  const scheduleRetry = useCallback(
      (requestId: string) => {
        const pending = pendingReportRef.current.get(requestId);
        if (!pending) return;

        const nextAttempt = pending.attempt + 1;

        if (nextAttempt > REPORT_MAX_ATTEMPTS) {
          remoteLog("error", `[report] all ${REPORT_MAX_ATTEMPTS} attempts exhausted for request_id=${requestId}, giving up`);
          pending.resolve("Error: report not received after retries");
          pendingReportRef.current.delete(requestId);
          setReportLoading(false);
          return;
        }

        remoteLog("warn", `[report] timeout waiting for request_id=${requestId}, retrying (attempt ${nextAttempt}/${REPORT_MAX_ATTEMPTS})`);

        const timeoutHandle = setTimeout(() => scheduleRetry(requestId), REPORT_TIMEOUT_MS);

        pendingReportRef.current.set(requestId, {
          ...pending,
          attempt: nextAttempt,
          timeoutHandle,
        });

        sendReportRequest(requestId, pending.transcriptText, nextAttempt);
      },
      [sendReportRequest],
  );

  // ----- incoming message handler -----
  const onMessage = useCallback(
      (msg: ReceivedDataMessage) => {
        try {
          const text = new TextDecoder().decode(msg.payload);
          const data = JSON.parse(text);

          // ── Report response ──────────────────────────────────────────────────
          if (data.type === "report") {
            const requestId: string = data.request_id ?? "(no id)";
            const reportLength = (data.report ?? "").length;

            const pending = pendingReportRef.current.get(requestId);

            if (pending) {
              remoteLog("info", `[report] received response request_id=${requestId} after attempt ${pending.attempt}/${REPORT_MAX_ATTEMPTS} at ${new Date().toISOString()}, length=${reportLength}`);
              clearTimeout(pending.timeoutHandle);
              pendingReportRef.current.delete(requestId);
              if (!data.report) {
                remoteLog("warn", `[report] response body is empty for request_id=${requestId} — showing placeholder`);
              }
              pending.resolve(data.report || "(empty report)");
            } else {
              // No matching pending entry — duplicate delivery after retry resolved it, or unknown id
              remoteLog("warn", `[report] received response for unknown/already-resolved request_id=${requestId} length=${reportLength} — ignoring`);
            }

            setReport(data.report || "(empty report)");
            setReportLoading(false);
          }

          // ── Transcript line ──────────────────────────────────────────────────
          if (data.type === "transcript" && data.identity && data.text && !transcriptPausedRef.current) {
            const line: TranscriptLine = {
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              who: data.identity as "doctor" | "patient",
              text: data.text,
              timestamp: formatTime(data.timestamp || new Date()),
            };
            setLines((prev) => [...prev, line]);
          }

          // ── Alert ────────────────────────────────────────────────────────────
          if (data.severity && data.title) {
            remoteLog("info", `[alert] received severity=${data.severity} title=${data.title}`);
            const alert: Alert = {
              id: `alert-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              severity: data.severity as "critical" | "warning" | "info",
              title: data.title,
              evidence: data.evidence || "",
              time: data.timestamp ? formatAlertTime(data.timestamp) : formatAlertTime(new Date().toISOString()),
              status: "active",
            };
            setAlerts((prev) => [alert, ...prev]);
          }
        } catch (err) {
          // Log unexpected parse errors but don't crash
          remoteLog("warn", `[data] failed to parse incoming message: ${String(err)}`);
        }
      },
      [scheduleRetry],
  );

  const { send } = useDataChannel(onMessage);

  // Keep sendRef in sync so retry callbacks always have the latest `send`
  sendRef.current = send;

  // ----- public requestReport -----
  const requestReport = useCallback(
      (transcriptText: string) => {
        if (!transcriptText.trim()) return;

        const requestId = `report-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        remoteLog("info", `[report] requesting report request_id=${requestId} at ${new Date().toISOString()}`);

        setReportLoading(true);
        setReport(null);

        // Register pending entry before sending so the response handler can find it
        // even if the response arrives synchronously
        const timeoutHandle = setTimeout(() => scheduleRetry(requestId), REPORT_TIMEOUT_MS);

        pendingReportRef.current.set(requestId, {
          transcriptText,
          resolve: (resolvedReport: string) => {
            setReport(resolvedReport);
            setReportLoading(false);
          },
          timeoutHandle,
          attempt: 1,
        });

        sendReportRequest(requestId, transcriptText, 1);
      },
      [sendReportRequest, scheduleRetry],
  );

  const getTranscriptText = useCallback((): string => {
    return lines.map((l) => `${l.who === "doctor" ? "Doctor" : "Patient"}: ${l.text}`).join("\n");
  }, [lines]);

  const acknowledgeAlert = useCallback((id: string) => {
    setAlerts((prev) =>
        prev.map((a) =>
            a.id === id
                ? {
                  ...a,
                  status: "acknowledged",
                  acknowledgedAt: new Date().toLocaleTimeString("en-US", {
                    hour: "numeric",
                    minute: "2-digit",
                    hour12: true,
                  }),
                }
                : a,
        ),
    );
  }, []);

  const dismissAlert = useCallback((id: string) => {
    setAlerts((prev) =>
        prev.map((a) =>
            a.id === id
                ? {
                  ...a,
                  status: "dismissed",
                  dismissedAt: new Date().toLocaleTimeString("en-US", {
                    hour: "numeric",
                    minute: "2-digit",
                    hour12: true,
                  }),
                }
                : a,
        ),
    );
  }, []);

  return {
    lines,
    report,
    reportLoading,
    requestReport,
    getTranscriptText,
    setTranscriptPaused,
    alerts,
    acknowledgeAlert,
    dismissAlert,
  };
}
