// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

require("dotenv").config();
const express = require("express");
const path = require("path");
const { AccessToken } = require("livekit-server-sdk");

const app = express();
app.use(express.json());

const { LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, PORT = "3000" } = process.env;

app.post("/api/connection-details", async (req, res) => {
  if (!LIVEKIT_URL || !LIVEKIT_API_KEY || !LIVEKIT_API_SECRET) {
    return res.status(500).json({ error: "LiveKit env vars not configured" });
  }

  const agentName = req.body?.room_config?.agents?.[0]?.agent_name;
  const participantIdentity = `voice_assistant_user_${Math.floor(Math.random() * 10_000)}`;
  const roomName = `voice_assistant_room_${Math.floor(Math.random() * 10_000)}`;

  const at = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
    identity: participantIdentity,
    name: "user",
    ttl: "15m",
  });

  at.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  });

  if (agentName) {
    at.roomConfig = { agents: [{ agentName }] };
  }

  const token = await at.toJwt();

  res.json({
    serverUrl: LIVEKIT_URL,
    roomName,
    participantToken: token,
    participantName: "user",
  });
});

// In production, serve the built Vite app
const clientDist = path.join(__dirname, "../dist");
app.use(express.static(clientDist));
app.get("/{*path}", (_req, res) => {
  res.sendFile(path.join(clientDist, "index.html"));
});

app.listen(Number(PORT), "0.0.0.0", () => {
  console.log(`Server running on port ${PORT}`);
});
