// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ReactNode } from 'react';
import styles from './Header.module.scss';

type PropsType = {
    title: string;
    description: string;
    children?: ReactNode;
}

export const Header = ({
    children,
    description,
    title
}: PropsType) => {
    return (
        <div className={styles.header}>
          <div className={styles.headerRow}>
            <h2 className={styles.title}>{title}</h2>
          </div>
          <p className={styles.description}>
            {description}
          </p>
          {children}
        </div>
    )
}
