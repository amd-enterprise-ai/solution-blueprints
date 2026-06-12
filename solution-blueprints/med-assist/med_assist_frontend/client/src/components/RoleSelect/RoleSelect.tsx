// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useEffect } from "react";
import styles from "./RoleSelect.module.css";

interface RoleSelectProps {
  onSelect: (role: "doctor" | "patient") => void;
  loading: boolean;
  error: string | null;
}

export function RoleSelect({ onSelect, loading, error }: RoleSelectProps) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDevice, setSelectedDevice] = useState<string>("");
  const [micError, setMicError] = useState<string | null>(null);

  useEffect(() => {
    async function getMicrophones() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        stream.getTracks().forEach((t) => t.stop());

        const allDevices = await navigator.mediaDevices.enumerateDevices();
        const mics = allDevices.filter((d) => d.kind === "audioinput");
        setDevices(mics);
        if (mics.length > 0 && !selectedDevice) {
          setSelectedDevice(mics[0].deviceId);
        }
      } catch {
        setMicError("Microphone access denied. Please allow microphone access and refresh the page.");
      }
    }
    getMicrophones();
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.left}>
        <div className={styles.leftInner}>
          <div className={styles.form}>
            <div className={styles.logo}>
              <span className={styles.logoMed}>MED</span>
              <span className={styles.logoAssist}>ASSIST</span>
            </div>

            <div className={styles.fieldGroup}>
              <label className={styles.label}>
                Microphone
                <span className={styles.labelIcon}>
                  <svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16' fill='none'>
                    <g clipPath='url(#clip0_mic_info)'>
                      <path
                        d='M6.06016 6.00001C6.2169 5.55446 6.52626 5.17875 6.93347 4.93943C7.34067 4.70012 7.81943 4.61264 8.28495 4.69248C8.75047 4.77233 9.17271 5.01436 9.47688 5.3757C9.78105 5.73703 9.94753 6.19436 9.94683 6.66668C9.94683 8.00001 7.94683 8.66668 7.94683 8.66668M8.00016 11.3333H8.00683M14.6668 8.00001C14.6668 11.6819 11.6821 14.6667 8.00016 14.6667C4.31826 14.6667 1.3335 11.6819 1.3335 8.00001C1.3335 4.31811 4.31826 1.33334 8.00016 1.33334C11.6821 1.33334 14.6668 4.31811 14.6668 8.00001Z'
                        stroke='#61656C'
                        strokeWidth='1.33333'
                        strokeLinecap='round'
                        strokeLinejoin='round'
                      />
                    </g>
                    <defs>
                      <clipPath id='clip0_mic_info'>
                        <rect width='16' height='16' fill='white' />
                      </clipPath>
                    </defs>
                  </svg>
                </span>
              </label>
              <select
                className={`${styles.select} ${selectedDevice ? styles.selectActive : ""}`}
                value={selectedDevice}
                onChange={(e) => setSelectedDevice(e.target.value)}
                disabled={devices.length === 0}
              >
                {devices.length === 0 && <option value=''>Select a microphone</option>}
                {devices.map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label || `Microphone ${devices.indexOf(d) + 1}`}
                  </option>
                ))}
              </select>
              <div className={styles.hint}>Select your audio input device.</div>
            </div>

            <button
              className={styles.connectBtn}
              onClick={() => onSelect("doctor")}
              disabled={loading || devices.length === 0}
            >
              {loading ? "Connecting…" : "Connect as doctor"}
            </button>

            {(error || micError) && <div className={styles.error}>{error || micError}</div>}
          </div>
        </div>

        <span className={styles.copyright}>© MedAssist 2026</span>
        <a href='mailto:help@medassist.com' className={styles.email}>
          <svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16' fill='none'>
            <path
              d='M1.3335 4.66666L6.77678 8.47696C7.21756 8.78551 7.43795 8.93978 7.67767 8.99954C7.88943 9.05232 8.1109 9.05232 8.32265 8.99954C8.56238 8.93978 8.78277 8.78551 9.22355 8.47696L14.6668 4.66666M4.5335 13.3333H11.4668C12.5869 13.3333 13.147 13.3333 13.5748 13.1153C13.9511 12.9236 14.2571 12.6176 14.4488 12.2413C14.6668 11.8135 14.6668 11.2534 14.6668 10.1333V5.86666C14.6668 4.74656 14.6668 4.18651 14.4488 3.75868C14.2571 3.38236 13.9511 3.0764 13.5748 2.88465C13.147 2.66666 12.5869 2.66666 11.4668 2.66666H4.5335C3.41339 2.66666 2.85334 2.66666 2.42552 2.88465C2.04919 3.0764 1.74323 3.38236 1.55148 3.75868C1.3335 4.18651 1.3335 4.74656 1.3335 5.86666V10.1333C1.3335 11.2534 1.3335 11.8135 1.55148 12.2413C1.74323 12.6176 2.04919 12.9236 2.42552 13.1153C2.85334 13.3333 3.41339 13.3333 4.5335 13.3333Z'
              stroke='#61656C'
              strokeWidth='1.33333'
              strokeLinecap='round'
              strokeLinejoin='round'
            />
          </svg>
          help@medassist.com
        </a>
      </div>

      <div className={styles.right} />
    </div>
  );
}
