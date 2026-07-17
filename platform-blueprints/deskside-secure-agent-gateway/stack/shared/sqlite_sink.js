// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Shared SQLite audit sink used by both the tool plane (axis_mcp_connector) and
// the inference plane (lemonade_proxy).
//
// Both planes write to the SAME database file (AUDIT_DB) from separate processes,
// so the sink opens in WAL journal mode with a busy_timeout — WAL lets a reader
// and a writer coexist, and the busy_timeout makes a concurrent writer wait for
// the lock instead of throwing SQLITE_BUSY and silently dropping an audit event.
//
// The constructor is fail-soft: if the DB can't be opened (bad path, read-only
// dir, disk full) the sink degrades to a no-op that never throws, so an audit
// misconfiguration can never crash the process that owns a request path. Whether
// the sink is actually recording is exposed via ok() so callers can surface it.
//
// Schema (one table, shared by both planes):
//   events (id INTEGER PRIMARY KEY AUTOINCREMENT,
//           time REAL, event TEXT, session TEXT, data TEXT)

import Database from "better-sqlite3";

const DEFAULT_DB = "./audit.db";

export class SqliteSink {
  #db = null;
  #insert = null;
  #dbPath;

  constructor({ dbPath } = {}) {
    this.#dbPath = dbPath || process.env.AUDIT_DB || DEFAULT_DB;
    try {
      this.#db = new Database(this.#dbPath);
      // WAL + busy_timeout: two processes (connector + proxy) share this file.
      this.#db.pragma("journal_mode = WAL");
      this.#db.pragma("busy_timeout = 5000");
      this.#db.exec(`
        CREATE TABLE IF NOT EXISTS events (
          id      INTEGER PRIMARY KEY AUTOINCREMENT,
          time    REAL,
          event   TEXT,
          session TEXT,
          data    TEXT
        )
      `);
      this.#insert = this.#db.prepare(
        "INSERT INTO events (time, event, session, data) VALUES (?, ?, ?, ?)",
      );
    } catch (e) {
      // Fail-soft: degrade to a no-op sink; never crash the request path.
      this.#db = null;
      this.#insert = null;
      console.error("[sqlite-sink] init failed:", e.message || e);
    }
  }

  /** True if the sink actually opened its DB and can record events. */
  ok() {
    return this.#insert !== null;
  }

  /** Insert one event synchronously. Never throws. */
  emit(event) {
    try {
      if (this.#insert) {
        this.#insert.run(
          event.time ?? Date.now() / 1000,
          event.event ?? "unknown",
          event.identity?.session ?? null,
          JSON.stringify(event),
        );
      }
    } catch (e) {
      console.error("[sqlite-sink] emit failed:", e.message || e);
    }
    return event;
  }

  /** Close the DB handle (checkpoints WAL). Safe to call multiple times. */
  close() {
    try {
      if (this.#db) {
        this.#db.close();
        this.#db = null;
        this.#insert = null;
      }
    } catch {
      /* best-effort */
    }
  }
}
