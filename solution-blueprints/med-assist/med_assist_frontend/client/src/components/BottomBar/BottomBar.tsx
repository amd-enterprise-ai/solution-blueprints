// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import styles from "./BottomBar.module.css";

interface BottomBarProps {
  onStopSession: () => void;
  onSaveDraft?: () => void;
  onViewReport: () => void;
  saveStatus?: "saved" | "saving" | "failed";
}

export function BottomBar({ onStopSession, onSaveDraft, onViewReport, saveStatus = "saved" }: BottomBarProps) {
  const statusConfig = {
    saved: { icon: "check", text: "All changes saved", color: "var(--color-success-check)" },
    saving: { icon: "loader", text: "Saving…", color: "var(--text-tertiary)" },
    failed: { icon: "alert", text: "Save failed — Retry", color: "var(--color-error-fg)" },
  }[saveStatus];

  return (
    <nav className={styles.footer} aria-label='Session controls'>
      <div className={styles.container}>
        <div className={styles.bar}>
          <div className={styles.saveStatus} role='status' aria-label={statusConfig.text}>
            {saveStatus === "saved" && (
              <svg
                xmlns='http://www.w3.org/2000/svg'
                width='20'
                height='20'
                viewBox='0 0 20 20'
                fill='none'
                aria-hidden='true'
              >
                <path
                  d='M6.25008 10L8.75008 12.5L13.7501 7.5M18.3334 10C18.3334 14.6024 14.6025 18.3333 10.0001 18.3333C5.39771 18.3333 1.66675 14.6024 1.66675 10C1.66675 5.39762 5.39771 1.66666 10.0001 1.66666C14.6025 1.66666 18.3334 5.39762 18.3334 10Z'
                  stroke='#3CCB7F'
                  strokeWidth='1.25'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            )}
            {saveStatus === "saving" && (
              <svg
                className={styles.savingSpinner}
                xmlns='http://www.w3.org/2000/svg'
                width='20'
                height='20'
                viewBox='0 0 20 20'
                fill='none'
                aria-hidden='true'
              >
                <path
                  opacity='0.3'
                  d='M10 2C5.58172 2 2 5.58172 2 10C2 14.4183 5.58172 18 10 18C14.4183 18 18 14.4183 18 10C18 5.58172 14.4183 2 10 2Z'
                  stroke='#94979C'
                  strokeWidth='1.5'
                  strokeLinecap='round'
                />
                <path d='M10 2C14.4183 2 18 5.58172 18 10' stroke='#94979C' strokeWidth='1.5' strokeLinecap='round' />
              </svg>
            )}
            {saveStatus === "failed" && (
              <svg
                xmlns='http://www.w3.org/2000/svg'
                width='20'
                height='20'
                viewBox='0 0 20 20'
                fill='none'
                aria-hidden='true'
              >
                <path
                  d='M10 6.66666V10M10 13.3333H10.0083M18.3334 10C18.3334 14.6024 14.6025 18.3333 10.0001 18.3333C5.39771 18.3333 1.66675 14.6024 1.66675 10C1.66675 5.39762 5.39771 1.66666 10.0001 1.66666C14.6025 1.66666 18.3334 5.39762 18.3334 10Z'
                  stroke='#F97066'
                  strokeWidth='1.25'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            )}
            <span
              className={styles.saveText}
              style={{ color: saveStatus === "failed" ? "var(--color-error-fg)" : undefined }}
            >
              {statusConfig.text}
            </span>
          </div>
          <p className={styles.disclaimer}>
            For demonstration purposes only. Not a substitute for professional medical advice.
          </p>
          <div className={styles.actions}>
            <button className={styles.stopBtn} onClick={onStopSession}>
              Stop session
            </button>
            <button className={styles.saveBtn} onClick={onSaveDraft}>
              Save draft
            </button>
            <button className={styles.viewBtn} onClick={onViewReport}>
              View full report
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
