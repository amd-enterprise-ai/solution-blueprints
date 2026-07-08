// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useCallback, useEffect } from "react";
import { useRoomContext, useChat } from "@livekit/components-react";
import { Track } from "livekit-client";
import styles from "./ClientSimulator.module.css";

interface ClientSimulatorProps {
  isCallActive: boolean;
  micOn: boolean;
  onMicToggle: (on: boolean) => void;
  showToolsPanel: boolean;
  onToggleToolsPanel: (show: boolean) => void;
  onStartCall?: () => void;
  onSendMessage?: (message: string) => void;
  onEndCall?: () => void;
  onFileUpload?: (file: File, type: "image" | "video") => void;
  onEndSessionSignaled?: (roomName: string) => void;
  showRatingModal?: boolean;
}

export function ClientSimulator({
                                  isCallActive,
                                  micOn,
                                  onMicToggle,
                                  showToolsPanel,
                                  onToggleToolsPanel,
                                  onStartCall,
                                  onSendMessage,
                                  onEndCall,
                                  onFileUpload,
                                  onEndSessionSignaled,
                                  showRatingModal = false,
                                }: ClientSimulatorProps) {
  const [message, setMessage] = useState("");
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [isUploadingVideo, setIsUploadingVideo] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [videoPreview, setVideoPreview] = useState<string | null>(null);
  const [showVideoTooltip, setShowVideoTooltip] = useState(false);
  const room = useRoomContext();
  const { send } = useChat();

  useEffect(() => {
    if (!room?.localParticipant) return;
    const pub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
    if (pub?.track) {
      if (micOn) {
        pub.track.unmute();
      } else {
        pub.track.mute();
      }
    }
  }, [micOn, room]);

  useEffect(() => {
    if (!room) return;

    room.registerRpcMethod("sessionEnded", async (data) => {
      try {
        const payload = JSON.parse(data.payload);
        const roomName = payload.room ?? room.name;
        onEndSessionSignaled?.(roomName);
      } catch (e) {
        console.error("sessionEnded parse error", e);
        onEndSessionSignaled?.(room.name);
      }
      return JSON.stringify({ status: "modal pending" });
    });

    return () => {
      room.unregisterRpcMethod("sessionEnded");
    };
  }, [room, onEndSessionSignaled]);

  const handleSend = useCallback(async () => {
    const text = message.trim();
    if (!text || !isCallActive) return;

    try {
      await send(text);
      onSendMessage?.(text);
      setMessage("");
    } catch (e) {
      console.error("Failed to send message", e);
    }
  }, [message, isCallActive, send, onSendMessage]);

  const handleKeyDown = useCallback(
      (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          void handleSend();
        }
      },
      [handleSend],
  );

  const handleEndCall = useCallback(() => {
    setMessage("");
    room?.disconnect();
    onEndCall?.();
  }, [onEndCall, room]);

  const handleStartCall = useCallback(() => {
    onStartCall?.();
  }, [onStartCall]);

  const handleUploadImage = useCallback(() => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";

    input.onchange = async (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file || !room?.name) return;

      const previewUrl = URL.createObjectURL(file);
      setImagePreview(previewUrl);
      setIsUploadingImage(true);

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("room_name", room.name);

        const response = await fetch("/agent/ingest/image", {
          method: "POST",
          body: formData,
        });

        const result = await response.json();

        if (result?.status === "ok") {
          onFileUpload?.(file, "image");

          setMessage("I've uploaded a photo");

          setTimeout(async () => {
            try {
              await send("I've uploaded a photo");
              onSendMessage?.("I've uploaded a photo");
              setMessage("");
            } catch (e) {
              console.error("Failed to send message", e);
            }
          }, 100);
        }
      } catch (error) {
        console.error("Upload failed:", error);
      } finally {
        setIsUploadingImage(false);
        URL.revokeObjectURL(previewUrl);
        setImagePreview(null);
      }
    };

    input.click();
  }, [room?.name, onFileUpload, send, onSendMessage]);

  const handleUploadVideo = useCallback(() => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "video/*";

    input.onchange = async (event) => {
      const file = (event.target as HTMLInputElement).files?.[0];
      if (!file || !room?.name) return;

      const previewUrl = URL.createObjectURL(file);
      setVideoPreview(previewUrl);
      setIsUploadingVideo(true);

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("room_name", room.name);

        const response = await fetch("/agent/ingest/video", {
          method: "POST",
          body: formData,
        });

        const result = await response.json();

        if (result?.status === "ok") {
          onFileUpload?.(file, "video");

          setMessage("I've uploaded a video");

          setTimeout(async () => {
            try {
              await send("I've uploaded a video");
              onSendMessage?.("I've uploaded a video");
              setMessage("");
            } catch (e) {
              console.error("Failed to send message", e);
            }
          }, 100);
        }
      } catch (error) {
        console.error("Upload failed:", error);
      } finally {
        setIsUploadingVideo(false);
        URL.revokeObjectURL(previewUrl);
        setVideoPreview(null);
      }
    };

    input.click();
  }, [room?.name, onFileUpload, send, onSendMessage]);

  const micStyle = micOn ? styles.micToggleActive : styles.micToggleMuted;
  const micDropStyle = micOn ? styles.micDropdownActive : styles.micDropdownMuted;

  return (
      <section className={styles.card} aria-label="Client simulator">
        <div className={styles.content}>
          <header className={styles.header}>
            <div className={styles.headerRow}>
              <div className={styles.headerInner}>
                <h2 className={styles.title}>Client Simulator</h2>
                <p className={styles.subtitle}>Demo only — simulates customer side</p>
              </div>
              <div
                  className={`${styles.toolsToggle} ${showToolsPanel ? styles.toolsToggleActive : ""}`}
                  role="switch"
                  aria-checked={showToolsPanel}
                  aria-label="Show tools panel"
                  tabIndex={0}
                  onClick={() => onToggleToolsPanel(!showToolsPanel)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onToggleToolsPanel(!showToolsPanel);
                    }
                  }}
              >
                <svg
                    className={styles.toolsToggleIcon}
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 20 20"
                    fill="none"
                >
                  <path
                      d="M17.5 4.16667L8.33333 4.16667M17.5 15.8333L8.33333 15.8333M17.5 10L8.33333 10M5 4.16667C5 4.85703 4.44036 5.41667 3.75 5.41667C3.05964 5.41667 2.5 4.85703 2.5 4.16667C2.5 3.47632 3.05964 2.91667 3.75 2.91667C4.44036 2.91667 5 3.47632 5 4.16667ZM5 15.8333C5 16.5237 4.44036 17.0833 3.75 17.0833C3.05964 17.0833 2.5 16.5237 2.5 15.8333C2.5 15.143 3.05964 14.5833 3.75 14.5833C4.44036 14.5833 5 15.143 5 15.8333ZM5 10C5 10.6904 4.44036 11.25 3.75 11.25C3.05964 11.25 2.5 10.6904 2.5 10C2.5 9.30965 3.05964 8.75001 3.75 8.75001C4.44036 8.75001 5 9.30965 5 10Z"
                      stroke="currentColor"
                      strokeWidth="1.67"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                  />
                </svg>
                <span className={styles.toolsToggleLabel}>Show tool calls separately</span>
                <div className={`${styles.switch} ${showToolsPanel ? styles.switchActive : ""}`}>
                  <div className={styles.switchKnob} />
                </div>
              </div>
            </div>
            <div className={styles.passphraseHint}>
              <span className={styles.passphraseLabel}>Say a passphrase to authenticate</span>
              <div className={styles.passphraseOptions}>
                <span className={styles.passphraseCode}>milkyway</span>
                <span className={styles.passphrasePlan}>— regular plan</span>
                <span className={styles.passphraseCode}>mars</span>
                <span className={styles.passphrasePlan}>— premium plan</span>
              </div>
            </div>
          </header>

          <div className={styles.controlBar}>
            <div className={styles.inputRow}>
              <input
                  className={styles.input}
                  type="text"
                  placeholder="Type something..."
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={!isCallActive}
              />
              <button
                  className={styles.sendBtn}
                  onClick={() => void handleSend()}
                  type="button"
                  aria-label="Send message"
                  disabled={!isCallActive || !message.trim()}
              >
                <svg
                    className={styles.sendIcon}
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 20 20"
                    fill="none"
                >
                  <path
                      d="M8.75036 10H4.16702M4.09648 10.243L2.15071 16.0552C1.99785 16.5118 1.92142 16.7401 1.97627 16.8807C2.0239 17.0028 2.1262 17.0954 2.25244 17.1306C2.3978 17.1712 2.61736 17.0724 3.05647 16.8748L16.9827 10.608C17.4113 10.4151 17.6256 10.3187 17.6918 10.1847C17.7494 10.0683 17.7494 9.93176 17.6918 9.81537C17.6256 9.6814 17.4113 9.58497 16.9827 9.39209L3.05161 3.12314C2.61383 2.92614 2.39493 2.82764 2.24971 2.86804C2.1236 2.90314 2.0213 2.99546 1.97351 3.11733C1.91847 3.25766 1.99408 3.48547 2.14531 3.9411L4.09702 9.82131C4.12299 9.89957 4.13598 9.9387 4.14111 9.97871C4.14565 10.0142 4.14561 10.0502 4.14097 10.0857C4.13574 10.1257 4.12265 10.1648 4.09648 10.243Z"
                      stroke="var(--text-secondary)"
                      strokeWidth="1.66667"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>

            <div className={styles.controlsRow}>
              <div className={styles.toggleGroup}>
                <div className={styles.micCompound}>
                  <button
                      className={`${styles.micToggle} ${micStyle}`}
                      type="button"
                      aria-label={micOn ? "Mute microphone" : "Unmute microphone"}
                      aria-pressed={micOn}
                      disabled={!isCallActive}
                      onClick={() => onMicToggle(!micOn)}
                  >
                    {micOn ? (
                        <svg
                            className={styles.toggleIcon}
                            xmlns="http://www.w3.org/2000/svg"
                            width="18"
                            height="18"
                            viewBox="0 0 20 20"
                            fill="none"
                        >
                          <path
                              d="M15.8334 8.33332V9.99999C15.8334 13.2217 13.2217 15.8333 10 15.8333M4.16669 8.33332V9.99999C4.16669 13.2217 6.77836 15.8333 10 15.8333M10 15.8333V18.3333M6.66669 18.3333H13.3334M10 12.5C8.61931 12.5 7.50002 11.3807 7.50002 9.99999V4.16666C7.50002 2.78594 8.61931 1.66666 10 1.66666C11.3807 1.66666 12.5 2.78594 12.5 4.16666V9.99999C12.5 11.3807 11.3807 12.5 10 12.5Z"
                              stroke="currentColor"
                              strokeWidth="1.67"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                          />
                        </svg>
                    ) : (
                        <svg
                            className={styles.toggleIcon}
                            xmlns="http://www.w3.org/2000/svg"
                            width="18"
                            height="18"
                            viewBox="0 0 24 24"
                            fill="none"
                        >
                          <path
                              d="M2 2L22 22M18.89 13.23A7.12 7.12 0 0 0 19 12V10M5 10V12C5 15.53 7.61 18.43 11 18.93M12 22V19M8 22H16M15 9.34V4C15 2.34 13.66 1 12 1C10.65 1 9.5 1.9 9.13 3.13M12 17C9.24 17 7 14.76 7 12V10L12.17 15.17"
                              stroke="currentColor"
                              strokeWidth="1.67"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                          />
                        </svg>
                    )}
                  </button>
                  <button
                      className={`${styles.micDropdown} ${micDropStyle}`}
                      type="button"
                      aria-label="Select microphone device"
                      disabled={!isCallActive}
                  >
                    <svg
                        className={styles.chevronIcon}
                        xmlns="http://www.w3.org/2000/svg"
                        width="14"
                        height="14"
                        viewBox="0 0 16 16"
                        fill="none"
                    >
                      <path
                          d="M4 6L8 10L12 6"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </div>

                <div className={styles.uploadButtonWrapper}>
                  <button
                      className={`${styles.toggleBtn}`}
                      type="button"
                      aria-label="Upload image"
                      disabled={!isCallActive || isUploadingImage}
                      onClick={handleUploadImage}
                  >
                    <svg
                        className={`${styles.toggleIcon} ${isUploadingImage ? styles.loader : ""}`}
                        xmlns="http://www.w3.org/2000/svg"
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.67"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    >
                      <rect x="2" y="4" width="20" height="16" rx="2" ry="2" />
                      <circle cx="8.5" cy="9.5" r="2.5" />
                      <path d="M21 15l-5-4-3 3-4-4-5 5" />
                    </svg>
                  </button>
                  {imagePreview && (
                      <div className={styles.previewPopup}>
                        <img src={imagePreview} alt="Upload preview" className={styles.previewImage} />
                      </div>
                  )}
                </div>

                <div className={styles.uploadButtonWrapper}>
                  <button
                      className={`${styles.toggleBtn}`}
                      type="button"
                      aria-label="Upload video"
                      disabled={!isCallActive || isUploadingVideo}
                      onClick={handleUploadVideo}
                      onMouseEnter={() => setShowVideoTooltip(true)}
                      onMouseLeave={() => setShowVideoTooltip(false)}
                  >
                    <svg
                        className={`${styles.toggleIcon} ${isUploadingVideo ? styles.loader : ""}`}
                        xmlns="http://www.w3.org/2000/svg"
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.67"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    >
                      <rect x="2" y="6" width="16" height="12" rx="2" />
                      <path d="M22 8l-4 4 4 4" />
                    </svg>
                  </button>

                  {showVideoTooltip && (
                      <div className={styles.videoTooltip}>
                        Recommended maximum video length is 60 seconds
                      </div>
                  )}

                  {videoPreview && (
                      <div className={styles.previewPopup}>
                        <video
                            src={videoPreview}
                            className={styles.previewImage}
                            controls={false}
                            autoPlay={false}
                        />
                      </div>
                  )}
                </div>
              </div>

              {isCallActive ? (
                  <button
                      className={styles.endCallBtn}
                      onClick={handleEndCall}
                      type="button"
                      // Disabled while rating modal is open — user must rate first
                      disabled={showRatingModal}
                      style={showRatingModal ? { opacity: 0.4, pointerEvents: "none" } : undefined}
                  >
                    <svg
                        className={styles.endCallIcon}
                        xmlns="http://www.w3.org/2000/svg"
                        width="16"
                        height="16"
                        viewBox="0 0 20 20"
                        fill="none"
                    >
                      <path
                          d="M4.56285 10.7192C3.70374 9.3852 3.06369 7.95102 2.6427 6.46777C2.50919 5.9974 2.44244 5.76221 2.44141 5.41809C2.44028 5.03624 2.57475 4.51916 2.76176 4.18624C2.9303 3.88622 3.15098 3.66554 3.59233 3.22419L3.72369 3.09282C4.16656 2.64996 4.388 2.42852 4.62581 2.30823C5.09878 2.06901 5.65734 2.06901 6.1303 2.30823C6.36812 2.42852 6.58956 2.64996 7.03242 3.09282L7.19482 3.25522C7.48615 3.54655 7.63182 3.69222 7.72706 3.8387C8.08622 4.39111 8.08622 5.10326 7.72706 5.65567C7.63182 5.80215 7.48615 5.94782 7.19482 6.23916C7.09956 6.33442 7.05192 6.38205 7.01206 6.43773C6.87038 6.63559 6.82146 6.92247 6.88957 7.1561C6.90873 7.22184 6.93368 7.2738 6.98357 7.37771C7.08426 7.58743 7.1913 7.79487 7.30469 7.99973M9.31808 10.6816L9.35553 10.7192C10.3568 11.7206 11.4891 12.5112 12.6971 13.0912C12.801 13.1411 12.8529 13.166 12.9187 13.1852C13.1523 13.2533 13.4392 13.2044 13.637 13.0627C13.6927 13.0228 13.7403 12.9752 13.8356 12.88C14.1269 12.5886 14.2726 12.4429 14.4191 12.3477C14.9715 11.9885 15.6837 11.9885 16.2361 12.3477C16.3825 12.4429 16.5282 12.5886 16.8196 12.88L16.9819 13.0423C17.4248 13.4852 17.6462 13.7066 17.7665 13.9445C18.0058 14.4174 18.0058 14.976 17.7665 15.449C17.6462 15.6868 17.4248 15.9082 16.9819 16.3511L16.8506 16.4824C16.4092 16.9238 16.1886 17.1445 15.8885 17.313C15.5556 17.5 15.0385 17.6345 14.6567 17.6334C14.3126 17.6323 14.0774 17.5656 13.607 17.4321C11.0792 16.7146 8.69387 15.3609 6.70388 13.3709L6.66647 13.3333M17.4997 2.50001L2.49968 17.5"
                          stroke="#F97066"
                          strokeWidth="1.67"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                      />
                    </svg>
                    <span className={styles.endCallText}>End call</span>
                  </button>
              ) : (
                  <button className={styles.callBtn} onClick={handleStartCall} type="button">
                    <span className={styles.callText}>Call</span>
                  </button>
              )}
            </div>
          </div>
        </div>


      </section>
  );
}
