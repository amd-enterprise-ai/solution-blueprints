// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState } from "react";
import type { Alert } from "../../hooks/useTranscript";
import styles from "./CriticalBanner.module.css";

interface CriticalBannerProps {
  alerts: Alert[];
}

export function CriticalBanner({ alerts }: CriticalBannerProps) {
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  const criticalAlert = alerts.find(
    (a) => a.severity === "critical" && a.status === "active" && !dismissedIds.has(a.id),
  );

  if (!criticalAlert) return null;

  return (
    <div className={styles.banner} role='alert'>
      <div className={styles.bannerInner}>
        <div className={styles.contentWrapper}>
          <div className={styles.iconAndText}>
            <div className={styles.iconWrapper} aria-hidden='true'>
              <div className={styles.iconRingOuter} />
              <div className={styles.iconRingInner} />
              <svg
                className={styles.iconSvg}
                xmlns='http://www.w3.org/2000/svg'
                width='28'
                height='28'
                viewBox='0 0 28 28'
                fill='none'
              >
                <path
                  d='M13.9999 9.33331V14M13.9999 18.6666H14.0116M25.6666 14C25.6666 20.4433 20.4432 25.6666 13.9999 25.6666C7.5566 25.6666 2.33325 20.4433 2.33325 14C2.33325 7.55666 7.5566 2.33331 13.9999 2.33331C20.4432 2.33331 25.6666 7.55666 25.6666 14Z'
                  stroke='#F97066'
                  strokeWidth='2'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </div>

            <p className={styles.textContent}>
              <strong className={styles.title}>{criticalAlert.title}</strong>
              <span className={styles.description}>{criticalAlert.evidence}</span>
            </p>
          </div>

          <div className={styles.actions}>
            <button
              className={styles.dismiss}
              onClick={() => setDismissedIds((prev) => new Set(prev).add(criticalAlert.id))}
            >
              <span className={styles.dismissText}>Dismiss</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
