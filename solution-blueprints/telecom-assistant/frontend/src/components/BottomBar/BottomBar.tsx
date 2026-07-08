// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState } from "react";
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
                            isAuthenticated = false,
                            onAddRoamingBoost,
                            onTransferToAgent,
                            onCreateTicket,
                          }: BottomBarProps) {
  const [uploadResult, setUploadResult] = useState<string>("");
  const [isUploading, setIsUploading] = useState(false);

  const handleUploadPDF = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".pdf";

    input.onchange = async (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file) return;

      setIsUploading(true);
      setUploadResult("Uploading...");

      try {
        const formdata = new FormData();
        formdata.append("file", file);
        formdata.append("force", "false");
        formdata.append("append", "true");

        const response = await fetch("/agent/ingest/pdf", {
          method: "POST",
          body: formdata,
        });

        const result = await response.json();

        if (result?.status === "ok") {
          setUploadResult("Success");
        } else {
          setUploadResult("Unexpected response");
        }
      } catch (error) {
        setUploadResult("Error");
      } finally {
        setIsUploading(false);
      }
    };

    input.click();
  };

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
                >
                  <circle cx="6" cy="6" r="5" fill={toolsOk ? "#47CD89" : "#F97066"} />
                </svg>
                <span className={styles.statusText}>
                {toolsOk ? "Tools OK" : "Tools Error"}
              </span>
              </div>

              <div className={styles.statusItem}>
                <svg
                    className={styles.wifiIcon}
                    xmlns="http://www.w3.org/2000/svg"
                    width="20"
                    height="20"
                    viewBox="0 0 20 20"
                    fill="none"
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
            </div>

            <div className={styles.actions}>
              {isAuthenticated && (
                  <>
                    <button className={`${styles.btn} ${styles.btnGhost}`} onClick={onAddRoamingBoost}>
                      <span className={styles.btnText}>Add roaming boost</span>
                    </button>

                    <button className={`${styles.btn} ${styles.btnSolid}`} onClick={onTransferToAgent}>
                      <span className={styles.btnText}>Transfer to live agent</span>
                    </button>

                    <button className={`${styles.btn} ${styles.btnSolid}`} onClick={onCreateTicket}>
                      <span className={styles.btnText}>Create ticket</span>
                    </button>
                  </>
              )}

              <span className={styles.uploadHint}>
                Knowledge base updates online. Please upload PDFs with documentation and troubleshooting guides.
              </span>

              <button
                  className={`${styles.btn} ${styles.btnPrimary}`}
                  onClick={handleUploadPDF}
                  disabled={isUploading}
              >
                {isUploading ? (
                    <span className={styles.loader} />
                ) : (
                    <span className={styles.btnText}>Upload PDF</span>
                )}
              </button>

              {uploadResult && (
                  <span className={styles.resultInline}>
                {uploadResult}
              </span>
              )}
            </div>
          </div>
        </div>
      </footer>
  );
}
