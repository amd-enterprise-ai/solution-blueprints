// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Fragment, useState } from "react";
import type { Alert } from "../../hooks/useTranscript";
import styles from "./AlertsPanel.module.css";

interface AlertsPanelProps {
  alerts: Alert[];
  onAcknowledge: (id: string) => void;
  onDismiss: (id: string) => void;
}

type Tab = "active" | "acknowledged";

export function AlertsPanel({ alerts, onAcknowledge, onDismiss }: AlertsPanelProps) {
  const [tab, setTab] = useState<Tab>("active");
  const [showDismissed, setShowDismissed] = useState(false);

  const activeAlerts = alerts.filter((a) => a.status === "active");
  const dismissedAlerts = alerts.filter((a) => a.status === "dismissed");
  const acknowledgedAlerts = alerts.filter((a) => a.status === "acknowledged");

  const activeTabAlerts = showDismissed ? [...activeAlerts, ...dismissedAlerts] : activeAlerts;
  const acknowledgedTabAlerts = acknowledgedAlerts;

  const displayAlerts = tab === "active" ? activeTabAlerts : acknowledgedTabAlerts;
  const emptyMessage = tab === "active" ? "No active alerts" : "No acknowledged alerts";

  return (
    <div className={styles.content}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.titleWrap}>
            <h2 className={styles.title}>Alerts</h2>
          </div>
        </div>
        <hr className={styles.divider} />
      </header>

      {/* Tab switcher */}
      <div className={styles.tabBar}>
        <div className={styles.tabGroup}>
          <button
            className={`${styles.tab} ${tab === "active" ? styles.tabActive : ""}`}
            onClick={() => setTab("active")}
          >
            Active
          </button>
          <button
            className={`${styles.tab} ${tab === "acknowledged" ? styles.tabActive : ""}`}
            onClick={() => setTab("acknowledged")}
          >
            Acknowledged
          </button>
        </div>

        {/* Show dismissed checkbox */}
        <label className={styles.checkboxLabel}>
          <input
            type='checkbox'
            className={styles.checkbox}
            checked={showDismissed}
            onChange={(e) => setShowDismissed(e.target.checked)}
          />
          <span className={styles.checkboxText}>Show dismissed</span>
        </label>

        <hr className={styles.divider} />
      </div>

      {displayAlerts.length === 0 ? (
        <div className={styles.emptyWrapper}>
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon} aria-hidden='true'>
              <svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none'>
                <path
                  d='M12 8V12M12 16H12.01M22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z'
                  stroke='white'
                  strokeWidth='2'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </div>
            <p className={styles.emptyText}>{emptyMessage}</p>
          </div>
        </div>
      ) : (
        <div className={styles.body} role='list' aria-label={`${tab} alerts`}>
          {displayAlerts.map((alert, index) => {
            const isDismissed = alert.status === "dismissed";
            const isAcknowledged = alert.status === "acknowledged";

            return (
              <Fragment key={alert.id}>
                {index > 0 && <hr className={styles.cardDivider} />}
                <article
                  className={`${styles.alertCard} ${isDismissed ? styles.alertCardDismissed : ""}`}
                  role='listitem'
                >
                  <div className={styles.alertContent}>
                    <div className={styles.alertTop}>
                      <span className={`${styles.badge} ${styles[alert.severity]}`}>
                        {alert.severity === "critical" ? "Critical" : alert.severity === "warning" ? "Warning" : "Info"}
                      </span>
                      <time className={styles.alertTime}>{alert.time}</time>
                    </div>
                    <div className={styles.alertTextGroup}>
                      <h3 className={styles.alertTitle}>{alert.title}</h3>
                      <p className={styles.alertEvidence}>{alert.evidence}</p>
                    </div>
                  </div>

                  {/* Active alerts: show action buttons */}
                  {!isDismissed && !isAcknowledged && (
                    <footer className={styles.alertFooter}>
                      <div className={styles.alertActions}>
                        <button className={styles.ackBtn} onClick={() => onAcknowledge(alert.id)}>
                          <span className={styles.ackBtnText}>Acknowledge</span>
                        </button>
                        <button className={styles.dismissBtn} onClick={() => onDismiss(alert.id)}>
                          <span className={styles.dismissBtnText}>Dismiss</span>
                        </button>
                      </div>
                    </footer>
                  )}

                  {/* Acknowledged alerts: show checkmark + time */}
                  {isAcknowledged && (
                    <div className={styles.statusLine}>
                      <svg
                        width='14'
                        height='14'
                        viewBox='0 0 14 14'
                        fill='none'
                        xmlns='http://www.w3.org/2000/svg'
                        aria-hidden='true'
                      >
                        <path
                          d='M11.6667 3.5L5.25 9.91667L2.33333 7'
                          stroke='var(--text-disabled)'
                          strokeWidth='1.5'
                          strokeLinecap='round'
                          strokeLinejoin='round'
                        />
                      </svg>
                      <span className={styles.statusText}>
                        Acknowledged{alert.acknowledgedAt ? ` at ${alert.acknowledgedAt}` : ""}
                      </span>
                    </div>
                  )}

                  {/* Dismissed alerts: show X + "Dismissed" */}
                  {isDismissed && (
                    <div className={styles.statusLine}>
                      <svg
                        width='14'
                        height='14'
                        viewBox='0 0 14 14'
                        fill='none'
                        xmlns='http://www.w3.org/2000/svg'
                        aria-hidden='true'
                      >
                        <path
                          d='M10.5 3.5L3.5 10.5M3.5 3.5L10.5 10.5'
                          stroke='var(--text-disabled)'
                          strokeWidth='1.5'
                          strokeLinecap='round'
                          strokeLinejoin='round'
                        />
                      </svg>
                      <span className={styles.statusText}>Dismissed</span>
                    </div>
                  )}
                </article>
              </Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}
