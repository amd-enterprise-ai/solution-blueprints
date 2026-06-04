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
}: ClientSimulatorProps) {
  const [message, setMessage] = useState("");
  const [camOn, setCamOn] = useState(false);
  const [screenOn, setScreenOn] = useState(false);
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

  const micStyle = micOn ? styles.micToggleActive : styles.micToggleMuted;
  const micDropStyle = micOn ? styles.micDropdownActive : styles.micDropdownMuted;

  return (
    <section className={styles.card} aria-label='Client simulator'>
      <div className={styles.content}>
        <header className={styles.header}>
          <div className={styles.headerRow}>
            <div className={styles.headerInner}>
              <h2 className={styles.title}>Client Simulator</h2>
              <p className={styles.subtitle}>Demo only — simulates customer side</p>
            </div>
            <div
              className={`${styles.toolsToggle} ${showToolsPanel ? styles.toolsToggleActive : ""}`}
              role='switch'
              aria-checked={showToolsPanel}
              aria-label='Show tools panel'
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
                xmlns='http://www.w3.org/2000/svg'
                width='16'
                height='16'
                viewBox='0 0 20 20'
                fill='none'
              >
                <path
                  d='M17.5 4.16667L8.33333 4.16667M17.5 15.8333L8.33333 15.8333M17.5 10L8.33333 10M5 4.16667C5 4.85703 4.44036 5.41667 3.75 5.41667C3.05964 5.41667 2.5 4.85703 2.5 4.16667C2.5 3.47632 3.05964 2.91667 3.75 2.91667C4.44036 2.91667 5 3.47632 5 4.16667ZM5 15.8333C5 16.5237 4.44036 17.0833 3.75 17.0833C3.05964 17.0833 2.5 16.5237 2.5 15.8333C2.5 15.143 3.05964 14.5833 3.75 14.5833C4.44036 14.5833 5 15.143 5 15.8333ZM5 10C5 10.6904 4.44036 11.25 3.75 11.25C3.05964 11.25 2.5 10.6904 2.5 10C2.5 9.30965 3.05964 8.75001 3.75 8.75001C4.44036 8.75001 5 9.30965 5 10Z'
                  stroke='currentColor'
                  strokeWidth='1.67'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
              <span className={styles.toolsToggleLabel}>Show tool execution history</span>
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
          {/* Chat input */}
          <div className={styles.inputRow}>
            <input
              className={styles.input}
              type='text'
              placeholder='Type something...'
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!isCallActive}
            />
            <button
              className={styles.sendBtn}
              onClick={() => void handleSend()}
              type='button'
              aria-label='Send message'
              disabled={!isCallActive || !message.trim()}
            >
              <svg
                className={styles.sendIcon}
                xmlns='http://www.w3.org/2000/svg'
                width='16'
                height='16'
                viewBox='0 0 20 20'
                fill='none'
              >
                <path
                  d='M8.75036 10H4.16702M4.09648 10.243L2.15071 16.0552C1.99785 16.5118 1.92142 16.7401 1.97627 16.8807C2.0239 17.0028 2.1262 17.0954 2.25244 17.1306C2.3978 17.1712 2.61736 17.0724 3.05647 16.8748L16.9827 10.608C17.4113 10.4151 17.6256 10.3187 17.6918 10.1847C17.7494 10.0683 17.7494 9.93176 17.6918 9.81537C17.6256 9.6814 17.4113 9.58497 16.9827 9.39209L3.05161 3.12314C2.61383 2.92614 2.39493 2.82764 2.24971 2.86804C2.1236 2.90314 2.0213 2.99546 1.97351 3.11733C1.91847 3.25766 1.99408 3.48547 2.14531 3.9411L4.09702 9.82131C4.12299 9.89957 4.13598 9.9387 4.14111 9.97871C4.14565 10.0142 4.14561 10.0502 4.14097 10.0857C4.13574 10.1257 4.12265 10.1648 4.09648 10.243Z'
                  stroke='var(--text-secondary)'
                  strokeWidth='1.66667'
                  strokeLinecap='round'
                  strokeLinejoin='round'
                />
              </svg>
            </button>
          </div>

          {/* Controls row */}
          <div className={styles.controlsRow}>
            <div className={styles.toggleGroup}>
              {/* Microphone — compound button */}
              <div className={styles.micCompound}>
                <button
                  className={`${styles.micToggle} ${micStyle}`}
                  type='button'
                  aria-label={micOn ? "Mute microphone" : "Unmute microphone"}
                  aria-pressed={micOn}
                  disabled={!isCallActive}
                  onClick={() => onMicToggle(!micOn)}
                >
                  {micOn ? (
                    <svg
                      className={styles.toggleIcon}
                      xmlns='http://www.w3.org/2000/svg'
                      width='18'
                      height='18'
                      viewBox='0 0 20 20'
                      fill='none'
                    >
                      <path
                        d='M15.8334 8.33332V9.99999C15.8334 13.2217 13.2217 15.8333 10 15.8333M4.16669 8.33332V9.99999C4.16669 13.2217 6.77836 15.8333 10 15.8333M10 15.8333V18.3333M6.66669 18.3333H13.3334M10 12.5C8.61931 12.5 7.50002 11.3807 7.50002 9.99999V4.16666C7.50002 2.78594 8.61931 1.66666 10 1.66666C11.3807 1.66666 12.5 2.78594 12.5 4.16666V9.99999C12.5 11.3807 11.3807 12.5 10 12.5Z'
                        stroke='currentColor'
                        strokeWidth='1.67'
                        strokeLinecap='round'
                        strokeLinejoin='round'
                      />
                    </svg>
                  ) : (
                    <svg
                      className={styles.toggleIcon}
                      xmlns='http://www.w3.org/2000/svg'
                      width='18'
                      height='18'
                      viewBox='0 0 24 24'
                      fill='none'
                    >
                      <path
                        d='M2 2L22 22M18.89 13.23A7.12 7.12 0 0 0 19 12V10M5 10V12C5 15.53 7.61 18.43 11 18.93M12 22V19M8 22H16M15 9.34V4C15 2.34 13.66 1 12 1C10.65 1 9.5 1.9 9.13 3.13M12 17C9.24 17 7 14.76 7 12V10L12.17 15.17'
                        stroke='currentColor'
                        strokeWidth='1.67'
                        strokeLinecap='round'
                        strokeLinejoin='round'
                      />
                    </svg>
                  )}
                </button>
                <button
                  className={`${styles.micDropdown} ${micDropStyle}`}
                  type='button'
                  aria-label='Select microphone device'
                  disabled={!isCallActive}
                >
                  <svg
                    className={styles.chevronIcon}
                    xmlns='http://www.w3.org/2000/svg'
                    width='14'
                    height='14'
                    viewBox='0 0 16 16'
                    fill='none'
                  >
                    <path
                      d='M4 6L8 10L12 6'
                      stroke='currentColor'
                      strokeWidth='1.5'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                    />
                  </svg>
                </button>
              </div>

              {/* Camera */}
              <button
                className={`${styles.toggleBtn} ${camOn ? styles.toggleBtnActive : ""}`}
                type='button'
                aria-label={camOn ? "Turn off camera" : "Turn on camera"}
                aria-pressed={camOn}
                disabled={!isCallActive}
                onClick={() => setCamOn((v) => !v)}
              >
                {camOn ? (
                  <svg
                    className={styles.toggleIcon}
                    xmlns='http://www.w3.org/2000/svg'
                    width='18'
                    height='18'
                    viewBox='0 0 20 20'
                    fill='none'
                  >
                    <path
                      d='M1.66669 6.98101C1.66669 6.68908 1.66669 6.54311 1.67887 6.42017C1.79635 5.23438 2.73441 4.29632 3.9202 4.17884C4.04314 4.16666 4.19698 4.16666 4.50467 4.16666C4.62323 4.16666 4.68251 4.16666 4.73284 4.16361C5.37553 4.12469 5.93831 3.71905 6.17847 3.12166C6.19728 3.07487 6.21486 3.02213 6.25002 2.91666C6.28518 2.81118 6.30276 2.75844 6.32157 2.71166C6.56173 2.11426 7.12451 1.70863 7.7672 1.6697C7.81753 1.66666 7.87312 1.66666 7.9843 1.66666H12.0157C12.1269 1.66666 12.1825 1.66666 12.2328 1.6697C12.8755 1.70863 13.4383 2.11426 13.6785 2.71166C13.6973 2.75844 13.7149 2.81118 13.75 2.91666C13.7852 3.02213 13.8028 3.07487 13.8216 3.12166C14.0617 3.71905 14.6245 4.12469 15.2672 4.16361C15.3175 4.16666 15.3768 4.16666 15.4954 4.16666C15.8031 4.16666 15.9569 4.16666 16.0798 4.17884C17.2656 4.29632 18.2037 5.23438 18.3212 6.42017C18.3334 6.54311 18.3334 6.68908 18.3334 6.98101V13.5C18.3334 14.9001 18.3334 15.6002 18.0609 16.135C17.8212 16.6054 17.4387 16.9878 16.9683 17.2275C16.4335 17.5 15.7335 17.5 14.3334 17.5H5.66669C4.26656 17.5 3.56649 17.5 3.03171 17.2275C2.56131 16.9878 2.17885 16.6054 1.93917 16.135C1.66669 15.6002 1.66669 14.9001 1.66669 13.5V6.98101Z'
                      stroke='currentColor'
                      strokeWidth='1.67'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                    />
                    <path
                      d='M10 13.75C11.841 13.75 13.3334 12.2576 13.3334 10.4167C13.3334 8.57571 11.841 7.08332 10 7.08332C8.15907 7.08332 6.66669 8.57571 6.66669 10.4167C6.66669 12.2576 8.15907 13.75 10 13.75Z'
                      stroke='currentColor'
                      strokeWidth='1.67'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                    />
                  </svg>
                ) : (
                  <svg
                    className={styles.toggleIcon}
                    xmlns='http://www.w3.org/2000/svg'
                    width='18'
                    height='18'
                    viewBox='0 0 24 24'
                    fill='none'
                  >
                    <path
                      d='M2 2L22 22M14.5 4.17C14.28 3.18 13.73 2.29 12.93 1.67H11.07C10.07 1.67 9.19 2.27 8.82 3.17L8.75 3.34C8.71 3.44 8.7 3.49 8.68 3.54C8.44 4.14 7.88 4.55 7.23 4.59C7.18 4.59 7.12 4.59 7 4.59H6.5C5.12 4.6 4.42 4.6 3.89 4.87C3.42 5.1 3.04 5.49 2.8 5.96C2.53 6.49 2.53 7.19 2.53 8.59V16.2C2.53 17.6 2.53 18.3 2.8 18.83C3.04 19.3 3.42 19.69 3.89 19.93C4.42 20.2 5.12 20.2 6.5 20.2H17.5C18.88 20.2 19.58 20.2 20.11 19.93C20.58 19.69 20.96 19.3 21.2 18.83C21.47 18.3 21.47 17.6 21.47 16.2V8.59C21.47 7.42 21.47 6.72 21.29 6.2M9.88 14.12C10.8 15.04 12.26 15.04 13.18 14.12C14.1 13.2 14.1 11.74 13.18 10.82'
                      stroke='currentColor'
                      strokeWidth='1.67'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                    />
                  </svg>
                )}
              </button>

              {/* Screen share */}
              <button
                className={`${styles.toggleBtn} ${screenOn ? styles.toggleBtnActive : ""}`}
                type='button'
                aria-label={screenOn ? "Stop screen share" : "Share screen"}
                aria-pressed={screenOn}
                disabled={!isCallActive}
                onClick={() => setScreenOn((v) => !v)}
              >
                {screenOn ? (
                  <svg
                    className={styles.toggleIcon}
                    xmlns='http://www.w3.org/2000/svg'
                    width='18'
                    height='18'
                    viewBox='0 0 20 20'
                    fill='none'
                  >
                    <path
                      d='M6.66669 17.5H13.3334M10 14.1667V17.5M5.66669 14.1667H14.3334C15.7335 14.1667 16.4335 14.1667 16.9683 13.8942C17.4387 13.6545 17.8212 13.272 18.0609 12.8016C18.3334 12.2669 18.3334 11.5668 18.3334 10.1667V6.5C18.3334 5.09987 18.3334 4.3998 18.0609 3.86502C17.8212 3.39462 17.4387 3.01217 16.9683 2.77248C16.4335 2.5 15.7335 2.5 14.3334 2.5H5.66669C4.26656 2.5 3.56649 2.5 3.03171 2.77248C2.56131 3.01217 2.17885 3.39462 1.93917 3.86502C1.66669 4.3998 1.66669 5.09987 1.66669 6.5V10.1667C1.66669 11.5668 1.66669 12.2669 1.93917 12.8016C2.17885 13.272 2.56131 13.6545 3.03171 13.8942C3.56649 14.1667 4.26656 14.1667 5.66669 14.1667Z'
                      stroke='currentColor'
                      strokeWidth='1.67'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                    />
                  </svg>
                ) : (
                  <svg
                    className={styles.toggleIcon}
                    xmlns='http://www.w3.org/2000/svg'
                    width='18'
                    height='18'
                    viewBox='0 0 24 24'
                    fill='none'
                  >
                    <path
                      d='M2 2L22 22M3 3H2.5C2.5 3.83 2.5 4.25 2.59 4.6C2.79 5.36 3.39 5.96 4.15 6.16C4.5 6.25 4.92 6.25 5.75 6.25H18.25C19.08 6.25 19.5 6.25 19.85 6.16C20.61 5.96 21.21 5.36 21.41 4.6C21.5 4.25 21.5 3.83 21.5 3H7.5M8 21H16M12 17V21M6.8 17H17.2C18.88 17 19.72 17 20.36 16.67C20.93 16.38 21.38 15.93 21.67 15.36C22 14.72 22 13.88 22 12.2V7.8C22 6.12 22 5.28 21.67 4.64C21.38 4.07 20.93 3.62 20.36 3.33C19.72 3 18.88 3 17.2 3H6.8C5.12 3 4.28 3 3.64 3.33C3.07 3.62 2.62 4.07 2.33 4.64C2 5.28 2 6.12 2 7.8V12.2C2 13.88 2 14.72 2.33 15.36C2.62 15.93 3.07 16.38 3.64 16.67C4.28 17 5.12 17 6.8 17Z'
                      stroke='currentColor'
                      strokeWidth='1.67'
                      strokeLinecap='round'
                      strokeLinejoin='round'
                    />
                  </svg>
                )}
              </button>
            </div>

            {/* End / Start call */}
            {isCallActive ? (
              <button className={styles.endCallBtn} onClick={handleEndCall} type='button'>
                <svg
                  className={styles.endCallIcon}
                  xmlns='http://www.w3.org/2000/svg'
                  width='16'
                  height='16'
                  viewBox='0 0 20 20'
                  fill='none'
                >
                  <path
                    d='M4.56285 10.7192C3.70374 9.3852 3.06369 7.95102 2.6427 6.46777C2.50919 5.9974 2.44244 5.76221 2.44141 5.41809C2.44028 5.03624 2.57475 4.51916 2.76176 4.18624C2.9303 3.88622 3.15098 3.66554 3.59233 3.22419L3.72369 3.09282C4.16656 2.64996 4.388 2.42852 4.62581 2.30823C5.09878 2.06901 5.65734 2.06901 6.1303 2.30823C6.36812 2.42852 6.58956 2.64996 7.03242 3.09282L7.19482 3.25522C7.48615 3.54655 7.63182 3.69222 7.72706 3.8387C8.08622 4.39111 8.08622 5.10326 7.72706 5.65567C7.63182 5.80215 7.48615 5.94782 7.19482 6.23916C7.09956 6.33442 7.05192 6.38205 7.01206 6.43773C6.87038 6.63559 6.82146 6.92247 6.88957 7.1561C6.90873 7.22184 6.93368 7.2738 6.98357 7.37771C7.08426 7.58743 7.1913 7.79487 7.30469 7.99973M9.31808 10.6816L9.35553 10.7192C10.3568 11.7206 11.4891 12.5112 12.6971 13.0912C12.801 13.1411 12.8529 13.166 12.9187 13.1852C13.1523 13.2533 13.4392 13.2044 13.637 13.0627C13.6927 13.0228 13.7403 12.9752 13.8356 12.88C14.1269 12.5886 14.2726 12.4429 14.4191 12.3477C14.9715 11.9885 15.6837 11.9885 16.2361 12.3477C16.3825 12.4429 16.5282 12.5886 16.8196 12.88L16.9819 13.0423C17.4248 13.4852 17.6462 13.7066 17.7665 13.9445C18.0058 14.4174 18.0058 14.976 17.7665 15.449C17.6462 15.6868 17.4248 15.9082 16.9819 16.3511L16.8506 16.4824C16.4092 16.9238 16.1886 17.1445 15.8885 17.313C15.5556 17.5 15.0385 17.6345 14.6567 17.6334C14.3126 17.6323 14.0774 17.5656 13.607 17.4321C11.0792 16.7146 8.69387 15.3609 6.70388 13.3709L6.66647 13.3333M17.4997 2.50001L2.49968 17.5'
                    stroke='#F97066'
                    strokeWidth='1.67'
                    strokeLinecap='round'
                    strokeLinejoin='round'
                  />
                </svg>
                <span className={styles.endCallText}>End call</span>
              </button>
            ) : (
              <button className={styles.callBtn} onClick={handleStartCall} type='button'>
                <span className={styles.callText}>Call</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
