// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import styles from "./Header.module.css";

export type VoiceState = "listening" | "transcribing" | "speaking" | "idle";

interface CustomerInfo {
  name: string;
  phone: string;
  plan: string;
  status: "active" | "suspended";
}

interface HeaderProps {
  isLive?: boolean;
  isMicOn?: boolean;
  voiceState?: VoiceState;
  customer?: CustomerInfo;
  showCustomerInfo?: boolean;
}

function LiveBadge() {
  return (
    <div className={`${styles.badge} ${styles.badgeLive}`} aria-label='Live'>
      <svg
        className={styles.badgeIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='12'
        height='12'
        viewBox='0 0 12 12'
        fill='none'
        aria-hidden='true'
      >
        <path
          d='M8.12132 3.87869C9.29289 5.05026 9.29289 6.94976 8.12132 8.12133M3.87868 8.12131C2.70711 6.94974 2.70711 5.05025 3.87868 3.87867M2.46447 9.53555C0.511845 7.58292 0.511845 4.4171 2.46447 2.46448M9.53553 2.4645C11.4882 4.41712 11.4882 7.58295 9.53553 9.53557M7 6.00001C7 6.5523 6.55228 7.00001 6 7.00001C5.44772 7.00001 5 6.5523 5 6.00001C5 5.44773 5.44772 5.00001 6 5.00001C6.55228 5.00001 7 5.44773 7 6.00001Z'
          stroke='#F97066'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
      <span className={styles.badgeLiveText}>Live</span>
    </div>
  );
}

function ListeningBadge() {
  return (
    <div className={`${styles.badge} ${styles.badgeListening}`} aria-label='Listening'>
      <svg
        className={styles.badgeIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='12'
        height='12'
        viewBox='0 0 12 12'
        fill='none'
        aria-hidden='true'
      >
        <path
          d='M9.5 5V6C9.5 7.933 7.933 9.5 6 9.5M2.5 5V6C2.5 7.933 4.067 9.5 6 9.5M6 9.5V11M4 11H8M6 7.5C5.17157 7.5 4.5 6.82843 4.5 6V2.5C4.5 1.67157 5.17157 1 6 1C6.82843 1 7.5 1.67157 7.5 2.5V6C7.5 6.82843 6.82843 7.5 6 7.5Z'
          stroke='#0BA5EC'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
      <span className={styles.badgeListeningText}>Listening</span>
    </div>
  );
}

function MutedBadge() {
  return (
    <div className={`${styles.badge} ${styles.badgeMuted}`} aria-label='Muted'>
      <svg
        className={styles.badgeIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='12'
        height='12'
        viewBox='0 0 12 12'
        fill='none'
        aria-hidden='true'
      >
        <path
          d='M1 1L11 11M9.5 6.6C9.5 6.4 9.5 6.2 9.5 6V5M2.5 5V6C2.5 7.93 4.07 9.5 6 9.5M6 9.5V11M4 11H8M7.5 4.67V2.5C7.5 1.67 6.83 1 6 1C5.33 1 4.75 1.45 4.57 2.07M6 7.5C5.17 7.5 4.5 6.83 4.5 6V5L6.1 6.6'
          stroke='#94979C'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
      <span className={styles.badgeMutedText}>Muted</span>
    </div>
  );
}

export function Header({ isLive = true, isMicOn = true, customer, showCustomerInfo = true }: HeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <div className={styles.content}>
          <div className={styles.brandGroup}>
            <h1 className={styles.logo}>
              Tele<span className={styles.logoAccent}>assist</span>
            </h1>
            {isLive && (
              <div className={styles.stateBadges}>
                <LiveBadge />
                {isMicOn ? <ListeningBadge /> : <MutedBadge />}
              </div>
            )}
          </div>
          {showCustomerInfo && customer && customer.name && (
            <div className={styles.actions}>
              <div className={styles.customerInfo}>
                <span className={styles.customerName}>{customer.name}</span>
                {customer.phone && <span className={styles.customerPhone}>{customer.phone}</span>}
              </div>
              {(customer.plan || customer.status) && (
                <div className={styles.planBadges}>
                  {customer.plan && (
                    <div className={styles.planBadge}>
                      <span className={styles.planBadgeText}>{customer.plan}</span>
                    </div>
                  )}
                  <div className={styles.statusBadge}>
                    <span className={styles.statusBadgeText}>
                      {customer.status === "active" ? "Active" : "Suspended"}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
