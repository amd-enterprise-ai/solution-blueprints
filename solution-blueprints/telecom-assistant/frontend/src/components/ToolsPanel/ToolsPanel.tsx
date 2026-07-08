// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

import { Fragment } from "react";
import type { ToolEvent } from "../ConversationPanel/ConversationPanel";
import styles from "./ToolsPanel.module.css";

/* ---- Original mock types and data ---- */

// type ToolStatus = "ready" | "running" | "success" | "failed";
//
// interface Tool {
//   id: string;
//   name: string;
//   result?: string;
//   status: ToolStatus;
// }
//
// const MOCK_TOOLS: Tool[] = [
//   {
//     id: "1",
//     name: "billing.get_balance",
//     result: "$45.32",
//     status: "success",
//   },
//   {
//     id: "2",
//     name: "billing.get_plan",
//     result: "Premium Plus",
//     status: "success",
//   },
//   {
//     id: "3",
//     name: "roaming.get_usage",
//     result: "2.1GB / 5GB",
//     status: "success",
//   },
//   {
//     id: "4",
//     name: "plan.add_roaming_boost",
//     status: "ready",
//   },
//   {
//     id: "5",
//     name: "ticket.create",
//     status: "ready",
//   },
//   {
//     id: "6",
//     name: "routing.transfer",
//     status: "ready",
//   },
// ];

interface ToolsPanelProps {
  tools: ToolEvent[];
  // onRun?: (id: string) => void;
}

function ToolOutputContent({ output }: { output: string }) {
  const trimmed = output.trim();

  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      const pretty = JSON.stringify(parsed, null, 2);
      return <pre className={styles.alertOutputPre}>{pretty}</pre>;
    } catch {}
  }

  const html = renderImprovedMarkdown(trimmed);
  return (
      <div
          className={styles.alertOutputMarkdown}
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: html }}
      />
  );
}

function renderImprovedMarkdown(text: string): string {
  const fenceMatch = text.match(/^```[^\n]*\n([\s\S]*?)```\s*$/);
  if (fenceMatch) text = fenceMatch[1];

  let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

  html = html.replace(/\*\*(.+?)\*\*/gs, "<strong>$1</strong>");
  html = html.replace(/__(.+?)__/gs, "<strong>$1</strong>");
  html = html.replace(/\*([^*\n]+?)\*/g, "<em>$1</em>");
  html = html.replace(/_([^_\n]+?)_/g, "<em>$1</em>");
  html = html.replace(/`([^`]+)`/g, `<code style="background:rgba(54,191,250,0.15);padding:1px 4px;border-radius:3px;">$1</code>`);

  const lines = html.split("\n");
  const result: string[] = [];
  let inList = false;
  let listType: "ul" | "ol" | null = null;

  for (const line of lines) {
    if (line.trim() === "") {
      result.push('<div style="height:8px;"></div>');
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      if (!inList) {
        result.push('<ul style="margin:8px 0; padding-left:20px;">');
        inList = true;
        listType = "ul";
      }
      const content = line.replace(/^[-*]\s+/, "");
      result.push(`<li style="margin:4px 0;">${content}</li>`);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      if (!inList) {
        result.push('<ol style="margin:8px 0; padding-left:20px;">');
        inList = true;
        listType = "ol";
      }
      const content = line.replace(/^\d+\.\s+/, "");
      result.push(`<li style="margin:4px 0;">${content}</li>`);
      continue;
    }

    if (inList) {
      result.push(listType === "ol" ? "</ol>" : "</ul>");
      inList = false;
      listType = null;
    }

    if (line.startsWith("### ")) {
      result.push(`<h3 style="margin:12px 0 6px 0; color:#36bffa;">${line.slice(4)}</h3>`);
      continue;
    }
    if (line.startsWith("#")) {
      result.push(`<h2 style="margin:14px 0 8px 0; color:#36bffa;">${line.replace(/^#+\s+/, "")}</h2>`);
      continue;
    }

    result.push(`<p style="margin:6px 0; white-space:pre-wrap;">${line}</p>`);
  }

  if (inList) result.push(listType === "ol" ? "</ol>" : "</ul>");

  return result.join("");
}

function CheckIcon() {
  return (
      <svg
          className={styles.checkIcon}
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          aria-label="Completed"
      >
        <path
            d="M6.24996 10L8.74996 12.5L13.75 7.50001M18.3333 10C18.3333 14.6024 14.6023 18.3333 9.99996 18.3333C5.39759 18.3333 1.66663 14.6024 1.66663 10C1.66663 5.39763 5.39759 1.66667 9.99996 1.66667C14.6023 1.66667 18.3333 5.39763 18.3333 10Z"
            stroke="#3CCB7F"
            strokeWidth="1.25"
            strokeLinecap="round"
            strokeLinejoin="round"
        />
      </svg>
  );
}

