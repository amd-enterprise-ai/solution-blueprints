// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef } from "react";
import type { TranscriptLine } from "../../hooks/useTranscript";
import styles from "./TranscriptPanel.module.css";

export type ConnectionStatus = "disconnected" | "connecting" | "live" | "paused" | "error";

interface TranscriptPanelProps {
  lines: TranscriptLine[];
  connectionStatus?: ConnectionStatus;
}

function DoctorAvatar() {
  return (
    <div className={`${styles.avatar} ${styles.avatarDoctor}`} aria-hidden='true'>
      <svg
        className={styles.avatarIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='20'
        height='20'
        viewBox='0 0 20 20'
        fill='none'
      >
        <path
          d='M16.6666 17.5C16.6666 16.337 16.6666 15.7555 16.5231 15.2824C16.1999 14.217 15.3662 13.3834 14.3009 13.0602C13.8277 12.9167 13.2462 12.9167 12.0832 12.9167H7.91659C6.75362 12.9167 6.17213 12.9167 5.69897 13.0602C4.63363 13.3834 3.79995 14.217 3.47678 15.2824C3.33325 15.7555 3.33325 16.337 3.33325 17.5M13.7499 6.25C13.7499 8.32107 12.071 10 9.99992 10C7.92885 10 6.24992 8.32107 6.24992 6.25C6.24992 4.17893 7.92885 2.5 9.99992 2.5C12.071 2.5 13.7499 4.17893 13.7499 6.25Z'
          stroke='#36BFFA'
          strokeWidth='1.5'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
    </div>
  );
}

function PatientAvatar() {
  return (
    <div className={`${styles.avatar} ${styles.avatarPatient}`} aria-hidden='true'>
      <svg
        className={styles.avatarIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='20'
        height='20'
        viewBox='0 0 20 20'
        fill='none'
      >
        <path
          d='M16.6666 17.5C16.6666 16.337 16.6666 15.7555 16.5231 15.2824C16.1999 14.217 15.3662 13.3834 14.3009 13.0602C13.8277 12.9167 13.2462 12.9167 12.0832 12.9167H7.91659C6.75362 12.9167 6.17213 12.9167 5.69897 13.0602C4.63363 13.3834 3.79995 14.217 3.47678 15.2824C3.33325 15.7555 3.33325 16.337 3.33325 17.5M13.7499 6.25C13.7499 8.32107 12.071 10 9.99992 10C7.92885 10 6.24992 8.32107 6.24992 6.25C6.24992 4.17893 7.92885 2.5 9.99992 2.5C12.071 2.5 13.7499 4.17893 13.7499 6.25Z'
          stroke='#3CCB7F'
          strokeWidth='1.5'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
    </div>
  );
}

const speakerName = (who: "doctor" | "patient") => (who === "doctor" ? "Dr. Emily Chen" : "Sarah Johnson");

function StatusBadge({ status }: { status: ConnectionStatus }) {
  const config = {
    live: { dot: "var(--color-success)", text: "Live", className: styles.badgeLive },
    connecting: { dot: "var(--color-recording-paused)", text: "Connecting…", className: styles.badgeConnecting },
    paused: { dot: "var(--color-recording-paused)", text: "Paused", className: styles.badgeConnecting },
    disconnected: { dot: "var(--color-recording-stopped)", text: "Disconnected", className: styles.badgeDisconnected },
    error: { dot: "var(--color-error-fg)", text: "Error", className: styles.badgeError },
  }[status];

  return (
    <div
      className={`${styles.statusBadge} ${config.className}`}
      role='status'
      aria-label={`Connection: ${config.text}`}
    >
      <svg
        className={styles.statusDot}
        xmlns='http://www.w3.org/2000/svg'
        width='8'
        height='8'
        viewBox='0 0 8 8'
        fill='none'
        aria-hidden='true'
      >
        <circle cx='4' cy='4' r='3' fill={config.dot} />
      </svg>
      <span className={styles.statusText}>{config.text}</span>
    </div>
  );
}

export function TranscriptPanel({ lines, connectionStatus = "live" }: TranscriptPanelProps) {
  const bodyRef = useRef<HTMLDivElement>(null);

  const showEmpty = lines.length === 0;

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [lines]);

  const emptyMessages: Record<ConnectionStatus, { icon: string; text: string }> = {
    disconnected: { icon: "mic", text: "Connect to start streaming transcript" },
    connecting: { icon: "loader", text: "Connecting to session…" },
    paused: { icon: "mic", text: "Transcription paused" },
    live: { icon: "mic", text: "Waiting for conversation…" },
    error: { icon: "alert", text: "Connection failed. Please retry." },
  };

  return (
    <section className={styles.content} aria-label='Transcript'>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.titleWrap}>
            <h2 className={styles.title}>Transcript</h2>
          </div>
          <StatusBadge status={connectionStatus} />
        </div>
        <hr className={styles.divider} />
      </header>

      {showEmpty ? (
        <div className={styles.emptyWrapper}>
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon} aria-hidden='true'>
              {connectionStatus === "connecting" ? (
                <svg
                  className={styles.emptySpinner}
                  xmlns='http://www.w3.org/2000/svg'
                  width='24'
                  height='24'
                  viewBox='0 0 24 24'
                  fill='none'
                >
                  <path
                    opacity='0.3'
                    d='M12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2Z'
                    stroke='white'
                    strokeWidth='2'
                    strokeLinecap='round'
                  />
                  <path d='M12 2C17.5228 2 22 6.47715 22 12' stroke='white' strokeWidth='2' strokeLinecap='round' />
                </svg>
              ) : connectionStatus === "error" ? (
                <svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none'>
                  <path
                    d='M12 8V12M12 16H12.01M22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z'
                    stroke='#F04438'
                    strokeWidth='2'
                    strokeLinecap='round'
                    strokeLinejoin='round'
                  />
                </svg>
              ) : (
                <svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none'>
                  <path
                    d='M19 10V12C19 15.866 15.866 19 12 19M5 10V12C5 15.866 8.13401 19 12 19M12 19V22M8 22H16M12 15C10.3431 15 9 13.6569 9 12V5C9 3.34315 10.3431 2 12 2C13.6569 2 15 3.34315 15 5V12C15 13.6569 13.6569 15 12 15Z'
                    stroke='white'
                    strokeWidth='2'
                    strokeLinecap='round'
                    strokeLinejoin='round'
                  />
                </svg>
              )}
            </div>
            <div className={styles.emptyTextWrap}>
              <p className={styles.emptyText}>{emptyMessages[connectionStatus].text}</p>
            </div>
          </div>
        </div>
      ) : (
        <div className={styles.body} ref={bodyRef} role='log' aria-live='polite'>
          {lines.map((line) => (
            <article key={line.id} className={styles.message}>
              {line.who === "doctor" ? <DoctorAvatar /> : <PatientAvatar />}
              <div className={styles.messageContent}>
                <div className={styles.messageHeader}>
                  <span className={styles.speakerName}>{speakerName(line.who)}</span>
                  <time className={styles.messageTime}>{line.timestamp}</time>
                </div>
                <p className={`${styles.bubble} ${line.who === "doctor" ? styles.bubbleDoctor : styles.bubblePatient}`}>
                  {line.text}
                </p>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
