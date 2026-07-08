// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useCallback, useEffect, useRef } from "react";
import { LiveKitRoom, RoomAudioRenderer, useRoomContext } from "@livekit/components-react";
import type { RpcInvocationData } from "livekit-client";
import { RpcError } from "livekit-client";
import type { ConnectionState } from "./types";
import { ConsoleLayout } from "./components/ConsoleLayout/ConsoleLayout";
import { RatingModal } from "./components/RatingModal/RatingModal";
import "./components/RatingModal/RatingModal.css";
import { Header } from "./components/Header/Header";
import { BottomBar } from "./components/BottomBar/BottomBar";
// import { CustomerProfile } from "./components/CustomerProfile/CustomerProfile";
import {
  ConversationPanelLivekit,
  type LocalUserMessage,
  type ToolEvent,
} from "./components/ConversationPanel/ConversationPanel";
import { ClientSimulator } from "./components/ClientSimulator/ClientSimulator";
import { ToolsPanel } from "./components/ToolsPanel/ToolsPanel";
import { ErrorScreen } from "./components/ErrorScreen/ErrorScreen";
import "./index.css";

interface ConnectionInfo {
  serverUrl: string;
  roomName: string;
  participantToken: string;
  participantName: string;
}

interface CustomerData {
  name: string;
  phone: string;
  plan: string;
  status: "active" | "suspended";
}

const DEFAULT_CUSTOMER: CustomerData = {
  name: "",
  phone: "",
  plan: "",
  status: "active",
};

const PASSPHRASE_PLAN_MAP: Record<string, string> = {
  milkyway: "Regular",
  mars: "Premium Plus",
};

function FunctionToolsRpcHandler({
                                   onUserAuthenticated,
                                   onUserAuthFailed,
                                 }: {
  onUserAuthenticated: (name: string) => void;
  onUserAuthFailed: () => void;
}) {
  const room = useRoomContext();

  useEffect(() => {
    if (!room) return;

    const handleUserAuthenticated = async (data: RpcInvocationData): Promise<string> => {
      try {
        const params = JSON.parse(data.payload as string);
        const name = params.UserName || "";

        if (!name) {
          onUserAuthFailed();
          throw new RpcError(1, "UserName is empty");
        }

        onUserAuthenticated(name);
        return "";
      } catch {
        onUserAuthFailed();
        throw new RpcError(1, "Could not retrieve user info");
      }
    };

    try {
      room.registerRpcMethod("userAuthenticated", handleUserAuthenticated);
    } catch (err) {
      console.warn("RPC registration failed", err);
      onUserAuthFailed();
    }

    return () => {
      try {
        room.unregisterRpcMethod("userAuthenticated");
      } catch {}
    };
  }, [room, onUserAuthenticated, onUserAuthFailed]);

  return null;
}

