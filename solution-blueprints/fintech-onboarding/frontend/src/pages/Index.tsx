// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState } from "react";
import { VerificationSidebar } from "@/components/VerificationSidebar";
import { LivenessCheck } from "@/components/LivenessCheck";
import { AuthenticateID } from "@/components/AuthenticateID";
import { VerifyMatch } from "@/components/VerifyMatch";
import styles from "./Index.module.scss";
import { LivenessState } from "@/components/models";

type IDState = "empty" | "partial" | "ready" | "processing" | "passed" | "mismatch" | "failed";
type MatchState = "not-run" | "processing" | "passed" | "failed" | "unavailable";

const Index = () => {
  const [currentStep, setCurrentStep] = useState(1);
  const [livenessState, setLivenessState] = useState<LivenessState>("ready");
  const [idState, setIdState] = useState<IDState>("empty");
  const [matchState, setMatchState] = useState<MatchState>("not-run");

  // States for embeddings
  const [liveEmbedding, setLiveEmbedding] = useState<number[] | null>(null);
  const [docEmbedding, setDocEmbedding] = useState<number[] | null>(null);

  const step1Completed = livenessState === "passed" || currentStep > 1;
  const step2Completed = idState === "passed" || currentStep > 2;
  const step3Completed = matchState === "passed";

  const steps = [
    {
      label: "Confirm liveness",
      status: step1Completed
          ? ("completed" as const)
          : currentStep === 1
              ? ("active" as const)
              : ("locked" as const),
    },
    {
      label: "Authenticate ID",
      status: step2Completed
          ? ("completed" as const)
          : currentStep === 2
              ? ("active" as const)
              : ("locked" as const),
    },
    {
      label: "Verify match",
      status: step3Completed
          ? ("completed" as const)
          : currentStep === 3
              ? ("active" as const)
              : ("locked" as const),
    },
  ];

  const handleRetakeSelfie = () => {
    setLivenessState("ready");
    setMatchState("not-run");
    setLiveEmbedding(null);
    setCurrentStep(1);
  };

  const handleFinish = () => {
    // Show final success screen or send data to server
    alert("Verification completed successfully!");
  };

  return (
      <div className={styles.root}>
        <VerificationSidebar steps={steps} />
        <main className={styles.main}>
          {currentStep === 1 && (
              <LivenessCheck
                  onStateChange={(state) => setLivenessState(state)}
                  onLivenessSuccess={(embedding) => setLiveEmbedding(embedding)}
                  onContinue={() => setCurrentStep(2)}
              />
          )}
          {currentStep === 2 && (
              <AuthenticateID
                  onStateChange={(state) => setIdState(state)}
                  onAuthenticateSuccess={(embedding, userData) => {
                    setDocEmbedding(embedding);
                    // Optionally store userData globally if needed
                  }}
                  onContinue={() => setCurrentStep(3)}
              />
          )}
          {currentStep === 3 && (
              <VerifyMatch
                  onStateChange={(state) => setMatchState(state)}
                  onRetakeSelfie={handleRetakeSelfie}
                  onFinish={handleFinish}
                  liveEmbedding={liveEmbedding}
                  docEmbedding={docEmbedding}
              />
          )}
        </main>
      </div>
  );
};

export default Index;
