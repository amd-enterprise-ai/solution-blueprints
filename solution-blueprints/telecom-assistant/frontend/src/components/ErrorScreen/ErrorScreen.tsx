// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState } from "react";
import styles from "./ErrorScreen.module.css";

interface ErrorScreenProps {
  message: string;
  onRetry: () => void | Promise<void>;
}

export function ErrorScreen({ message, onRetry }: ErrorScreenProps) {
  const [retrying, setRetrying] = useState(false);

  const handleRetry = async () => {
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className={styles.backdrop}>
      <div className={styles.card}>
        <div className={styles.iconWrap} aria-hidden='true'>
          <div className={styles.ringOuter} />
          <div className={styles.ringInner} />
          <svg
            className={styles.icon}
            xmlns='http://www.w3.org/2000/svg'
            width='24'
            height='24'
            viewBox='0 0 24 24'
            fill='none'
          >
            <path
              d='M12 8V12M12 16H12.01M22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z'
              stroke='#F97066'
              strokeWidth='2'
              strokeLinecap='round'
              strokeLinejoin='round'
            />
          </svg>
        </div>

        <div className={styles.textGroup}>
          <h1 className={styles.title}>Connection failed</h1>
          <p className={styles.description}>
            Unable to connect to the server. Please check your connection and try again.
          </p>
        </div>

        {message && <p className={styles.errorDetail}>{message}</p>}

        <div className={styles.actions}>
          <button className={styles.retryButton} onClick={handleRetry} disabled={retrying}>
            <svg
              className={styles.retryIcon}
              xmlns='http://www.w3.org/2000/svg'
              width='18'
              height='18'
              viewBox='0 0 18 18'
              fill='none'
            >
              <path
                d='M1.5 1.5V6H6M16.5 16.5V12H12M15.365 6.75A6.75 6.75 0 0 0 2.635 6.75L1.5 6M2.635 11.25A6.75 6.75 0 0 0 15.365 11.25L16.5 12'
                stroke='currentColor'
                strokeWidth='1.67'
                strokeLinecap='round'
                strokeLinejoin='round'
              />
            </svg>
            {retrying ? "Retrying…" : "Retry connection"}
          </button>
        </div>
      </div>
    </div>
  );
}
