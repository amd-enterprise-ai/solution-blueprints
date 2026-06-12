// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useCallback, useEffect } from "react";
import { LiveKitRoom, RoomAudioRenderer } from "@livekit/components-react";
import { useToken } from "./hooks/useToken";
import { RoleSelect } from "./components/RoleSelect/RoleSelect";
import { ConnectingScreen } from "./components/ConnectingScreen/ConnectingScreen";
import { ErrorScreen } from "./components/ErrorScreen/ErrorScreen";
import { DoctorConsole } from "./components/DoctorConsole/DoctorConsole";
import type { ConnectionState } from "./types";
import "@livekit/components-styles";
import "./index.css";

function App() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const { connectionInfo, error, connect, disconnect } = useToken();
  const [lastError, setLastError] = useState<string>("");

  const handleConnect = useCallback(async () => {
    setConnectionState("connecting");
    setLastError("");
    try {
      await connect("doctor");
    } catch (e) {
      setLastError(e instanceof Error ? e.message : "Connection failed");
      setConnectionState("error");
    }
  }, [connect]);

  // Watch for token fetch results
  // If we're in connecting state and get connectionInfo, move to live
  // If we get an error, move to error state
  if (connectionState === "connecting" && connectionInfo) {
    // Will render LiveKitRoom which handles the actual WebRTC connection
  }

  const handleDisconnect = useCallback(() => {
    disconnect();
    setConnectionState("disconnected");
    setLastError("");
  }, [disconnect]);

  const handleRetry = useCallback(() => {
    handleConnect();
  }, [handleConnect]);

  useEffect(() => {
    if (connectionState === "connecting" && error && lastError !== error) {
      setLastError(error);
      setConnectionState("error");
    }
  }, [connectionState, error, lastError]);

  // Disconnected — show sign-in
  if (connectionState === "disconnected") {
    return <RoleSelect onSelect={() => handleConnect()} loading={false} error={null} />;
  }

  // Connecting — waiting for token
  if (connectionState === "connecting" && !connectionInfo) {
    return <ConnectingScreen />;
  }

  // Error
  if (connectionState === "error") {
    return (
      <ErrorScreen
        error={lastError || "Unable to connect to session. Please try again."}
        onRetry={handleRetry}
        onBack={handleDisconnect}
      />
    );
  }

  // Live — have token, connect to room
  if (connectionInfo) {
    return (
      <LiveKitRoom
        token={connectionInfo.token}
        serverUrl={connectionInfo.wsUrl}
        connect={true}
        audio={true}
        onDisconnected={handleDisconnect}
        onError={(err) => {
          setLastError(err?.message || "Connection lost");
          setConnectionState("error");
        }}
      >
        <RoomAudioRenderer />
        <DoctorConsole />
      </LiveKitRoom>
    );
  }

  // Fallback
  return <ConnectingScreen />;
}

export default App;
