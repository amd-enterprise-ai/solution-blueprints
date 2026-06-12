// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useEffect } from "react";
import styles from "./Header.module.css";

export type RecordingState = "recording" | "paused" | "stopped";

interface HeaderProps {
  recordingState?: RecordingState;
  onRecordingStateChange?: (state: RecordingState) => void;
  onStop?: () => void;
}

export function Header({ recordingState: externalState, onRecordingStateChange, onStop }: HeaderProps = {}) {
  const [internalState, setInternalState] = useState<RecordingState>("recording");
  const state = externalState ?? internalState;

  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    if (state !== "recording") return;
    const interval = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [state]);

  const formatTimer = (totalSeconds: number) => {
    const m = Math.floor(totalSeconds / 60)
      .toString()
      .padStart(2, "0");
    const s = (totalSeconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const handleTogglePause = () => {
    const next = state === "recording" ? "paused" : "recording";
    if (onRecordingStateChange) {
      onRecordingStateChange(next);
    } else {
      setInternalState(next);
    }
  };

  const handleStop = () => {
    if (onStop) {
      onStop();
    }
  };

  const statusLabel = state === "recording" ? "RECORDING" : state === "paused" ? "PAUSED" : "STOPPED";
  const statusClass =
    state === "recording" ? styles.statusRecording : state === "paused" ? styles.statusPaused : styles.statusStopped;

  const dotColor =
    state === "recording"
      ? "var(--color-recording)"
      : state === "paused"
        ? "var(--color-recording-paused)"
        : "var(--color-recording-stopped)";

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <div className={styles.logo}>
          <span className={styles.logoMed}>MED</span>
          <span className={styles.logoAssist}>ASSIST</span>
        </div>
        <div className={styles.sessionInfo}>
          <span className={styles.sessionId}>Session MC-2847</span>
          <span className={styles.sessionDate}>
            {new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </span>
          <div className={styles.personGroup}>
            <span className={styles.personName}>Dr. Emily Chen</span>
            <span className={styles.personDetail}>Cardiology</span>
            <span className={styles.dot} aria-hidden='true'>
              •
            </span>
            <span className={styles.personDetail}>Room 4B</span>
          </div>
          <div className={styles.personGroup}>
            <span className={styles.personName}>Sarah Johnson</span>
            <span className={styles.personDetail}>42 yrs</span>
            <span className={styles.dot} aria-hidden='true'>
              •
            </span>
            <span className={styles.personDetail}>DOB: 03/15/1983</span>
          </div>
        </div>
      </div>

      <div className={styles.right}>
        <div className={styles.recordingStatus}>
          <svg
            className={styles.recordingDot}
            xmlns='http://www.w3.org/2000/svg'
            width='12'
            height='12'
            viewBox='0 0 12 12'
            fill='none'
            aria-hidden='true'
          >
            <circle cx='6' cy='6' r='5' fill={dotColor} />
          </svg>
          <span className={`${styles.recordingLabel} ${statusClass}`}>{statusLabel}</span>
        </div>
        <span className={styles.timer} aria-label={`Timer: ${formatTimer(seconds)}`}>
          {formatTimer(seconds)}
        </span>
        <div className={styles.controls}>
          <button
            className={styles.pauseBtn}
            onClick={state !== "stopped" ? handleTogglePause : undefined}
            disabled={state === "stopped"}
            title={state === "paused" ? "Resume" : "Pause"}
            aria-label={state === "paused" ? "Resume recording" : "Pause recording"}
          >
            {state === "paused" ? (
              <svg
                xmlns='http://www.w3.org/2000/svg'
                width='16'
                height='16'
                viewBox='0 0 16 16'
                fill='none'
                aria-hidden='true'
              >
                <path d='M3 2L13 8L3 14V2Z' fill='white' />
              </svg>
            ) : (
              <svg
                xmlns='http://www.w3.org/2000/svg'
                width='16'
                height='16'
                viewBox='0 0 16 16'
                fill='none'
                aria-hidden='true'
              >
                <path
                  fillRule='evenodd'
                  clipRule='evenodd'
                  d='M4 1C5.10457 1 6 1.89543 6 3V13C6 14.1046 5.10457 15 4 15C2.89543 15 2 14.1046 2 13V3C2 1.89543 2.89543 1 4 1ZM12 1C13.1046 1 14 1.89543 14 3V13C14 14.1046 13.1046 15 12 15C10.8954 15 10 14.1046 10 13V3C10 1.89543 10.8954 1 12 1Z'
                  fill='white'
                />
              </svg>
            )}
          </button>
          <button
            className={styles.stopBtn}
            onClick={state !== "stopped" ? handleStop : undefined}
            disabled={state === "stopped"}
            title='Stop session'
            aria-label='Stop session'
          >
            <svg
              xmlns='http://www.w3.org/2000/svg'
              width='20'
              height='20'
              viewBox='0 0 20 20'
              fill='none'
              aria-hidden='true'
            >
              <path
                d='M2.5 6.5C2.5 5.09987 2.5 4.3998 2.77248 3.86502C3.01217 3.39462 3.39462 3.01217 3.86502 2.77248C4.3998 2.5 5.09987 2.5 6.5 2.5H13.5C14.9001 2.5 15.6002 2.5 16.135 2.77248C16.6054 3.01217 16.9878 3.39462 17.2275 3.86502C17.5 4.3998 17.5 5.09987 17.5 6.5V13.5C17.5 14.9001 17.5 15.6002 17.2275 16.135C16.9878 16.6054 16.6054 16.9878 16.135 17.2275C15.6002 17.5 14.9001 17.5 13.5 17.5H6.5C5.09987 17.5 4.3998 17.5 3.86502 17.2275C3.39462 16.9878 3.01217 16.6054 2.77248 16.135C2.5 15.6002 2.5 14.9001 2.5 13.5V6.5Z'
                fill='#FF692E'
              />
            </svg>
          </button>
        </div>
      </div>
    </header>
  );
}
