// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useEffect, useRef, useState } from "react";
import styles from "./ConversationPanel.module.css";
import {
  RoomEvent,
  type Participant,
  type RpcInvocationData,
  type TrackPublication,
  type TranscriptionSegment,
} from "livekit-client";
import { useRoomContext } from "@livekit/components-react";

type MessageType = "customer" | "agent" | "system";

interface ChatMessage {
  id: string;
  type: MessageType;
  sender: string;
  text: string;
  timestamp: string;
  systemTitle?: string;
  isFinal?: boolean;
}

export interface LocalUserMessage {
  id: string;
  text: string;
  timestamp: string;
}

export interface ToolEvent {
  id: string;
  fn: string;
  args: string;
  output: string;
  isError: boolean;
  timestamp: string;
}

interface ConversationPanelProps {
  messages: ChatMessage[];
  hideSystemMessages?: boolean;
}

interface ConversationPanelLivekitProps {
  localUserMessages?: LocalUserMessage[];
  resetKey?: number;
  isCallActive?: boolean;
  hideSystemMessages?: boolean;
  onToolExecuted?: (event: ToolEvent) => void;
}

function formatTime(date = new Date()) {
  const day = new Intl.DateTimeFormat("en-US", { weekday: "long" }).format(date);
  const time = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  })
    .format(date)
    .toLowerCase();
  return `${day} ${time}`;
}

function parseParticipantRole(participant: Participant): MessageType {
  try {
    if (participant.metadata) {
      const md = JSON.parse(participant.metadata) as { role?: string };
      if (md.role === "agent") return "agent";
      if (md.role === "customer" || md.role === "user") return "customer";
    }
  } catch {}

  const identity = participant.identity?.toLowerCase() ?? "";
  const name = participant.name?.toLowerCase() ?? "";
  if (identity.includes("agent") || name.includes("agent")) return "agent";
  return "customer";
}

function CustomerAvatar() {
  return (
    <div className={`${styles.avatar} ${styles.avatarCustomer}`} aria-hidden='true'>
      <svg
        className={styles.avatarIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='20'
        height='20'
        viewBox='0 0 20 20'
        fill='none'
      >
        <path
          d='M16.6666 17.5C16.6666 16.337 16.6666 15.7555 16.5231 15.2824C16.1999 14.217 15.3663 13.3834 14.3009 13.0602C13.8278 12.9167 13.2463 12.9167 12.0833 12.9167H7.91665C6.75368 12.9167 6.17219 12.9167 5.69903 13.0602C4.63369 13.3834 3.80001 14.217 3.47685 15.2824C3.33331 15.7555 3.33331 16.337 3.33331 17.5M13.75 6.25C13.75 8.32107 12.071 10 9.99998 10C7.92891 10 6.24998 8.32107 6.24998 6.25C6.24998 4.17893 7.92891 2.5 9.99998 2.5C12.071 2.5 13.75 4.17893 13.75 6.25Z'
          stroke='#3CCB7F'
          strokeWidth='1.5'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
    </div>
  );
}

function AgentAvatar() {
  return (
    <div className={`${styles.avatar} ${styles.avatarAgent}`} aria-hidden='true'>
      <svg
        className={styles.avatarIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='20'
        height='20'
        viewBox='0 0 20 20'
        fill='none'
      >
        <path
          d='M16.6666 17.5C16.6666 16.337 16.6666 15.7555 16.5231 15.2824C16.1999 14.217 15.3663 13.3834 14.3009 13.0602C13.8278 12.9167 13.2463 12.9167 12.0833 12.9167H7.91665C6.75368 12.9167 6.17219 12.9167 5.69903 13.0602C4.63369 13.3834 3.80001 14.217 3.47685 15.2824C3.33331 15.7555 3.33331 16.337 3.33331 17.5M13.75 6.25C13.75 8.32107 12.071 10 9.99998 10C7.92891 10 6.24998 8.32107 6.24998 6.25C6.24998 4.17893 7.92891 2.5 9.99998 2.5C12.071 2.5 13.75 4.17893 13.75 6.25Z'
          stroke='#36BFFA'
          strokeWidth='1.5'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
    </div>
  );
}

function SystemAlertIcon() {
  return (
    <div className={styles.alertIconWrap} aria-hidden='true'>
      <div className={styles.alertIconOuter} />
      <div className={styles.alertIconInner} />
      <svg
        className={styles.alertIcon}
        xmlns='http://www.w3.org/2000/svg'
        width='20'
        height='20'
        viewBox='0 0 20 20'
        fill='none'
      >
        <path
          d='M10 13.3334V10M10 6.66669H10.0084M18.3334 10C18.3334 14.6024 14.6024 18.3334 10 18.3334C5.39765 18.3334 1.66669 14.6024 1.66669 10C1.66669 5.39765 5.39765 1.66669 10 1.66669C14.6024 1.66669 18.3334 5.39765 18.3334 10Z'
          stroke='#36BFFA'
          strokeWidth='1.66667'
          strokeLinecap='round'
          strokeLinejoin='round'
        />
      </svg>
    </div>
  );
}

export function ConversationPanel({ messages, hideSystemMessages = false }: ConversationPanelProps) {
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages]);

  const visibleMessages = hideSystemMessages ? messages.filter((m) => m.type !== "system") : messages;

  return (
    <div className={styles.card}>
      <div className={styles.content}>
        <header className={styles.header}>
          <div className={styles.headerInner}>
            <div className={styles.titleWrap}>
              <h2 className={styles.title}>Conversation</h2>
            </div>
          </div>
          <hr className={styles.divider} />
        </header>

        <div className={styles.body} ref={bodyRef} role='log' aria-live='polite'>
          {visibleMessages.map((msg) =>
            msg.type === "system" ? (
              <div className={styles.systemAlert} key={msg.id} role='status'>
                <SystemAlertIcon />
                <div className={styles.alertContent}>
                  <div className={styles.alertTextGroup}>
                    <p className={styles.alertTitle}>{msg.systemTitle}</p>
                    <p className={styles.alertDescription}>{msg.text}</p>
                  </div>
                </div>
              </div>
            ) : (
              <article className={styles.message} key={msg.id}>
                {msg.type === "customer" ? <CustomerAvatar /> : <AgentAvatar />}
                <div className={styles.messageContent}>
                  <div className={styles.messageHeader}>
                    <span className={styles.speakerName}>{msg.sender}</span>
                    <time className={styles.messageTime}>{msg.timestamp}</time>
                  </div>
                  <p
                    className={`${styles.bubble} ${
                      msg.type === "customer" ? styles.bubbleCustomer : styles.bubbleAgent
                    }`}
                  >
                    {msg.text}
                  </p>
                </div>
              </article>
            ),
          )}
        </div>
      </div>
    </div>
  );
}

