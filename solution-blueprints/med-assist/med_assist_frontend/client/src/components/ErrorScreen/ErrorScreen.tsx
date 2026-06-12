// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import styles from "./ErrorScreen.module.css";

interface ErrorScreenProps {
  error: string;
  onRetry: () => void;
  onBack: () => void;
}

export function ErrorScreen({ error, onRetry, onBack }: ErrorScreenProps) {
  return (
    <div className={styles.container}>
      <div className={styles.logo}>
        <span className={styles.logoMed}>MED</span>
        <span className={styles.logoAssist}>ASSIST</span>
      </div>
      <div className={styles.icon}>!</div>
      <div className={styles.title}>Connection failed</div>
      <div className={styles.message}>{error}</div>
      <div className={styles.actions}>
        <button className={styles.backBtn} onClick={onBack}>
          Back
        </button>
        <button className={styles.retryBtn} onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}
