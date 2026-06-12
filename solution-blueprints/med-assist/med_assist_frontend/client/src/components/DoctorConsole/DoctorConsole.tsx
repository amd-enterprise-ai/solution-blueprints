// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useCallback, useEffect } from "react";
import { useLocalParticipant, useRemoteParticipants } from "@livekit/components-react";
import styles from "./DoctorConsole.module.css";
import { Header } from "../Header/Header";
import type { RecordingState } from "../Header/Header";
import { BottomBar } from "../BottomBar/BottomBar";
import { AlertsPanel } from "../AlertsPanel/AlertsPanel";
import { TranscriptPanel } from "../TranscriptPanel/TranscriptPanel";
import type { ConnectionStatus } from "../TranscriptPanel/TranscriptPanel";
import { ReportPanel } from "../ReportPanel/ReportPanel";
import { CriticalBanner } from "../CriticalBanner/CriticalBanner";
import { ReportModal } from "../ReportModal/ReportModal";
import { ConfirmDialog } from "../ConfirmDialog/ConfirmDialog";
import { useTranscript } from "../../hooks/useTranscript";
import { stripMarkdown } from "../../utils";

export function DoctorConsole() {
  const {
    lines,
    report,
    reportLoading,
    requestReport,
    getTranscriptText,
    setTranscriptPaused,
    alerts,
    acknowledgeAlert,
    dismissAlert,
  } = useTranscript();
  const { localParticipant } = useLocalParticipant();
  const remoteParticipants = useRemoteParticipants();
  const [showReportModal, setShowReportModal] = useState(false);
  const [showStopConfirm, setShowStopConfirm] = useState(false);
  const [recordingState, setRecordingState] = useState<RecordingState>("recording");
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "failed">("saved");
  const [draft, setDraft] = useState<string>("");
  const [agentReady, setAgentReady] = useState(false);
  const [linesAtReport, setLinesAtReport] = useState<number>(0);

  useEffect(() => {
    if (agentReady) return;
    if (remoteParticipants.length > 0) {
      setAgentReady(true);
    }
  }, [remoteParticipants, agentReady]);

  const hasNewTranscriptSinceReport = report !== null && lines.length > linesAtReport;

  const connectionStatus: ConnectionStatus =
    recordingState === "stopped" ? "disconnected" : recordingState === "paused" ? "paused" : "live";

  // Sync mic mute and transcript gating with recording state
  useEffect(() => {
    if (!localParticipant) return;

    if (recordingState === "recording") {
      localParticipant.setMicrophoneEnabled(true);
      setTranscriptPaused(false);
    } else {
      localParticipant.setMicrophoneEnabled(false);
      setTranscriptPaused(true);
    }
  }, [recordingState, localParticipant, setTranscriptPaused]);

  // Strip markdown when a new report comes in
  useEffect(() => {
    if (report) {
      setDraft(stripMarkdown(report));
      setLinesAtReport(lines.length);
    }
  }, [report]);

  // Handle recording state changes from Header (pause/resume)
  const handleRecordingStateChange = useCallback(
    (next: RecordingState) => {
      if (recordingState === "stopped") return;
      setRecordingState(next);
    },
    [recordingState],
  );

  const handleStopSession = useCallback(() => {
    setRecordingState("stopped");
    setShowStopConfirm(false);
  }, []);

  const handleSaveDraft = useCallback(() => {
    setSaveStatus("saving");
    setTimeout(() => setSaveStatus("saved"), 1500);
  }, []);

  const handleRequestStop = useCallback(() => {
    setShowStopConfirm(true);
  }, []);

  // Show waiting state until agent connects
  if (!agentReady) {
    return (
      <div className={styles.layout}>
        <div className={styles.waitingOverlay}>
          <div className={styles.waitingSpinner} />
          <p className={styles.waitingText}>Waiting for agent to connect…</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.layout}>
      <Header
        recordingState={recordingState}
        onRecordingStateChange={handleRecordingStateChange}
        onStop={handleRequestStop}
      />

      <div className={styles.body}>
        <CriticalBanner alerts={alerts} />

        <main className={styles.main}>
          <aside className={styles.panelAlerts} aria-label='Clinical alerts'>
            <AlertsPanel alerts={alerts} onAcknowledge={acknowledgeAlert} onDismiss={dismissAlert} />
          </aside>

          <section className={styles.panelTranscript} aria-label='Live transcript'>
            <TranscriptPanel lines={lines} connectionStatus={connectionStatus} />
          </section>

          <aside className={styles.panelReport} aria-label='Medical report'>
            <ReportPanel
              report={report}
              draft={draft}
              onDraftChange={setDraft}
              loading={reportLoading}
              onGenerate={() => requestReport(getTranscriptText())}
              onRefresh={() => requestReport(getTranscriptText())}
              hasTranscript={lines.length > 0}
              hasNewData={hasNewTranscriptSinceReport}
            />
          </aside>
        </main>
      </div>

      <footer className={styles.bottomBar}>
        <BottomBar
          onStopSession={handleRequestStop}
          onSaveDraft={handleSaveDraft}
          onViewReport={() => setShowReportModal(true)}
          saveStatus={saveStatus}
        />
      </footer>

      {showReportModal && (
        <ReportModal draft={draft} onDraftChange={setDraft} onClose={() => setShowReportModal(false)} />
      )}

      {showStopConfirm && (
        <ConfirmDialog
          title='Stop session?'
          message='Transcript and alerts will stop updating. You can still view and edit the report after stopping.'
          confirmLabel='Stop session'
          onConfirm={handleStopSession}
          onCancel={() => setShowStopConfirm(false)}
        />
      )}
    </div>
  );
}
