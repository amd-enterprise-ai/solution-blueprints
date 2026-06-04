// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import styles from "./BottomBar.module.css";

interface BottomBarProps {
  toolsOk?: boolean;
  apiConnected?: boolean;
  queueCount?: number;
  isAuthenticated?: boolean;
  onAddRoamingBoost?: () => void;
  onTransferToAgent?: () => void;
  onCreateTicket?: () => void;
}

export function BottomBar({
  toolsOk = true,
  apiConnected = true,
  // queueCount = 3,
  isAuthenticated = false,
  onAddRoamingBoost,
  onTransferToAgent,
  onCreateTicket,
}: BottomBarProps) {
  return (
    <footer className={styles.footer}>
      <hr className={styles.divider} />
      <div className={styles.container}>
        <div className={styles.content}>
          <div className={styles.statusGroup}>
            <div className={styles.statusItem}>
              <svg
                className={styles.statusIcon}
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 12 12"
                fill="none"
                aria-hidden="true"
              >
                <circle cx="6" cy="6" r="5" fill={toolsOk ? "#47CD89" : "#F97066"} />
              </svg>
              <span className={styles.statusText}>{toolsOk ? "Tools OK" : "Tools Error"}</span>
            </div>

            <div className={styles.statusItem}>
              <svg
                className={styles.wifiIcon}
                xmlns="http://www.w3.org/2000/svg"
                width="20"
                height="20"
                viewBox="0 0 20 20"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M10 16.25H10.0084M19.0054 7.25063C16.633 5.07666 13.4714 3.75 9.99995 3.75C6.52849 3.75 3.3669 5.07666 0.994507 7.25063M3.94332 10.2025C5.55842 8.77971 7.67843 7.91667 10 7.91667C12.3216 7.91667 14.4416 8.77971 16.0567 10.2025M13.082 13.1459C12.2327 12.4802 11.1627 12.0833 9.99995 12.0833C8.81962 12.0833 7.73481 12.4923 6.87952 13.1763"
                  stroke="#3CCB7F"
                  strokeWidth="1.25"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className={styles.statusText}>
                {apiConnected ? "API Connected" : "API Disconnected"}
              </span>
            </div>

            {/*<div className={styles.statusItem}>*/}
            {/*  <span className={styles.statusText}>Queue: {queueCount} waiting</span>*/}
            {/*</div>*/}
          </div>

          {isAuthenticated && (
            <div className={styles.actions}>
              <button className={`${styles.btn} ${styles.btnGhost}`} onClick={onAddRoamingBoost} type="button">
                <span className={styles.btnText}>Add roaming boost</span>
              </button>

              <button className={`${styles.btn} ${styles.btnSolid}`} onClick={onTransferToAgent} type="button">
                <svg
                  className={styles.btnIcon}
                  xmlns="http://www.w3.org/2000/svg"
                  width="20"
                  height="20"
                  viewBox="0 0 20 20"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M15.8333 17.5L13.3333 15M13.3333 15L15.8333 12.5M13.3333 15H18.3333M10 12.9167H6.25001C5.08704 12.9167 4.50555 12.9167 4.03239 13.0602C2.96705 13.3834 2.13337 14.217 1.8102 15.2824C1.66667 15.7555 1.66667 16.337 1.66667 17.5M12.0833 6.25C12.0833 8.32107 10.4044 10 8.33334 10C6.26227 10 4.58334 8.32107 4.58334 6.25C4.58334 4.17893 6.26227 2.5 8.33334 2.5C10.4044 2.5 12.0833 4.17893 12.0833 6.25Z"
                    stroke="white"
                    strokeWidth="1.66667"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className={styles.btnText}>Transfer to live agent</span>
              </button>

              <button className={`${styles.btn} ${styles.btnSolid}`} onClick={onCreateTicket} type="button">
                <svg
                  className={styles.btnIcon}
                  xmlns="http://www.w3.org/2000/svg"
                  width="20"
                  height="20"
                  viewBox="0 0 20 20"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M17.5 4.16667L8.33333 4.16667M17.5 15.8333L8.33333 15.8333M17.5 10L8.33333 10M5 4.16667C5 4.85703 4.44036 5.41667 3.75 5.41667C3.05964 5.41667 2.5 4.85703 2.5 4.16667C2.5 3.47632 3.05964 2.91667 3.75 2.91667C4.44036 2.91667 5 3.47632 5 4.16667ZM5 15.8333C5 16.5237 4.44036 17.0833 3.75 17.0833C3.05964 17.0833 2.5 16.5237 2.5 15.8333C2.5 15.143 3.05964 14.5833 3.75 14.5833C4.44036 14.5833 5 15.143 5 15.8333ZM5 10C5 10.6904 4.44036 11.25 3.75 11.25C3.05964 11.25 2.5 10.6904 2.5 10C2.5 9.30965 3.05964 8.75001 3.75 8.75001C4.44036 8.75001 5 9.30965 5 10Z"
                    stroke="white"
                    strokeWidth="1.66667"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className={styles.btnText}>Create ticket</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </footer>
  );
}
