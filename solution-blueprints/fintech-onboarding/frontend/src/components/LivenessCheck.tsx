// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useEffect, useRef, useCallback } from "react";
import { ArrowRight, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { CameraPreview } from "@/components/CameraPreview";
import { CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/libs/utils";
import { BACKEND_URL } from "@/constants";
import styles from "./LivenessCheck.module.scss";
import { FaceId } from "./svg/FaceId";
import { CheckCircle } from "./svg/CheckCircle";
import { Camera } from "./svg/Camera";
import { ChevronDown } from "./svg/ChevronDown";
import { LivenessState } from "./models";
import { StateInformation } from "./ui/StateInformation";
import { Badge } from "./ui/badge"
import { Card } from "./ui/card";
import { Header } from "./ui/Header";

const CHALLENGES = [
  { key: "straight", label: "Look straight at the camera" },
  { key: "right", label: "Turn your head to your right" },
  { key: "left", label: "Turn your head to your left" },
  { key: "blink", label: "Blink a few times" },
] as const;

const DETAILS_CHALLENGES = [
  { key: "right", label: "Turn your head to your right" },
  { key: "left", label: "Turn your head to your left" },
  { key: "blink", label: "Blink a few times" },
] as const;

interface LivenessCheckProps {
  onStateChange?: (state: LivenessState) => void;
  onLivenessSuccess?: (embedding: number[]) => void;
  onContinue?: () => void;
}

interface LivenessDetails {
  yaw_left_detected: boolean;
  yaw_right_detected: boolean;
  blink_detected: boolean;
  final_state: number;
  challenge_passed: boolean;
}

interface LivenessResponse {
  success: boolean;
  reason?: string;
  embedding?: number[] | null;
  liveness_details?: LivenessDetails;
}

const ReadyToStart = () => <><b>Ready to start</b> Ensure good lighting and keep your face centered in the frame.</>
const FollowTheInstructions = () => <><b>Follow the instructions.</b> Keep your face centered.</>
const CheckingLieness = () => <b>Checking liveness (usually ~10s).</b>
const LivenessConfirmed = () => <><b>Liveness confirmed.</b> You may continue.</>
const LivenessFailed = () => <><b>We couldn’t confirm liveness.</b> Please try again.</>
const ServiceUnavailable = () => <><b>We can’t reach the verification service.</b> Retry in a moment.</>

export function LivenessCheck({
                                onStateChange,
                                onLivenessSuccess,
                                onContinue,
                              }: LivenessCheckProps) {
  const [state, setState] = useState<LivenessState>("ready");
  const [progress, setProgress] = useState(0);
  const [challengeIndex, setChallengeIndex] = useState(0);
  const [completedChallenges, setCompletedChallenges] = useState<string[]>([]);
  const [frames, setFrames] = useState<Blob[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [serverChallengeStatus, setServerChallengeStatus] = useState({
    right: false,
    left: false,
    blink: false
  });

  const [responseReceived, setResponseReceived] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(document.createElement("canvas"));
  const streamRef = useRef<MediaStream | null>(null);
  const framesRef = useRef<Blob[]>([]);

  const frameIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const LIVENESS_DURATION = 10000;
  const FRAME_INTERVAL = 700;
  const MIN_FRAMES_REQUIRED = 5;

  const initializeCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      });

      if (!videoRef.current) throw new Error("Video ref missing");

      videoRef.current.srcObject = stream;
      streamRef.current = stream;

      await new Promise<void>((resolve, reject) => {
        const checkReady = () => {
          if (
              videoRef.current &&
              videoRef.current.readyState >= 4 &&
              videoRef.current.videoWidth > 0 &&
              videoRef.current.videoHeight > 0
          ) {
            videoRef.current.removeEventListener("canplaythrough", checkReady);
            resolve();
          }
        };

        videoRef.current.addEventListener("canplaythrough", checkReady, { once: true });

        setTimeout(() => {
          videoRef.current?.removeEventListener("canplaythrough", checkReady);
          reject(new Error("Timeout waiting for video"));
        }, 12000);
      });
    } catch (err: any) {
      console.error("Camera init failed:", err);
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setErrorMsg("Camera access denied. Please allow access in browser settings.");
        setState("camera-denied");
      } else {
        setErrorMsg("Failed to start camera.");
        setState("unavailable");
      }
    }
  }, []);

  useEffect(() => {
    initializeCamera();

    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
      if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
    };
  }, [initializeCamera]);

  const captureFrame = useCallback(() => {
    if (!videoRef.current || videoRef.current.videoWidth === 0) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob((blob) => {
      if (blob) {
        framesRef.current.push(blob);
        setFrames([...framesRef.current]);
      }
    }, "image/jpeg", 0.85);
  }, []);

  const startLiveness = async () => {
    if (state === "camera-denied" || state === "unavailable") {
      setErrorMsg("Camera access is required. Please allow it in your browser.");
      return;
    }

    if (!videoRef.current || videoRef.current.videoWidth === 0) {
      setErrorMsg("Camera is not ready yet. Please wait or reload.");
      setState("unavailable");
      return;
    }

    setErrorMsg(null);
    framesRef.current = [];
    setFrames([]);
    setProgress(0);
    setChallengeIndex(0);
    setCompletedChallenges([]);
    setServerChallengeStatus({
      right: false,
      left: false,
      blink: false
    });
    setResponseReceived(false);
    setState("in-progress");

    await new Promise((resolve) => setTimeout(resolve, 1500));

    frameIntervalRef.current = setInterval(captureFrame, FRAME_INTERVAL);

    const startTime = Date.now();

    progressIntervalRef.current = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const percent = Math.min((elapsed / LIVENESS_DURATION) * 100, 100);
      setProgress(percent);

      setChallengeIndex(prevIndex => {
        const targetIndex = Math.min(Math.floor(percent / 25), CHALLENGES.length - 1);
        if (targetIndex > prevIndex) {
          setCompletedChallenges(prev => [
            ...new Set([...prev, CHALLENGES[targetIndex - 1].key]),
          ]);
          return targetIndex;
        }
        return prevIndex;
      });

      if (percent >= 100) {
        if (frameIntervalRef.current) clearInterval(frameIntervalRef.current);
        if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
        setState("processing");
        sendToBackend();
      }
    }, 80);
  };

  const sendToBackend = async () => {
    if (framesRef.current.length < MIN_FRAMES_REQUIRED) {
      setErrorMsg(`Only ${framesRef.current.length} frames captured. Please try again.`);
      setState("failed");
      return;
    }

    const formData = new FormData();
    framesRef.current.forEach((blob, i) => {
      formData.append("files", blob, `frame_${i + 1}.jpg`);
    });

    try {
      const res = await fetch(`${BACKEND_URL}/extract_live_embedding`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(`Server responded with status ${res.status}`);

      const data: LivenessResponse = await res.json();

      if (data.liveness_details) {
        setServerChallengeStatus({
          right: data.liveness_details.yaw_right_detected,
          left: data.liveness_details.yaw_left_detected,
          blink: data.liveness_details.blink_detected
        });
      }

      setResponseReceived(true);

      if (data.success && Array.isArray(data.embedding)) {
        onLivenessSuccess?.(data.embedding);
        setCompletedChallenges(CHALLENGES.map((c) => c.key));
        setState("passed");
      } else {
        setErrorMsg(data.reason || "Liveness verification failed");
        setState("failed");
      }
    } catch (err) {
      console.error("Backend request failed:", err);
      setErrorMsg("Failed to connect to the server");
      setState("failed");
      setResponseReceived(true);
    }
  };

  const reset = async () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    framesRef.current = [];
    setFrames([]);
    setChallengeIndex(0);
    setCompletedChallenges([]);
    setState("ready");
    setErrorMsg(null);

    await initializeCamera();
  };

  const stateInfo =
      state === "ready"
          ? <ReadyToStart />
          : state === "in-progress"
              ? <FollowTheInstructions />
              : state === "processing"
                  ? <CheckingLieness />
                  : state === "passed"
                      ? <LivenessConfirmed />
                      : state === "failed"
                          ? <LivenessFailed />
                          : <ServiceUnavailable />

  const instruction =
      state === "ready"
          ? "Position your face inside the oval"
          : state === "in-progress"
              ? CHALLENGES[challengeIndex]?.label ?? "Follow the instructions"
              : state === "processing"
                  ? "Processing…"
                  : state === "passed"
                      ? "Liveness check passed"
                      : state === "failed"
                          ? "Liveness verification failed"
                          : "Service unavailable";

  const badgeLabel =
      state === "ready"
          ? "Ready"
          : state === "in-progress"
              ? "In progress"
              : state === "processing"
                  ? "Processing"
                  : state === "passed"
                      ? "Passed"
                      : state === "failed"
                          ? "Failed"
                          : "Error";

  return (
      <Card>
        {/* Header */}
        <Header
            title="Step 1. Confirm liveness"
            description="Complete a brief liveness check to verify your identity"
        >
          <Badge
              state={
                state === "passed"
                    ? "success"
                    : (state === "failed" || state === "unavailable" || errorMsg)
                        ? "error"
                        : state === "processing"
                            ? "processing"
                            : undefined
              }
          >
            {badgeLabel}
          </Badge>
        </Header>

        {/* Camera */}
        <CameraPreview state={state} instruction={instruction} progress={progress} videoRef={videoRef} />

        <StateInformation state={errorMsg ? "failed" : state}>
          {errorMsg || stateInfo}
        </StateInformation>

        {/* Actions */}
        <Collapsible className={styles.collapsibleRoot}>
          <div className={styles.actions}>
            <CollapsibleTrigger className={styles.collapsibleTrigger}>
              <ChevronDown />
              <span>Show details</span>
            </CollapsibleTrigger>
            <div className={styles.actions_buttons}>
              {(state === "failed" || state === "unavailable") && (
                  <Button variant="outline" onClick={reset}>
                    <RotateCcw className="w-4 h-4" />
                    Reset
                  </Button>
              )}

              {(state === "ready" || state === "failed" || state === "unavailable") && (
                  <Button onClick={startLiveness}>
                    <Camera />
                    {state === "ready" ? "Start liveness check" : "Retry"}
                  </Button>
              )}

              {state === "passed" && onContinue && (
                  <div className={styles.primaryActionRight}>
                    <Button onClick={onContinue} disabled={state !== "passed"}>
                      Continue
                      <ArrowRight className="w-4 h-4" />
                    </Button>
                  </div>
              )}
            </div>
          </div>
          <CollapsibleContent className={styles.collapsibleContent}>
            <div className={styles.challengesCard}>
              <div className={styles.challengesList}>
                {responseReceived ? (
                    DETAILS_CHALLENGES.map((challenge) => {
                      let isDone = false;

                      if (challenge.key === "right") {
                        isDone = serverChallengeStatus.right;
                      } else if (challenge.key === "left") {
                        isDone = serverChallengeStatus.left;
                      } else if (challenge.key === "blink") {
                        isDone = serverChallengeStatus.blink;
                      }

                      return (
                          <div key={challenge.key} className={styles.challengeRow}>
                            {isDone ? (
                                <CheckCircle2 className={styles.challengeIconDone} />
                            ) : (
                                <XCircle className={styles.challengeIconPending} />
                            )}
                            <span
                                className={cn(
                                    styles.challengeLabel,
                                    isDone ? styles.challengeLabelDone : styles.challengeLabelPending,
                                )}
                            >
                          {challenge.label}
                        </span>
                          </div>
                      );
                    })
                ) : (
                    <div style={{ minHeight: '100px' }}></div>
                )}
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </Card>
  );
}
