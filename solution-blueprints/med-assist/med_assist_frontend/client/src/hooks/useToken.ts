// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { useState, useCallback } from "react";

interface ConnectionInfo {
  token: string;
  wsUrl: string;
}

export function useToken() {
  const [connectionInfo, setConnectionInfo] = useState<ConnectionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connect = useCallback(async (role: "doctor" | "patient") => {
    setError(null);
    setConnectionInfo(null);
    try {
      const [wsRes, tokenRes] = await Promise.all([fetch("/api/ws-url"), fetch(`/api/token?role=${role}`)]);

      if (!wsRes.ok || !tokenRes.ok) {
        throw new Error("Failed to get connection info from server");
      }

      const wsData = await wsRes.json();
      const tokenData = await tokenRes.json();

      const info = {
        wsUrl: wsData.wsUrl,
        token: tokenData.token,
      };
      setConnectionInfo(info);
      return info;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Connection failed";
      setError(msg);
      throw e;
    }
  }, []);

  const disconnect = useCallback(() => {
    setConnectionInfo(null);
    setError(null);
  }, []);

  return { connectionInfo, error, connect, disconnect };
}
