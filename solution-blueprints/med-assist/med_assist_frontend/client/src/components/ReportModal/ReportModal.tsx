// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useEffect, useCallback } from "react";
import styles from "./ReportModal.module.css";

interface ReportModalProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onClose: () => void;
}

export function ReportModal({ draft, onDraftChange, onClose }: ReportModalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (!draft) return;
    navigator.clipboard.writeText(draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [draft]);

  const handleExport = useCallback(() => {
    if (!draft) return;
    const blob = new Blob([draft], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "clinical-report.txt";
    a.click();
    URL.revokeObjectURL(url);
  }, [draft]);

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      className={styles.overlay}
      onClick={handleOverlayClick}
      role='dialog'
      aria-modal='true'
      aria-label='Full Clinical Report'
    >
      <aside className={styles.drawer}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <h2 className={styles.title}>Full Clinical Report</h2>
            <div className={styles.saveStatus} role='status'>
              <svg
                xmlns='http://www.w3.org/2000/svg'
                width='16'
                height='16'
                viewBox='0 0 16 16'
                fill='none'
                aria-hidden='true'
              >
                <path
                  d='M5 8L7 10L11 6M14.6667 8C14.6667 11.6819 11.6819 14.6667 8 14.6667C4.3181 14.6667 1.33333 11.6819 1.33333 8C1.33333 4.3181 4.3181 1.33333 8 1.33333C11.6819 1.33333 14.6667 4.3181 14.6667 8Z'
                  stroke='#3CCB7F'
                  strokeWidth='1.25'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
              <span className={styles.saveStatusText}>Saved</span>
            </div>
          </div>
          <nav className={styles.headerActions} aria-label='Report actions'>
            <button className={styles.actionBtn} onClick={handleExport} disabled={!draft}>
              Export
            </button>
            <button className={styles.actionBtn} onClick={handleCopy} disabled={!draft}>
              {copied ? "Copied!" : "Copy"}
            </button>
            <button className={styles.closeBtn} onClick={onClose}>
              Close
            </button>
          </nav>
        </header>

        <div className={styles.body}>
          {!draft ? (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>No report generated yet.</p>
              <p className={styles.emptyDescription}>Generate a report from the console first.</p>
            </div>
          ) : (
            <textarea className={styles.reportTextarea} value={draft} onChange={(e) => onDraftChange(e.target.value)} />
          )}
        </div>
      </aside>
    </div>
  );
}
