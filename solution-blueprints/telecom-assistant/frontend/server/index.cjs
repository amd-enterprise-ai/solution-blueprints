// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

require("dotenv").config();
const express = require("express");
const path = require("path");
const { AccessToken } = require("livekit-server-sdk");

const app = express();

const {
  LIVEKIT_API_KEY,
  LIVEKIT_API_SECRET,
  LIVEKIT_URL,
  PORT = "3000",
  AGENT_URL
} = process.env;

console.log(`[STARTUP] AGENT_URL: ${AGENT_URL}`);

// Proxy for /agent - handles file uploads (multipart/form-data)
app.use("/agent", async (req, res) => {
  if (!AGENT_URL) {
    return res.status(500).json({ error: "AGENT_URL env var not configured" });
  }

  let agentHost;
  try {
    agentHost = new URL(AGENT_URL).host;
  } catch (e) {
    return res.status(500).json({ error: "Invalid AGENT_URL", message: e.message });
  }

  // Preserve the full original path including /agent
  const originalPath = req.originalUrl;

  console.log(`[PROXY] ${req.method} ${originalPath}`);
  console.log(`[PROXY] Target: ${AGENT_URL}${originalPath}`);

  try {
    const targetUrl = `${AGENT_URL}${originalPath}`;

    const fetchOptions = {
      method: req.method,
      headers: {
        ...req.headers,
        host: agentHost,
      },
    };

    if (req.method !== 'GET' && req.method !== 'HEAD') {
      fetchOptions.body = req;
      fetchOptions.duplex = 'half';
    }

    delete fetchOptions.headers['host'];
    delete fetchOptions.headers['content-length'];

    const response = await fetch(targetUrl, fetchOptions);

    console.log(`[PROXY] Response status: ${response.status}`);

    const responseBody = await response.arrayBuffer();

    response.headers.forEach((value, key) => {
      if (key !== 'content-encoding' && key !== 'content-length') {
        res.setHeader(key, value);
      }
    });

    res.status(response.status);
    res.send(Buffer.from(responseBody));
  } catch (error) {
    console.error('[PROXY] Error:', error);
    res.status(500).json({ error: 'Proxy failed', message: error.message });
  }
});

app.post("/api/connection-details", express.json(), async (req, res) => {
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

app.use((req, res) => {
  res.sendFile(path.join(clientDist, "index.html"));
});

app.listen(Number(PORT), "0.0.0.0", () => {
  console.log(`Server running on port ${PORT}`);
});