function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [connectionInfo, setConnectionInfo] = useState<ConnectionInfo | null>(null);
  const [lastError, setLastError] = useState("");

  const [isCallActive, setIsCallActive] = useState(false);
  const [isUserAuthenticated, setIsUserAuthenticated] = useState(false);
  const [customerData, setCustomerData] = useState<CustomerData>(DEFAULT_CUSTOMER);
  const detectedPlanRef = useRef("");
  const [micOn, setMicOn] = useState(true);
  const [showToolsPanel, setShowToolsPanel] = useState(false);
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([]);

  const [callSessionId, setCallSessionId] = useState(0);
  const [localUserMessages, setLocalUserMessages] = useState<LocalUserMessage[]>([]);
  const [showRatingModal, setShowRatingModal] = useState(false);
  const endSessionPendingRef = useRef(false);
  const endSessionRoomRef = useRef("");

  const handleConnect = useCallback(async () => {
    setConnectionState("connecting");
    setLastError("");
    setIsUserAuthenticated(false);

    try {
      const res = await fetch("/api/connection-details", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      if (!res.ok) throw new Error(await res.text());

      const data: ConnectionInfo = await res.json();
      setConnectionInfo(data);
      setIsCallActive(true);
      setConnectionState("live");
    } catch (e) {
      setLastError(e instanceof Error ? e.message : "Connection failed");
      setConnectionState("error");
      setIsCallActive(false);
    }
  }, []);

  useEffect(() => {
    handleConnect();
  }, [handleConnect]);

  const handleEndCall = useCallback(() => {
    setShowRatingModal(false);
    endSessionPendingRef.current = false;
    setIsCallActive(false);
    setIsUserAuthenticated(false);
    setCustomerData(DEFAULT_CUSTOMER);
    detectedPlanRef.current = "";
    setMicOn(true);
    setToolEvents([]);
    setLocalUserMessages([]);
    setCallSessionId((prev) => prev + 1);
  }, []);

  const handleStartCall = useCallback(async () => {
    await handleConnect();
  }, [handleConnect]);

  const handleLocalSendMessage = useCallback((text: string) => {
    const now = new Date();
    const day = new Intl.DateTimeFormat("en-US", { weekday: "long" }).format(now);
    const time = new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    })
        .format(now)
        .toLowerCase();

    setLocalUserMessages((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        text,
        timestamp: `${day} ${time}`,
      },
    ]);
  }, []);

  const handleEndSessionSignaled = useCallback((roomName: string) => {
    endSessionPendingRef.current = true;
    // Store room name for the modal (passed up from ClientSimulator)
    endSessionRoomRef.current = roomName;
  }, []);

  const handleAgentFinalTranscript = useCallback(() => {
    if (endSessionPendingRef.current) {
      endSessionPendingRef.current = false;
      setTimeout(() => setShowRatingModal(true), 2000);
    }
  }, []);

  const handleRatingSubmitted = useCallback(() => {
    setShowRatingModal(false);
    handleEndCall();
  }, [handleEndCall]);

  const handleToolExecuted = useCallback((event: ToolEvent) => {
    setToolEvents((prev) => [...prev, event]);

    // Extract plan from passphrase tool
    if (event.fn === "get_user_by_pass_phrase") {
      try {
        const parsed = JSON.parse(event.args);
        const passphrase = (parsed.pass_phrase || "").toLowerCase();
        const plan = PASSPHRASE_PLAN_MAP[passphrase];
        if (plan) {
          detectedPlanRef.current = plan;
          setCustomerData((prev) => ({ ...prev, plan }));
        }
      } catch {}
    }
  }, []);

  // const showCustomerUi = isCallActive && isUserAuthenticated;

  if (connectionState === "connecting" || connectionState === "disconnected") {
    return <div style={{ color: "var(--text-primary)", padding: "32px" }}>Connecting...</div>;
  }

  if (connectionState === "error") {
    return <ErrorScreen message={lastError} onRetry={handleConnect} />;
  }

  if (!connectionInfo) return null;

  return (
      <LiveKitRoom
          token={connectionInfo.participantToken}
          serverUrl={connectionInfo.serverUrl}
          connect={isCallActive}
          audio={true}
          onError={(err) => {
            setLastError(err?.message || "Connection lost");
            setConnectionState("error");
            setIsCallActive(false);
            setIsUserAuthenticated(false);
          }}
          onDisconnected={() => {
            setIsCallActive(false);
          }}
      >
        <FunctionToolsRpcHandler
            onUserAuthenticated={(name) => {
              setCustomerData({
                name,
                phone: "",
                plan: detectedPlanRef.current,
                status: "active",
              });
              setIsUserAuthenticated(true);
            }}
            onUserAuthFailed={() => setIsUserAuthenticated(false)}
        />

        <RoomAudioRenderer />

        <ConsoleLayout
            header={
              <Header
                  isLive={isCallActive}
                  isMicOn={micOn}
                  showCustomerInfo={isUserAuthenticated}
                  customer={customerData}
              />
            }
            bottomBar={isCallActive ? <BottomBar isAuthenticated={false} /> : null}
        >
          {showToolsPanel && <ToolsPanel tools={toolEvents} />}

          <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "24px",
                flex: "1 0 0",
                alignSelf: "stretch",
                minHeight: 0,
              }}
          >
            <ConversationPanelLivekit
                isCallActive={isCallActive}
                resetKey={callSessionId}
                localUserMessages={localUserMessages}
                hideSystemMessages={showToolsPanel}
                onToolExecuted={handleToolExecuted}
                onAgentFinalTranscript={handleAgentFinalTranscript}
            />
            <ClientSimulator
                isCallActive={isCallActive}
                micOn={micOn}
                onMicToggle={setMicOn}
                showToolsPanel={showToolsPanel}
                onToggleToolsPanel={setShowToolsPanel}
                onStartCall={handleStartCall}
                onEndCall={handleEndCall}
                onSendMessage={handleLocalSendMessage}
                onEndSessionSignaled={handleEndSessionSignaled}
                showRatingModal={showRatingModal}
            />
            {showRatingModal && (
                <RatingModal
                    roomName={endSessionRoomRef.current}
                    onRatingSubmitted={handleRatingSubmitted}
                />
            )}
          </div>
        </ConsoleLayout>
      </LiveKitRoom>
  );
}

export default App;
