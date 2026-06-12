// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useRef, useCallback } from "react";
import {
  ArrowRight,
  RotateCcw,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileText,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/libs/utils";
import { BACKEND_URL } from "@/constants";
import styles from "./AuthenticateID.module.scss";
import { Card } from "./ui/card"
import { Badge } from "./ui/badge";
import { Header } from "./ui/Header";
import { PassportIcon } from "./svg/PassportIcon";
import { QrCodeIcon } from "./svg/QrCodeIcon";
import { UploadCloudIcon } from "./svg/UploadCloudIcon";
import { StateInformation } from "./ui/StateInformation";
import { UploadIcon } from "./svg/UploadIcon";
import { CheckCircle } from "./svg/CheckCircle";
import { ChevronDown } from "./svg/ChevronDown";

type IDState =
    | "empty"
    | "partial"
    | "ready"
    | "processing"
    | "passed"
    | "mismatch"
    | "failed";

type FailReason = "barcode" | "quality" | "ocr" | "";

interface AuthenticateIDProps {
  onStateChange?: (state: IDState) => void;
  onAuthenticateSuccess?: (embedding: number[], userData: any) => void;
  onContinue?: () => void;
}

export function AuthenticateID({ onStateChange, onAuthenticateSuccess, onContinue }: AuthenticateIDProps) {
  const [state, setState] = useState<IDState>("empty");
  const [frontFile, setFrontFile] = useState<File | null>(null);
  const [backFile, setBackFile] = useState<File | null>(null);
  const [frontPreview, setFrontPreview] = useState<string | null>(null);
  const [backPreview, setBackPreview] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [failReason, setFailReason] = useState<FailReason>("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [frontData, setFrontData] = useState<any>(null);
  const [backData, setBackData] = useState<any>(null);
  const [frontEmbedding, setFrontEmbedding] = useState<number[]>([]);
  const [matchResult, setMatchResult] = useState<any>(null);

  const frontInputRef = useRef<HTMLInputElement>(null);
  const backInputRef = useRef<HTMLInputElement>(null);

  const updateState = useCallback(
      (s: IDState) => {
        setState(s);
        onStateChange?.(s);
      },
      [onStateChange]
  );

  const deriveUploadState = useCallback(
      (front: File | null, back: File | null) => {
        if (front && back) updateState("ready");
        else if (front || back) updateState("partial");
        else updateState("empty");
      },
      [updateState]
  );

  const isProcessing = (s: IDState): s is "processing" => s === "processing";

  const handleFile = (side: "front" | "back", file: File) => {
    const url = URL.createObjectURL(file);
    if (side === "front") {
      setFrontFile(file);
      setFrontPreview(url);
      deriveUploadState(file, backFile);
    } else {
      setBackFile(file);
      setBackPreview(url);
      deriveUploadState(frontFile, file);
    }
  };

  const handleFileSelect = (side: "front" | "back", e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    handleFile(side, file);
  };

  const handleClear = () => {
    setFrontFile(null);
    setBackFile(null);
    setFrontPreview(null);
    setBackPreview(null);
    setFailReason("");
    setDetailsOpen(false);
    setFrontData(null);
    setBackData(null);
    setFrontEmbedding([]);
    setMatchResult(null);
    setErrorMsg(null);
    updateState("empty");
    frontInputRef.current.value = ''
    backInputRef.current.value = ''
  };

  const handleProcess = async () => {
    if (!frontFile || !backFile) return;

    updateState("processing");
    setErrorMsg(null);

    try {
      // Front side
      const frontForm = new FormData();
      frontForm.append("file", frontFile);
      const frontRes = await fetch(`${BACKEND_URL}/extract_user_data`, {
        method: "POST",
        body: frontForm,
      });
      if (!frontRes.ok) throw new Error(`Front processing failed: ${frontRes.status}`);
      const frontJson = await frontRes.json();
      if (!frontJson.success) {
        setFailReason("ocr");
        setErrorMsg(frontJson.reason || "Front side processing failed");
        updateState("failed");
        return;
      }
      setFrontData(frontJson.user_data || {});
      setFrontEmbedding(frontJson.embedding || []);

      // Back side
      const backForm = new FormData();
      backForm.append("file", backFile);
      const backRes = await fetch(`${BACKEND_URL}/extract_barcode_data`, {
        method: "POST",
        body: backForm,
      });
      if (!backRes.ok) throw new Error(`Back processing failed: ${backRes.status}`);
      const backJson = await backRes.json();
      if (!backJson.success) {
        setFailReason("barcode");
        setErrorMsg(backJson.reason || "Back side barcode parsing failed");
        updateState("failed");
        return;
      }
      setBackData(backJson.data || {});

      // Compare data
      const comparison = performDocumentDataComparison(frontJson.user_data, backJson.data);
      setMatchResult(comparison);

      if (comparison.overall_match) {
        onAuthenticateSuccess?.(frontJson.embedding, { ...frontJson.user_data, ...backJson.data });
        updateState("passed");
      } else {
        updateState("mismatch");
      }
    } catch (err: any) {
      console.error("Processing error:", err);
      setErrorMsg(err.message || "Processing failed. Please try again.");
      setFailReason("quality");
      updateState("failed");
    }
  };

  const performDocumentDataComparison = (front: any, back: any) => {
    if (!front || !back) return { overall_match: false, name_match: false, dob_match: false, gender_match: false };

    const fnameFront = (front.name || "").trim().toLowerCase();
    const fnameBack = (back.name || back.first_name || "").trim().toLowerCase();

    const lnameFront = (front.surname || "").trim().toLowerCase();
    const lnameBack = (back.surname || back.last_name || "").trim().toLowerCase();

    const dobFront = (front.dateOfBirth || "").replace(/[^0-9]/g, "");
    const dobBack = (back.dateOfBirth || back.date_of_birth || "").replace(/[^0-9]/g, "");

    const genderFront = (front.gender || "").trim().toLowerCase();
    const genderBack = (back.gender || "").trim().toLowerCase();

    const matchName =
        fnameFront &&
        lnameFront &&
        (fnameFront.includes(fnameBack) || fnameBack.includes(fnameFront)) &&
        (lnameFront.includes(lnameBack) || lnameBack.includes(lnameFront));

    const matchDob = dobFront && dobBack && dobFront === dobBack;

    const matchGender =
        genderFront &&
        genderBack &&
        (genderFront === genderBack ||
            (genderFront === "male" && genderBack === "m") ||
            (genderFront === "female" && genderBack === "f"));

    const overallMatch = matchName && matchDob && matchGender;

    return {
      name_match: matchName,
      dob_match: matchDob,
      gender_match: matchGender,
      overall_match: overallMatch,
      front,
      back,
    };
  };

  const formatDateToUS = (dateString: string): string => {
    if (!dateString) return "";

    if (dateString.match(/^\d{4}-\d{2}-\d{2}$/)) {
      const [year, month, day] = dateString.split("-");
      return `${month}/${day}/${year}`;
    }

    return dateString;
  };

  const handleRetry = () => {
    setFailReason("");
    setErrorMsg(null);
    deriveUploadState(frontFile, backFile);
  };

  const badgeLabel =
      state === "empty" || state === "partial"
          ? "Ready"
          : state === "ready"
              ? "Ready"
              : state === "processing"
                  ? "Processing"
                  : state === "passed"
                      ? "Passed"
                      : state === "mismatch"
                          ? "Needs review"
                          : "Failed";

  const showExtractedData = state === "passed" || state === "mismatch" || isProcessing(state);

  return (
      <Card>
        {/* Header */}
        <Header
          title="Step 2. Authenticate ID"
          description="Upload the front and back of your government-issued ID"
        >
          <Badge
            state={
              state === "passed"
                ? "success"
                : (state === "failed" || state === "mismatch" || errorMsg)
                  ? "error"
                  : state === "processing"
                    ? "processing"
                    : undefined
            }
          >
            {badgeLabel}
          </Badge>
        </Header>

        {/* Upload panels */}
        <div className={styles.panelsGrid}>
          {/* Front */}
          <div>
            <div className={styles.panelTitleRow}>
              <PassportIcon />
              Front (Photo)
            </div>
            <UploadPanel
                file={frontPreview}
                disabled={isProcessing(state)}
                onClickUpload={() => frontInputRef.current?.click()}
                onFileDrop={(file) => handleFile("front", file)}
            />
            <input
                ref={frontInputRef}
                type="file"
                accept="image/*"
                className={cn(styles.uploadInput, "hidden")}
                onChange={(e) => handleFileSelect("front", e)}
            />
            {showExtractedData && (
                <ExtractedDataCard
                    data={[
                      { label: "First Name", value: frontData?.name || "" },
                      { label: "Last Name", value: frontData?.surname || "" },
                      { label: "Date of Birth (MM/DD/YYYY)", value: formatDateToUS(frontData?.dateOfBirth || "") },
                      { label: "Gender", value: frontData?.gender || "" },
                    ]}
                    loading={isProcessing(state)}
                />
            )}
          </div>

          {/* Back */}
          <div>
            <div className={styles.panelTitleRow}>
              <QrCodeIcon />
              Back (Barcode)
            </div>
            <UploadPanel
                file={backPreview}
                disabled={isProcessing(state)}
                onClickUpload={() => backInputRef.current?.click()}
                onFileDrop={(file) => handleFile("back", file)}
            />
            <input
                ref={backInputRef}
                type="file"
                accept="image/*"
                className={cn(styles.uploadInput, "hidden")}
                onChange={(e) => handleFileSelect("back", e)}
            />
            {showExtractedData && (
                <ExtractedDataCard
                    data={[
                      { label: "First Name", value: backData?.name || backData?.first_name || "" },
                      { label: "Last Name", value: backData?.surname || backData?.last_name || "" },
                      { label: "Date of Birth (MM/DD/YYYY)", value: formatDateToUS(backData?.dateOfBirth || backData?.date_of_birth || "") },
                      { label: "Gender", value: backData?.gender || "" },
                    ]}
                    loading={isProcessing(state)}
                />
            )}
          </div>
        </div>

        {/* Status / Error */}
        {errorMsg && (
          <StateInformation state="failed">
            {errorMsg}
          </StateInformation>
        )}

        {!errorMsg && (
          <StateInformation
            state={
              state === "passed"
                ? "passed"
                : state === "failed"
                  ? "failed"
                  : undefined
            }
            customIcon={
              (state === "empty" || state === "partial")
                ? <UploadIcon />
                : state === "ready"
                  ? <CheckCircle stroke="white" />
                  : undefined
            }
          >
            {state === "empty" && <span><b>Upload required</b> Upload the front and back of your ID to continue.</span>}
            {state === "partial" && <span><b>Upload required</b> Upload both sides of your ID to continue.</span>}
            {state === "ready" && <span><b>Both sides uploaded</b> Click 'Process documents' to authenticate your ID.</span>}
            {isProcessing(state) && <span><b>Processing documents...</b> Please wait.</span>}
            {state === "passed" && <span><b>ID processed successfully</b> Your document has been authenticated and data extracted.</span>}
            {state === "mismatch" && <span><b>Data mismatch detected</b> Please check and re-upload if needed.</span>}
            {state === "failed" && (
              failReason === "barcode"
                ? <span><b>Barcode not detected</b> Please upload a clearer back photo.</span>
                : failReason === "quality"
                    ? <span><b>Image quality is too low (glare/blur)</b> Please re-upload.</span>
                    : failReason === "ocr"
                        ? <span><b>Couldn't read the document</b> Please re-upload.</span>
                        : <span><b>Document processing failed</b> Please try again.</span>
            )}
          </StateInformation>
        )}

        {/* Actions */}
        <Collapsible open={detailsOpen} onOpenChange={setDetailsOpen} className={styles.detailsRoot}>
          <div className={styles.actions}>
            <CollapsibleTrigger className={styles.detailsTrigger}>
              <ChevronDown />
              <span>Show details</span>
            </CollapsibleTrigger>
            <div className={styles.actions_buttons}>
              <Button variant="outline" onClick={handleClear}>
                <RotateCcw className="w-4 h-4" />
                Clear
              </Button>
              {(state === "ready" || state === "mismatch" || state === "failed") && (
                <Button onClick={handleProcess} disabled={isProcessing(state)}>
                  Process Documents
                  <ArrowRight className="w-4 h-4" />
                </Button>
              )}
              {state === "passed" && onContinue && (
                  <div className={styles.primaryActionRight}>
                    <Button onClick={onContinue}>
                      Continue
                      <ArrowRight className="w-4 h-4" />
                    </Button>
                  </div>
              )}
            </div>
          </div>
          <CollapsibleContent className={styles.detailsContent}>
            <div className={styles.detailsCard}>
              {matchResult && (
                  <div className={styles.detailsList}>
                    <p><strong>Overall Match:</strong> {matchResult.overall_match ? "Yes" : "No"}</p>
                    <p><strong>Name Match:</strong> {matchResult.name_match ? "Yes" : "No"}</p>
                    <p><strong>Date of Birth Match:</strong> {matchResult.dob_match ? "Yes" : "No"}</p>
                    <p><strong>Gender Match:</strong> {matchResult.gender_match ? "Yes" : "No"}</p>
                  </div>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </Card>
  );
}

function UploadPanel({
  file,
  disabled,
  onClickUpload,
  onFileDrop,
}: {
  file: string | null;
  disabled: boolean;
  onClickUpload: () => void;
  onFileDrop: (file: File) => void;
}) {
  const dragCounter = useRef(0);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (!disabled) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = 0;
    setIsDragging(false);
    if (disabled) return;
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.type.startsWith("image/")) {
      onFileDrop(droppedFile);
    }
  };

  return (
      <div
          onClick={disabled ? undefined : onClickUpload}
          onDragOver={handleDragOver}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
              styles.uploadPanel,
              file ? styles.uploadPanelFilled : styles.uploadPanelEmpty,
              disabled && styles.uploadPanelDisabled,
              isDragging && styles.uploadPanelDragging,
          )}
      >
        {file ? (
            <img src={file} alt="Uploaded document" className={styles.uploadImage} />
        ) : (
            <div className={styles.uploadPlaceholder}>
              <div className={styles.uploadIconWrapper}>
                <UploadCloudIcon />
              </div>
              <p className={styles.uploadText}>
                <span className={styles.uploadTextEmphasis}>Click to upload</span> or drag and drop
              </p>
            </div>
        )}
      </div>
  );
}

