// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/libs/utils";
import styles from "./VerificationSidebar.module.scss";
import { Connector } from "./svg/Connector";
import { CheckIcon } from "./svg/Check";
import { ShieldTickIcon } from "./svg/ShieldTickIcon";

type StepStatus = "active" | "completed" | "locked";

interface Step {
  label: string;
  status: StepStatus;
}

interface VerificationSidebarProps {
  steps: Step[];
}

function TermsModal({ onClose }: { onClose: () => void }) {
  return createPortal(
      <div
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.45)",
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
      >
        <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#14181f",
              borderRadius: "12px",
              padding: "32px",
              maxWidth: "480px",
              width: "90%",
              maxHeight: "80vh",
              overflowY: "auto",
              boxShadow: "0 8px 40px rgba(0,0,0,0.18)",
              position: "relative",
            }}
        >
          <button
              onClick={onClose}
              style={{
                position: "absolute",
                top: "16px",
                right: "16px",
                background: "none",
                border: "none",
                fontSize: "18px",
                cursor: "pointer",
                color: "#888",
                lineHeight: 1,
              }}
          >
            ✕
          </button>

          <h2 style={{ marginTop: 0, marginBottom: "20px", fontSize: "18px", fontWeight: 600 }}>
            Terms & Privacy
          </h2>

          <h3 style={{ fontSize: "14px", fontWeight: 600, marginBottom: "6px" }}>Terms of Service</h3>
          <p style={{ fontSize: "13px", color: "#e0e6eb", lineHeight: 1.6, marginBottom: "16px" }}>
            By using this verification service, you agree to provide accurate and truthful information.
            Any false or misleading details may result in suspension of your account.
          </p>

          <h3 style={{ fontSize: "14px", fontWeight: 600, marginBottom: "6px" }}>Data Collection</h3>
          <p style={{ fontSize: "13px", color: "#e0e6eb", lineHeight: 1.6, marginBottom: "16px" }}>
            We collect personal information necessary to complete identity verification, including your
            name, date of birth, and government-issued ID details. All data is processed securely.
          </p>

          <h3 style={{ fontSize: "14px", fontWeight: 600, marginBottom: "6px" }}>Data Usage</h3>
          <p style={{ fontSize: "13px", color: "#e0e6eb", lineHeight: 1.6, marginBottom: "16px" }}>
            Your data is used solely for verification purposes and will not be sold or shared with
            third parties without your explicit consent, except where required by law.
          </p>

          <h3 style={{ fontSize: "14px", fontWeight: 600, marginBottom: "6px" }}>Privacy</h3>
          <p style={{ fontSize: "13px", color: "#e0e6eb", lineHeight: 1.6, marginBottom: 0 }}>
            All data transmissions are encrypted using industry-standard TLS protocols. You may
            request deletion of your data subject to applicable legal obligations.
          </p>
        </div>
      </div>,
      document.body
  );
}

export function VerificationSidebar({ steps }: VerificationSidebarProps) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  function handleTermsClick(e: React.MouseEvent<HTMLAnchorElement>) {
    e.preventDefault();
    setIsModalOpen(true);
  }

  function handleModalClose() {
    setIsModalOpen(false);
  }

  return (
      <aside className={styles.sidebar}>
        <div className={styles.header}>
          <img src="/assets/logo.png" />
        </div>

        <nav className={styles.nav}>
          <ol className={styles.stepsList}>
            {steps.map((step, i) => (
                <li key={step.label} className={cn(
                    styles.stepItem,
                    (step.status === "active" || step.status === "completed") && styles.stepItem_active
                )}>
                  <div className={styles.connectorWrapper}>
                    <div
                        className={cn(
                            styles.iconCircle,
                            step.status === "completed"
                                ? styles.iconCircleCompleted
                                : step.status === "active"
                                    ? styles.iconCircleActive
                                    : undefined,
                        )}
                    >
                      {step.status === "completed" ? <CheckIcon /> : i + 1}
                    </div>
                    {i < steps.length - 1 && <Connector />}
                  </div>
                  <div className={styles.stepLabelWrapper}>
                <span
                    className={cn(
                        styles.stepLabel,
                        step.status === "active" || step.status === "completed"
                            ? styles.stepLabelActive
                            : undefined
                    )}
                >
                  <div className={styles.stepLabel_title}>{step.label}</div>
                  <div className={styles.stepLabel_step}>Step {i + 1}</div>
                </span>
                  </div>
                </li>
            ))}
          </ol>
        </nav>

        <div className={styles.footer}>
          <a href="#" className={styles.footerLink} onClick={handleTermsClick}>
            <ShieldTickIcon />
            Terms & Privacy
          </a>
        </div>

        {isModalOpen && <TermsModal onClose={handleModalClose} />}
      </aside>
  );
}
