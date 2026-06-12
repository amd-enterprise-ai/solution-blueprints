// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from '@/libs/utils'
import styles from './StateInformation.module.scss'
import { FaceId } from '../svg/FaceId'
import { CheckCircle } from '../svg/CheckCircle'
import { AlertTriangle } from '../svg/AlertTriangle'
import { LivenessState } from '../models'
import { ReactNode } from 'react'

type PropsType = {
    children?: ReactNode;
    customIcon?: ReactNode;
    state: LivenessState;
}

export const StateInformation = ({ state, children, customIcon }: PropsType) => {
    return (
      <div className={cn(
        styles.stateInformation,
        state === 'passed' && styles.stateInformation_success,
        state === 'failed' && styles.stateInformation_failed
      )}>
        {customIcon ?? (
          <>
            {state !== 'passed' && state !== 'failed' && <FaceId />}
            {state === 'passed' && <CheckCircle />}
            {state === 'failed' && <AlertTriangle />}
          </>
        )}
        {children}
      </div>
    )
}
