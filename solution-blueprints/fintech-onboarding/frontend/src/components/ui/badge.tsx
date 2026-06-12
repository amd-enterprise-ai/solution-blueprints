// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ReactNode } from 'react';

import { cn } from '@/libs/utils'

import styles from './Badge.module.scss'

type PropsType = {
    state?: 'success' | 'error' | 'processing';
    children?: ReactNode;
}

export const Badge = ({ state, children }: PropsType) => {
    return (
        <span
            className={cn(
                styles.badge,
                state === "success" && styles.badgeSuccess,
                state === "error" && styles.badgeError,
                state === "processing" && styles.badgeProcessing,
            )}
        >
            {children}
        </span>
    )
}
