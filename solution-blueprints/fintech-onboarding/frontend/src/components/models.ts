// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

export type LivenessState =
    | "ready"
    | "in-progress"
    | "processing"
    | "passed"
    | "failed"
    | "unavailable"
    | "camera-denied";
