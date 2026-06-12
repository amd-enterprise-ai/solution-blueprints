// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useEffect, useCallback } from "react";
import {
  ArrowRight,
  RotateCcw,
  RefreshCw,
  ChevronDown,
  CheckCircle2,
  XCircle,
  Info,
  Loader2,
  ShieldCheck,
  ShieldX,
  ScanFace,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/libs/utils";
import { BACKEND_URL } from "@/constants";
import styles from "./VerifyMatch.module.scss";
import { Card } from "./ui/card";
import { Header } from "./ui/Header";
import { Badge } from "./ui/badge";
import { CheckCircle } from "./svg/CheckCircle";
import { Camera } from "./svg/Camera";
import { StateInformation } from "./ui/StateInformation";
import SpinnerIcon from "./svg/SpinnerIcon";
import Ripple from "./ui/Ripple";
import { CheckIcon } from "./svg/Check";
import { Check24Icon } from "./svg/Check24Icon";
import { AlertTriangle } from "./svg/AlertTriangle";

type MatchState = "not-run" | "processing" | "passed" | "failed" | "unavailable";

interface VerifyMatchProps {
  onStateChange?: (state: MatchState) => void;
  onRetakeSelfie?: () => void;
  onFinish?: () => void;
  liveEmbedding: number[] | null;     // from LivenessCheck
  docEmbedding: number[] | null;      // from AuthenticateID
}

// Response interface from backend
interface CompareFacesResponse {
  match: boolean;
  similarity: number;
  threshold: number;
  note?: string;
}

export function VerifyMatch({
                              onStateChange,
                              onRetakeSelfie,
                              onFinish,
                              liveEmbedding,
                              docEmbedding,
                            }: VerifyMatchProps) {
  const [state, setState] = useState<MatchState>("not-run");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [matchScore, setMatchScore] = useState<number | null>(null);
  const [matchThreshold, setMatchThreshold] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [responseReceived, setResponseReceived] = useState(false);

  const updateState = useCallback(
      (s: MatchState) => {
        setState(s);
        onStateChange?.(s);
      },
      [onStateChange]
  );

  const handleRunMatch = async () => {
    if (!liveEmbedding || !docEmbedding) {
      setErrorMsg("Embeddings are missing. Please complete previous steps.");
      updateState("unavailable");
      return;
    }

    updateState("processing");
    setErrorMsg(null);
    setMatchScore(null);
    setMatchThreshold(null);
    setResponseReceived(false);

    try {
      const res = await fetch(`${BACKEND_URL}/compare_faces`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          live_embedding: liveEmbedding,
          doc_embedding: docEmbedding,
        }),
      });

      if (!res.ok) {
        throw new Error(`Server responded with status ${res.status}`);
      }

      const data: CompareFacesResponse = await res.json();

      // Convert similarity to percentage and round to 1 decimal place
      const similarityPercentage = data.similarity * 100;
      const roundedScore = Math.round(similarityPercentage * 10) / 10;

      setMatchScore(roundedScore);
      setMatchThreshold(data.threshold * 100); // Convert threshold to percentage
      setResponseReceived(true);

      if (data.match) {
        updateState("passed");
      } else {
        updateState("failed");
      }
    } catch (err: any) {
      console.error("Face comparison error:", err);
      setErrorMsg("Failed to compare faces. Please try again.");
      updateState("unavailable");
      setResponseReceived(true); // Still mark as received to show details with error
    }
  };

  const badgeLabel =
      state === "not-run"
          ? "Ready"
          : state === "processing"
              ? "Processing"
              : state === "passed"
                  ? "Match"
                  : state === "failed"
                      ? "No match"
                      : "Error";

  // Format score for display
  const formattedScore = matchScore !== null ? matchScore.toFixed(1) : "—";

  // Determine if details should be shown (only after response received)
  const showDetails = responseReceived && (state === "passed" || state === "failed" || state === "unavailable");

  return (
      <Card>
        {/* Header */}
        <Header
            title="Step 3. Verify match"
            description="Comparing your selfie to your ID photo"
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

        {/* Result card */}
        <div className={styles.resultCard}>
          {/* Visual header */}
          <div
              className={cn(
                  styles.resultHeader,
                  state === "passed" && styles.resultHeaderSuccess,
                  state === "failed" && styles.resultHeaderError,
              )}
          >
            {state === "not-run" && (
                <div className={styles.resultInner}>
                  <ScanFace className={styles.mutedIcon} />
                  <span className={styles.resultDesc}>Ready to compare faces</span>
                </div>
            )}
            {state === "processing" && (
                <div className={styles.resultInner}>
                  <div className={styles.rippleWrapper}>
                    <Ripple />
                    <div className={styles.processingIcon}>
                      <SpinnerIcon />
                    </div>
                  </div>
                  <div className={styles.processingText}>
                    <div className={styles.resultTitle}>Processing</div>
                    <span className={styles.resultDesc}>Comparing biometric data...</span>
                  </div>
                </div>
            )}
            {state === "passed" && (
                <div className={styles.resultInner}>
                  <div className={cn(styles.processingIcon, styles.processingIcon_success)}>
                    <Check24Icon />
                  </div>
                  <div className={styles.processingText}>
                    <div className={styles.resultTitle}>Identity Verified</div>
                    <div className={styles.resultDesc}>
                      Face match score: {formattedScore}%
                    </div>
                  </div>
                </div>
            )}
            {state === "failed" && (
                <div className={styles.resultInner}>
                  <div className={cn(styles.processingIcon, styles.processingIcon_failure)}>
                    <AlertTriangle stroke="#fff" />
                  </div>
                  <div className={styles.processingText}>
                    <div className={styles.resultTitle}>No Match</div>
                    <div className={styles.resultDesc}>Selfie does not match ID photo</div>
                  </div>
                </div>
            )}
            {state === "unavailable" && (
                <div className={styles.resultInner}>
                  <div className={cn(styles.processingIcon, styles.processingIcon_failure)}>
                    <AlertTriangle stroke="#fff" />
                  </div>
                  <div className={styles.processingText}>
                    <div className={styles.resultDesc}>Service unavailable</div>
                  </div>
                </div>
            )}
          </div>

          {/* Score bar (passed only) */}
          {state === "passed" && matchScore !== null && (
              <div className={styles.scoreSection}>
                <div className={styles.scoreRow}>
                  <span className={styles.scoreLabel}>Face match confidence</span>
                  <span className={styles.scoreValue}>{formattedScore}%</span>
                </div>
                <div className={styles.scoreBarOuter}>
                  <div
                      className={styles.scoreBarInner}
                      style={{ width: `${matchScore}%` }}
                  />
                </div>
              </div>
          )}
        </div>

        {/* Status message */}
        {errorMsg && (
            <StateInformation state="failed">
              {errorMsg}
            </StateInformation>
        )}

        {!errorMsg && (
            <>
              <StateInformation
                  state={
                    state === "passed"
                        ? "passed"
                        : state === "failed"
                            ? "failed"
                            : undefined
                  }
              >
                {state === "not-run" && <span><b>Ready to run face match</b> Click the button below to compare your selfie with the ID photo.</span>}
                {state === "processing" && <span><b>Comparing selfie to ID photo…</b> This usually takes a few seconds.</span>}
                {state === "passed" && <span><b>Identity verified</b> Selfie matches ID photo. You may finish the verification.</span>}
                {state === "failed" && <span><b>ID Face match failed</b> The selfie does not match the ID photo. Please retake the selfie.</span>}
                {state === "unavailable" && <span><b>We can't reach the verification service</b> Please retry in a moment.</span>}
              </StateInformation>
            </>
        )}

        {/* Actions */}
        <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen} className={styles.detailsRoot}>
          <div className={styles.actions}>
            <CollapsibleTrigger className={styles.detailsTrigger}>
              <ChevronDown
                  className={cn(styles.detailsIcon, detailsOpen && styles.detailsIconOpen)}
              />
              Show details
            </CollapsibleTrigger>
            <div className={styles.actions_buttons}>
              {state === "not-run" && (
                  <Button onClick={handleRunMatch}>
                    <ScanFace className="w-4 h-4" />
                    Run match
                  </Button>
              )}

              {state === "failed" && (
                  <>
                    <Button variant="outline" onClick={handleRunMatch}>
                      <RefreshCw className="w-4 h-4" />
                      Retry match
                    </Button>
                    <Button onClick={onRetakeSelfie}>
                      <Camera />
                      Retake selfie
                    </Button>
                  </>
              )}

              {state === "unavailable" && (
                  <>
                    <Button onClick={handleRunMatch}>
                      <RotateCcw className="w-4 h-4" />
                      Retry
                    </Button>
                    <Button variant="ghost" onClick={() => window.location.reload()}>
                      Reload page
                    </Button>
                  </>
              )}

              {state === "passed" && onFinish && (
                  <div className={styles.finishRight}>
                    <Button onClick={onFinish}>
                      <CheckCircle stroke="white" />
                      Finish
                    </Button>
                  </div>
              )}
            </div>
          </div>
          <CollapsibleContent className={styles.detailsContent}>
            <div className={styles.detailsCard}>
              {showDetails ? (
                  <div className={styles.detailsList}>
                    <div className="flex items-center justify-between text-sm">
                      <span>Selfie capture </span>
                      <span>Step 1 — Liveness check</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>ID photo source </span>
                      <span>Step 2 — Document front</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>Match score = </span>
                      <span>{matchScore !== null ? `${matchScore.toFixed(1)}%` : "—"}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>Threshold </span>
                      <span>≥ {matchThreshold !== null ? `${Math.round(matchThreshold)}%` : "80%"}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span>Result - </span>
                      <span>{state === "passed" ? "MATCH" : state === "failed" ? "NO MATCH" : "—"}</span>
                    </div>
                  </div>
              ) : (
                  <div style={{ minHeight: '180px' }}></div> // Empty placeholder until response received
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </Card>
  );
}

function StatusMessage({ type, message }: { type: "info" | "success" | "error"; message: string }) {
  const Icon = type === "success" ? CheckCircle2 : type === "error" ? XCircle : Info;
  return (
      <div
          className={cn(
              styles.statusMessage,
              type === "info" && styles.statusInfo,
              type === "success" && styles.statusSuccess,
              type === "error" && styles.statusError,
          )}
      >
        <Icon className={styles.statusIcon} />
        {message}
      </div>
  );
}