export function ConversationPanelLivekit({
  localUserMessages = [],
  resetKey,
  isCallActive = true,
  hideSystemMessages = false,
  onToolExecuted,
}: ConversationPanelLivekitProps) {
  const room = useRoomContext();
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  useEffect(() => {
    if (!isCallActive) setMessages([]);
  }, [isCallActive]);

  useEffect(() => {
    setMessages([]);
  }, [resetKey]);

  useEffect(() => {
    if (!localUserMessages.length) return;

    setMessages((prev) => {
      const next = [...prev];
      for (const m of localUserMessages) {
        if (next.some((x) => x.id === m.id)) continue;
        next.push({
          id: m.id,
          type: "customer",
          sender: "You",
          text: m.text,
          timestamp: m.timestamp,
          isFinal: true,
        });
      }
      return next;
    });
  }, [localUserMessages]);

  // RPC tool events -> added to chat as system messages AND routed to ToolsPanel
  useEffect(() => {
    if (!room) return;

    const handleFunctionToolsExecuted = async (data: RpcInvocationData): Promise<string> => {
      try {
        const payload = JSON.parse(data.payload as string);
        const fn = payload.Function || "<unknown>";
        const rawArgs = typeof payload.Arguments === "string" ? payload.Arguments : "";
        const out = typeof payload.Output === "string" ? payload.Output : JSON.stringify(payload.Output ?? "");
        const isError = !!payload.IsError;
        const errFlag = isError ? " (error)" : "";

        // Always add to messages (visibility controlled by hideSystemMessages prop)
        setMessages((prev) => [
          ...prev,
          {
            id: `sys-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            type: "system",
            sender: "System",
            systemTitle: `Tool executed: ${fn}${errFlag}`,
            text: out,
            timestamp: formatTime(),
          },
        ]);

        // Also route to ToolsPanel
        onToolExecuted?.({
          id: `tool-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          fn,
          args: rawArgs,
          output: out,
          isError,
          timestamp: formatTime(),
        });

        return "";
      } catch (error) {
        console.warn("failed to parse functionToolsExecuted payload", error);
        return "";
      }
    };

    try {
      room.registerRpcMethod("functionToolsExecuted", handleFunctionToolsExecuted);
    } catch (err) {
      console.warn("RPC registration failed", err);
    }

    return () => {
      try {
        room.unregisterRpcMethod("functionToolsExecuted");
      } catch {}
    };
  }, [room, onToolExecuted]);

  useEffect(() => {
    if (!room) return;

    const onTranscriptionReceived = (
      segments: TranscriptionSegment[],
      participant?: Participant,
      _publication?: TrackPublication,
    ) => {
      if (!participant) return;

      setMessages((prev) => {
        const next = [...prev];

        for (const seg of segments) {
          const id = `${participant.identity}:${seg.id}`;
          const idx = next.findIndex((m) => m.id === id);

          const updated: ChatMessage = {
            id,
            type: parseParticipantRole(participant),
            sender: participant.name || participant.identity || "Unknown",
            text: seg.text,
            timestamp: formatTime(),
            isFinal: !!seg.final,
          };

          if (idx >= 0) next[idx] = { ...next[idx], ...updated };
          else next.push(updated);
        }

        return next;
      });
    };

    room.on(RoomEvent.TranscriptionReceived, onTranscriptionReceived);
    return () => {
      room.off(RoomEvent.TranscriptionReceived, onTranscriptionReceived);
    };
  }, [room]);

  return <ConversationPanel messages={messages} hideSystemMessages={hideSystemMessages} />;
}
