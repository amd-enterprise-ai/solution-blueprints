// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { cn } from "@/libs/utils";
import styles from "./CameraPreview.module.scss";
import { FaceFrame } from "./svg/FaceFram";

type LivenessState =
    | "ready"
    | "in-progress"
    | "processing"
    | "passed"
    | "failed"
    | "unavailable"
    | "camera-denied";

interface CameraPreviewProps {
  state: LivenessState;
  instruction: string;
  progress: number;
  videoRef: React.RefObject<HTMLVideoElement>;
}

export function CameraPreview({
  state,
  instruction,
  progress,
  videoRef,
}: CameraPreviewProps) {
  const showFace = state !== "ready";
  const isActive = state === "in-progress";

  return (
      <div className={styles.root}>
        {/* Video feed */}
        <video ref={videoRef} autoPlay playsInline muted className={styles.video} />

        {/* Corner brackets */}
        <CornerBracket position="top-left" />
        <CornerBracket position="top-right" />
        <CornerBracket position="bottom-left" />
        <CornerBracket position="bottom-right" />

        {/* Center content */}
        <FaceFrame
          className={cn(
            styles.centerOverlay,
            isActive && styles.faceOvalActive,
          )}
          fill={
            state === 'passed'
              ? '#2EB870'
              : state === "failed" || state === "unavailable" || state === "camera-denied"
                ? '#D74242'
                : undefined
          }
        />

        {/* Bottom instruction bar */}
        {(state === "in-progress" || state === "processing") && (
          <div className={styles.bottomBar}>
            <span className={styles.instruction}>{instruction}</span>
            <div className={styles.progress}>
              <div className={styles.progressTrack}>
                <div className={styles.progressBar} style={{ width: `${progress}%` }} />
              </div>
              <span className={styles.progressLabel}>{Math.round(progress)}%</span>
            </div>
          </div>
        )}
      </div>
  );
}

function CornerBracket({ position }: { position: "top-left" | "top-right" | "bottom-left" | "bottom-right" }) {
  const className =
      position === "top-left"
          ? cn(styles.corner, styles.cornerTopLeft)
          : position === "top-right"
              ? cn(styles.corner, styles.cornerTopRight)
              : position === "bottom-left"
                  ? cn(styles.corner, styles.cornerBottomLeft)
                  : cn(styles.corner, styles.cornerBottomRight);
  return <div className={className} />;
}
