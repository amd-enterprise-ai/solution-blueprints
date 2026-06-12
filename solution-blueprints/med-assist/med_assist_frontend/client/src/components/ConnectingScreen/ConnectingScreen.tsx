// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import styles from "./ConnectingScreen.module.css";

export function ConnectingScreen() {
  return (
    <div className={styles.container}>
      <div className={styles.logo}>
        <span className={styles.logoMed}>MED</span>
        <span className={styles.logoAssist}>ASSIST</span>
      </div>
      <div className={styles.spinner} />
      <div className={styles.text}>Connecting to session…</div>
    </div>
  );
}
