// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import styles from "./FlowStepper.module.css";

interface FlowStep {
  number: number;
  label: string;
}

interface FlowStepperProps {
  steps?: FlowStep[];
  activeStep?: number;
}

const MOCK_STEPS: FlowStep[] = [
  { number: 1, label: "Checking roaming usage" },
  { number: 2, label: "Offer roaming boost" },
  { number: 3, label: "Confirm purchase" },
];

export function FlowStepper({ steps = MOCK_STEPS, activeStep = 1 }: FlowStepperProps) {
  return (
    <nav className={styles.stepper} aria-label='Progress'>
      {steps.map((step) => {
        const isActive = step.number <= activeStep;
        return (
          <div className={styles.step} key={step.number}>
            <div className={styles.stepInner}>
              <div className={`${styles.stepIcon} ${isActive ? styles.stepIconActive : styles.stepIconInactive}`}>
                <span
                  className={`${styles.stepNumber} ${isActive ? styles.stepNumberActive : styles.stepNumberInactive}`}
                >
                  {step.number}
                </span>
              </div>
              <span className={`${styles.stepLabel} ${isActive ? styles.stepLabelActive : styles.stepLabelInactive}`}>
                {step.label}
              </span>
              <div className={styles.connector} />
            </div>
          </div>
        );
      })}
    </nav>
  );
}