function ErrorIcon() {
  return (
      <svg
          className={styles.checkIcon}
          xmlns="http://www.w3.org/2000/svg"
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          aria-label="Error"
      >
        <path
            d="M10 6.66669V10M10 13.3334H10.0084M18.3334 10C18.3334 14.6024 14.6024 18.3334 10 18.3334C5.39765 18.3334 1.66669 14.6024 1.66669 10C1.66669 5.39765 5.39765 1.66669 10 1.66669C14.6024 1.66669 18.3334 5.39765 18.3334 10Z"
            stroke="#F97066"
            strokeWidth="1.25"
            strokeLinecap="round"
            strokeLinejoin="round"
        />
      </svg>
  );
}

/* ---- Original button icons ---- */

// function PlayIcon() {
//   return (
//     <svg
//       className={styles.runBtnIcon}
//       xmlns="http://www.w3.org/2000/svg"
//       width="20"
//       height="20"
//       viewBox="0 0 20 20"
//       fill="none"
//       aria-hidden="true"
//     >
//       <path
//         d="M4.16663 4.15803C4.16663 3.34873 4.16663 2.94407 4.33537 2.72101C4.48237 2.52669 4.70706 2.40644 4.95029 2.39192C5.22949 2.37525 5.56618 2.59971 6.23956 3.04863L15.0025 8.89061C15.5589 9.26154 15.8371 9.44701 15.9341 9.68078C16.0188 9.88516 16.0188 10.1149 15.9341 10.3192C15.8371 10.553 15.5589 10.7385 15.0025 11.1094L6.23956 16.9514C5.56618 17.4003 5.22949 17.6248 4.95029 17.6081C4.70706 17.5936 4.48237 17.4733 4.33537 17.279C4.16663 17.0559 4.16663 16.6513 4.16663 15.842V4.15803Z"
//         stroke="#36BFFA"
//         strokeWidth="1.66667"
//         strokeLinecap="round"
//         strokeLinejoin="round"
//       />
//     </svg>
//   );
// }
//
// function InfoIcon() {
//   return (
//     <svg
//       className={styles.infoBtnIcon}
//       xmlns="http://www.w3.org/2000/svg"
//       width="20"
//       height="20"
//       viewBox="0 0 20 20"
//       fill="none"
//       aria-hidden="true"
//     >
//       <path
//         d="M10 13.3333V10M10 6.66667H10.0083M6.5 17.5H13.5C14.9001 17.5 15.6002 17.5 16.135 17.2275C16.6054 16.9878 16.9878 16.6054 17.2275 16.135C17.5 15.6002 17.5 14.9001 17.5 13.5V6.5C17.5 5.09987 17.5 4.3998 17.2275 3.86502C16.9878 3.39462 16.6054 3.01217 16.135 2.77248C15.6002 2.5 14.9001 2.5 13.5 2.5H6.5C5.09987 2.5 4.3998 2.5 3.86502 2.77248C3.39462 3.01217 3.01217 3.39462 2.77248 3.86502C2.5 4.3998 2.5 5.09987 2.5 6.5V13.5C2.5 14.9001 2.5 15.6002 2.77248 16.135C3.01217 16.6054 3.39462 16.9878 3.86502 17.2275C4.3998 17.5 5.09987 17.5 6.5 17.5Z"
//         stroke="#36BFFA"
//         strokeWidth="1.66667"
//         strokeLinecap="round"
//         strokeLinejoin="round"
//       />
//     </svg>
//   );
// }

export function ToolsPanel({ tools }: ToolsPanelProps) {
  return (
      <div className={styles.wrapper}>
        <aside className={styles.card} aria-label="Tool executions">
          <div className={styles.content}>
            <header className={styles.header}>
              <div className={styles.headerInner}>
                <h2 className={styles.title}>Tool execution history</h2>
              </div>
              <hr className={styles.divider} />
            </header>

            <div className={styles.body} role="log">
              {tools.length === 0 && <p className={styles.emptyText}>No tools executed yet</p>}

              {tools.map((tool, i) => (
                  <Fragment key={tool.id}>
                    {i > 0 && <hr className={styles.divider} />}

                    <article className={styles.toolCard}>
                      <div className={styles.toolContent}>
                        <div className={styles.toolHeadingRow}>
                          <div className={styles.toolNameRow}>
                            <span className={styles.toolName}>{tool.fn}</span>
                            {tool.isError ? <ErrorIcon /> : <CheckIcon />}
                          </div>
                        </div>

                        <div className={styles.alertDescription}>
                          <ToolOutputContent output={tool.output} />
                        </div>
                      </div>
                    </article>
                  </Fragment>
              ))}
            </div>
          </div>
        </aside>
      </div>
  );
}
