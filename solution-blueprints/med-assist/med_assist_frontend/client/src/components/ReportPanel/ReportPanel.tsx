// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useRef } from "react";
import styles from "./ReportPanel.module.css";

interface ReportPanelProps {
  report: string | null;
  draft: string;
  onDraftChange: (value: string) => void;
  loading: boolean;
  onGenerate: () => void;
  onRefresh: () => void;
  hasTranscript: boolean;
  hasNewData: boolean;
}

const sparkleIcon = (
  <svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' aria-hidden='true'>
    <path
      d='M4.5 22V17M4.5 7V2M2 4.5H7M2 19.5H7M13 3L11.2658 7.50886C10.9838 8.24209 10.8428 8.60871 10.6235 8.91709C10.4292 9.1904 10.1904 9.42919 9.91709 9.62353C9.60871 9.84281 9.24209 9.98381 8.50886 10.2658L4 12L8.50886 13.7342C9.24209 14.0162 9.60871 14.1572 9.91709 14.3765C10.1904 14.5708 10.4292 14.8096 10.6235 15.0829C10.8428 15.3913 10.9838 15.7579 11.2658 16.4911L13 21L14.7342 16.4911C15.0162 15.7579 15.1572 15.3913 15.3765 15.0829C15.5708 14.8096 15.8096 14.5708 16.0829 14.3765C16.3913 14.1572 16.7579 14.0162 17.4911 13.7342L22 12L17.4911 10.2658C16.7579 9.98381 16.3913 9.8428 16.0829 9.62353C15.8096 9.42919 15.5708 9.1904 15.3765 8.91709C15.1572 8.60871 15.0162 8.24209 14.7342 7.50886L13 3Z'
      stroke='#ABEFC6'
      strokeWidth='2'
      strokeLinecap='round'
      strokeLinejoin='round'
    />
  </svg>
);

function SpinnerIcon() {
  return (
    <svg
      className={styles.spinner}
      xmlns='http://www.w3.org/2000/svg'
      width='20'
      height='20'
      viewBox='0 0 20 20'
      fill='none'
      aria-hidden='true'
    >
      <path
        opacity='0.3'
        d='M19 10C19 11.1819 18.7672 12.3522 18.3149 13.4442C17.8626 14.5361 17.1997 15.5282 16.364 16.364C15.5282 17.1997 14.5361 17.8626 13.4441 18.3149C12.3522 18.7672 11.1819 19 10 19C8.8181 19 7.64778 18.7672 6.55585 18.3149C5.46392 17.8626 4.47176 17.1997 3.63604 16.364C2.80031 15.5282 2.13738 14.5361 1.68508 13.4441C1.23279 12.3522 1 11.1819 1 10C1 8.8181 1.23279 7.64778 1.68509 6.55585C2.13738 5.46392 2.80031 4.47176 3.63604 3.63604C4.47177 2.80031 5.46392 2.13737 6.55585 1.68508C7.64778 1.23279 8.81811 0.999999 10 1C11.1819 1 12.3522 1.23279 13.4442 1.68509C14.5361 2.13738 15.5282 2.80031 16.364 3.63604C17.1997 4.47177 17.8626 5.46392 18.3149 6.55585C18.7672 7.64778 19 8.81811 19 10L19 10Z'
        stroke='white'
        strokeWidth='2'
        strokeLinecap='round'
        strokeLinejoin='round'
      />
      <path
        d='M10 1C11.1819 1 12.3522 1.23279 13.4442 1.68508C14.5361 2.13738 15.5282 2.80031 16.364 3.63604C17.1997 4.47177 17.8626 5.46392 18.3149 6.55585C18.7672 7.64778 19 8.8181 19 10'
        stroke='white'
        strokeWidth='2'
        strokeLinecap='round'
        strokeLinejoin='round'
      />
    </svg>
  );
}

function RefreshIcon({ color = "#85888E" }: { color?: string }) {
  return (
    <svg
      className={styles.refreshBtnIcon}
      xmlns='http://www.w3.org/2000/svg'
      width='20'
      height='20'
      viewBox='0 0 20 20'
      fill='none'
      aria-hidden='true'
    >
      <path
        d='M1.66675 11.6667C1.66675 11.6667 1.76785 12.3744 4.69678 15.3033C7.62571 18.2322 12.3744 18.2322 15.3034 15.3033C16.3411 14.2656 17.0112 12.9994 17.3136 11.6667M1.66675 11.6667V16.6667M1.66675 11.6667H6.66675M18.3334 8.33333C18.3334 8.33333 18.2323 7.62563 15.3034 4.6967C12.3744 1.76777 7.62571 1.76777 4.69678 4.6967C3.65905 5.73443 2.98899 7.0006 2.6866 8.33333M18.3334 8.33333V3.33333M18.3334 8.33333H13.3334'
        stroke={color}
        strokeWidth='1.66667'
        strokeLinecap='round'
        strokeLinejoin='round'
      />
    </svg>
  );
}

