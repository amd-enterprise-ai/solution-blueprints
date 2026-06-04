// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Fragment } from "react";
import styles from "./CustomerProfile.module.css";

interface ProfileSection {
  heading: string;
  rows: { label: string; value: string }[];
}

interface CustomerProfileProps {
  sections?: ProfileSection[];
}

const MOCK_SECTIONS: ProfileSection[] = [
  {
    heading: "Plan",
    rows: [
      { label: "Plan Type", value: "Premium Plus" },
      { label: "Monthly Rate", value: "$79.99/mo" },
      { label: "Billing Cycle", value: "15th of month" },
      { label: "Next Bill", value: "Mar 15, 2026" },
    ],
  },
  {
    heading: "Usage",
    rows: [
      { label: "Data Used", value: "18.5GB / 50GB" },
      { label: "Minutes Used", value: "320 / Unlimited" },
      { label: "Messages", value: "Unlimited" },
      { label: "Hotspot", value: "5.2GB / 15GB" },
    ],
  },
  {
    heading: "Roaming",
    rows: [
      { label: "Region", value: "Europe" },
      { label: "Data Used", value: "2.1GB / 5GB" },
      { label: "Countries", value: "3 visited" },
      { label: "Active Until", value: "Apr 1, 2026" },
    ],
  },
  {
    heading: "Balance",
    rows: [
      { label: "Current Balance", value: "$45.32" },
      { label: "Auto-pay", value: "Enabled" },
      { label: "Payment Method", value: "••••4567" },
      { label: "Last Payment", value: "Feb 15, 2026" },
    ],
  },
];

export function CustomerProfile({ sections = MOCK_SECTIONS }: CustomerProfileProps) {
  return (
    <aside className={styles.card} aria-label='Customer profile'>
      <div className={styles.content}>
        <header className={styles.header}>
          <div className={styles.headerInner}>
            <h2 className={styles.title}>Customer Profile</h2>
          </div>
          <hr className={styles.divider} />
        </header>

        <div className={styles.body}>
          {sections.map((section, i) => (
            <Fragment key={section.heading}>
              {i > 0 && <hr className={styles.divider} />}
              <section className={styles.section}>
                <h3 className={styles.sectionHeading}>{section.heading}</h3>
                <div className={styles.details}>
                  {section.rows.map((row) => (
                    <div className={styles.row} key={row.label}>
                      <span className={styles.label}>{row.label}</span>
                      <span className={styles.value}>{row.value}</span>
                    </div>
                  ))}
                </div>
              </section>
            </Fragment>
          ))}
        </div>
      </div>
    </aside>
  );
}
