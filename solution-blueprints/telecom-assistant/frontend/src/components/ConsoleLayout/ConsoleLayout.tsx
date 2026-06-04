// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import type { ReactNode } from "react";
import styles from "./ConsoleLayout.module.css";

interface ConsoleLayoutProps {
  header: ReactNode;
  children: ReactNode;
  bottomBar: ReactNode;
}

export function ConsoleLayout({ header, children, bottomBar }: ConsoleLayoutProps) {
  return (
    <div className={styles.layout}>
      {header}
      <div className={styles.body}>
        <div className={styles.panelsContainer}>
          <div className={styles.panels}>{children}</div>
        </div>
      </div>
      {bottomBar}
    </div>
  );
}