function ConcentricCircles() {
  return (
    <div className={styles.bgPattern} aria-hidden='true'>
      <div className={styles.bgPatternCircles}>
        <div className={`${styles.bgCircle} ${styles.bgCircle1}`} />
        <div className={`${styles.bgCircle} ${styles.bgCircle2}`} />
        <div className={`${styles.bgCircle} ${styles.bgCircle3}`} />
        <div className={`${styles.bgCircle} ${styles.bgCircle4}`} />
        <div className={`${styles.bgCircle} ${styles.bgCircle5}`} />
        <div className={`${styles.bgCircle} ${styles.bgCircle6}`} />
        <div className={`${styles.bgCircle} ${styles.bgCircle7}`} />
      </div>
      <div className={styles.bgPatternMask} />
    </div>
  );
}

export function ReportPanel({
  report,
  draft,
  onDraftChange,
  loading,
  onGenerate,
  onRefresh,
  hasTranscript,
  hasNewData,
}: ReportPanelProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Derive UI state from real props:
  // 1 = no transcript yet, 2 = has transcript, 3 = loading, 4 = report ready, 5 = new data since report
  let effectiveState: 1 | 2 | 3 | 4 | 5;
  if (loading) {
    effectiveState = 3;
  } else if (draft && report) {
    effectiveState = hasNewData ? 5 : 4;
  } else if (hasTranscript) {
    effectiveState = 2;
  } else {
    effectiveState = 1;
  }

  const headerRight = (() => {
    if (effectiveState === 3) {
      return (
        <span className={styles.draftingBadge}>
          <span className={styles.draftingBadgeText}>Drafting…</span>
        </span>
      );
    }
    if (effectiveState >= 4) {
      const isActive = effectiveState === 5;
      return (
        <button
          className={`${styles.refreshBtn} ${isActive ? styles.refreshBtnActive : ""}`}
          onClick={isActive ? onRefresh : undefined}
          aria-disabled={!isActive}
        >
          <RefreshIcon color={isActive ? "#fff" : "#85888E"} />
          <span className={styles.refreshBtnTextWrap}>
            <span className={styles.refreshBtnText}>Refresh</span>
          </span>
        </button>
      );
    }
    return null;
  })();

  // States 4 & 5: Report ready
  if (effectiveState >= 4 && draft) {
    return (
      <div className={styles.content}>
        <header className={styles.header}>
          <div className={styles.headerInner}>
            <div className={styles.titleWrap}>
              <h2 className={styles.title}>Medical Report</h2>
            </div>
            {headerRight}
          </div>
          <hr className={styles.divider} />
        </header>
        <div className={styles.body}>
          <p className={styles.subtitle}>Generated from transcript. Edit as needed.</p>
          <textarea
            ref={textareaRef}
            className={styles.reportTextarea}
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
          />
        </div>
      </div>
    );
  }

  // States 1, 2, 3: Empty / loading
  const isReady = effectiveState >= 2;
  const isLoading = effectiveState === 3;

  let btnClass = styles.generateBtn;
  if (isLoading) btnClass = `${styles.generateBtn} ${styles.generateBtnLoading}`;
  else if (!isReady) btnClass = `${styles.generateBtn} ${styles.generateBtnDisabled}`;

  return (
    <div className={styles.content}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.titleWrap}>
            <h2 className={styles.title}>Medical Report</h2>
          </div>
          {headerRight}
        </div>
        <hr className={styles.divider} />
      </header>
      <div className={styles.emptyWrapper}>
        <div className={styles.emptyState}>
          <div className={styles.emptyInner}>
            <div className={styles.emptyFixed}>
              <div className={styles.iconWithCircles}>
                <ConcentricCircles />
                <div className={styles.emptyIcon}>{sparkleIcon}</div>
              </div>
              <p className={styles.emptyTitle}>{isLoading ? "Generating…" : "Draft report"}</p>
            </div>
            <div className={styles.emptyVariable}>
              <p className={styles.emptyDescription}>
                {isLoading
                  ? "Drafting report from transcript."
                  : "Generate a draft from the transcript when you're ready."}
              </p>
              <div className={styles.emptyActions}>
                <button
                  className={btnClass}
                  onClick={isLoading ? undefined : onGenerate}
                  disabled={!isReady && !isLoading}
                  aria-busy={isLoading}
                >
                  {isLoading && <SpinnerIcon />}
                  <span className={styles.generateBtnText}>{isLoading ? "Generating…" : "Generate report"}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
