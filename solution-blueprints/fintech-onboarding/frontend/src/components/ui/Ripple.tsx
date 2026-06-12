// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import styles from './Ripple.module.scss';

export default function Ripple() {
  const count = 8;
  const duration = 4;

  return (
    <>
        {Array.from({ length: count }).map((_, i) => (
            <span
                key={i}
                className={styles.circle}
                style={{
                animationDelay: `-${(duration / count) * i}s`
                }}
            />
        ))}
    </>
  );
}