function ExtractedDataCard({
  data,
  loading,
}: {
  data: { label: string; value: string }[];
  loading: boolean;
}) {
  return (
      <div className={styles.extractedCard}>
        <h4 className={styles.extractedTitle}>Extracted data</h4>
        <div className={styles.extractedList}>
          {data.map((d) => (
            <div key={d.label} className={styles.extractedRow}>
              <span className={styles.extractedLabel}>{d.label}</span>
              {loading ? (
                  <div className={styles.extractedLoading}>
                    <Loader2 className={styles.spinnerIcon} />
                    <span className={styles.spinnerText}>Extracting…</span>
                  </div>
              ) : (
                  <span className={styles.extractedValue}>{d.value || "—"}</span>
              )}
            </div>
          ))}
        </div>
      </div>
  );
}

function StatusMessage({
                         type,
                         message,
                       }: {
  type: "info" | "success" | "error" | "warning";
  message: string;
}) {
  const Icon = type === "success" ? CheckCircle2 : type === "error" ? XCircle : type === "warning" ? AlertTriangle : FileText;
  return (
      <div
          className={cn(
              styles.statusMessage,
              type === "info" && styles.statusInfo,
              type === "success" && styles.statusSuccess,
              type === "error" && styles.statusError,
              type === "warning" && styles.statusWarning,
          )}
      >
        <Icon className={styles.statusIcon} />
        {message}
      </div>
  );
}
