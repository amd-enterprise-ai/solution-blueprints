// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { ReactNode } from 'react'
import styles from './Card.module.scss'

type PropsType = {
    children?: ReactNode
}

export const Card = ({ children }: PropsType) => {
    return (
        <div className={styles.container}>{children}</div>
    )
}
