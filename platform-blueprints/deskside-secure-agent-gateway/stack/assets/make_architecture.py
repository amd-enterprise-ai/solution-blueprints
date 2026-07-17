#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Regenerate stack/assets/architecture.png.

Two-plane governance diagram. The SQLite audit DB is drawn as a standalone sink that sits
OUTSIDE both the inference plane and the tool/audit plane, with arrows showing
that both the lemonade_proxy and the axis MCP connector report to it.
"""
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import (  # noqa: E402
    FancyArrowPatch,
    FancyBboxPatch,
    PathPatch,
)
from matplotlib.path import Path  # noqa: E402

# ---------------------------------------------------------------- palette
BLUE_E, BLUE_F, BLUE_T = "#4a90d9", "#eaf2fc", "#1f6fd4"
GREEN_E, GREEN_F, GREEN_T = "#57ab5a", "#eaf7ee", "#2f9e44"
ORANGE_E, ORANGE_F = "#e8823a", "#fdf0e6"
PURPLE_E, PURPLE_F = "#7048e8", "#f0ebfb"
BANNER_E, BANNER_F = "#e8823a", "#fdf3e3"
GREY_E, DARK = "#8a94a6", "#3b4252"
AUDIT, INK = "#5aa02c", "#242a33"

W, H = 1100, 812
fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.set_aspect("equal")
ax.axis("off")


def rbox(x0, y0, x1, y1, edge, face, lw=2.0, rnd=11, z=1):
    ax.add_patch(
        FancyBboxPatch(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            boxstyle=f"round,pad=0,rounding_size={rnd}",
            linewidth=lw,
            edgecolor=edge,
            facecolor=face,
            zorder=z,
        )
    )


def icon(cx, cy, color, glyph=""):
    ax.add_patch(
        FancyBboxPatch(
            (cx - 11, cy - 11), 22, 22, boxstyle="round,pad=0,rounding_size=6", linewidth=0, facecolor=color, zorder=6
        )
    )
    if glyph:
        ax.text(
            cx,
            cy - 0.5,
            glyph,
            ha="center",
            va="center",
            color="white",
            fontsize=9,
            fontweight="bold",
            family="monospace",
            zorder=7,
        )


def card(x0, y0, x1, y1, edge, accent, title, body, glyph="", face="white", tsize=11, bsize=9):
    rbox(x0, y0, x1, y1, edge, face, lw=2.0, z=3)
    icon(x0 + 20, y1 - 19, accent, glyph)
    ax.text(x0 + 38, y1 - 13, title, ha="left", va="top", fontsize=tsize, fontweight="bold", color=accent, zorder=7)
    ax.text(
        x0 + 15,
        y1 - 39,
        body,
        ha="left",
        va="top",
        fontsize=bsize,
        color=INK,
        family="monospace",
        linespacing=1.45,
        zorder=7,
    )


def arrow(pts, color, lw=2.2, scale=16, z=8):
    verts = list(pts)
    codes = [Path.MOVETO] + [Path.LINETO] * (len(verts) - 1)
    ax.add_patch(
        PathPatch(Path(verts, codes), fill=False, edgecolor=color, lw=lw, joinstyle="round", capstyle="round", zorder=z)
    )
    ax.add_patch(
        FancyArrowPatch(
            verts[-2],
            verts[-1],
            arrowstyle="-|>",
            mutation_scale=scale,
            color=color,
            lw=lw,
            shrinkA=0,
            shrinkB=0,
            zorder=z,
        )
    )


# ---------------------------------------------------------------- title
ax.text(
    W / 2,
    H - 32,
    "Client-Side Integration: Two-Plane Governance Model",
    ha="center",
    va="center",
    fontsize=20,
    fontweight="bold",
    color="#1b2733",
)

# ---------------------------------------------------------------- Claude Code
card(440, 696, 660, 748, GREY_E, DARK, "Agent Harness", "", glyph=">_", face="#f4f6fa")

LC, RC = 300, 800  # left / right plane centre x
arrow([(550, 696), (550, 668), (LC, 668), (LC, 637)], GREY_E, lw=2.4, scale=18)
arrow([(550, 668), (RC, 668), (RC, 637)], GREY_E, lw=2.4, scale=18)

# ---------------------------------------------------------------- planes
PTOP, PBOT = 634, 250
rbox(70, PBOT, 530, PTOP, BLUE_E, BLUE_F, lw=2.2, rnd=14, z=1)
rbox(570, PBOT, 1030, PTOP, GREEN_E, GREEN_F, lw=2.2, rnd=14, z=1)

ax.text(LC, PTOP - 16, "inference plane", ha="center", va="top", fontsize=15, fontweight="bold", color=BLUE_T)
ax.text(LC, PTOP - 39, "LLM_URL -> proxy", ha="center", va="top", fontsize=9, color=BLUE_T, family="monospace")

ax.text(RC, PTOP - 16, "tool / audit plane", ha="center", va="top", fontsize=15, fontweight="bold", color=GREEN_T)
ax.text(
    RC, PTOP - 39, ".mcp.json: mcp__axis__run", ha="center", va="top", fontsize=9, color=GREEN_T, family="monospace"
)

# ---- inference plane cards
card(
    100,
    478,
    500,
    578,
    BLUE_E,
    BLUE_T,
    "lemonade_proxy (Node)",
    "transparent telemetry proxy\n" "identity + metadata\n" "semantic router (consult)",
    glyph="oo",
)

arrow([(LC, 478), (LC, 464), (185, 464), (185, 434)], BLUE_E, lw=2.0, scale=14)
arrow([(LC, 464), (415, 464), (415, 434)], BLUE_E, lw=2.0, scale=14)
ax.text(120, 460, "local", ha="center", va="top", fontsize=8, color=BLUE_T, family="monospace", linespacing=1.3)
ax.text(460, 456, "frontier tier", ha="center", va="top", fontsize=8.5, color=BLUE_T)

card(90, 340, 290, 432, BLUE_E, BLUE_T, "Lemonade", "LLM (CPU)\nfree", glyph="L")
card(310, 340, 510, 432, BLUE_E, BLUE_T, "Frontier LLM API", "paid API", glyph="A")

# ---- tool / audit plane cards
card(
    600,
    478,
    1000,
    578,
    GREEN_E,
    GREEN_T,
    "axis MCP connector (Node)",
    "identity + redacted argv\n" "AXIS -> SQLite audit event",
    glyph="<>",
)

arrow([(RC, 478), (RC, 364)], GREEN_E, lw=2.0, scale=14)

card(
    695,
    274,
    905,
    362,
    PURPLE_E,
    PURPLE_E,
    "AXIS sandbox",
    "seccomp + landlock + netns\n(sole enforcement layer)",
    glyph="#",
    face=PURPLE_F,
)

# ------------------------------------------------- SQLite audit DB (OUTSIDE both planes)
SX0, SY0, SX1, SY1 = 410, 158, 690, 232
SYM = (SY0 + SY1) / 2
card(SX0, SY0, SX1, SY1, AUDIT, AUDIT, "SQLite audit DB", "audit.db (local)", glyph=">", face="#f3f8ee")
ax.text(
    (SX0 + SX1) / 2,
    SY0 - 11,
    "shared telemetry  -  outside both planes",
    ha="center",
    va="center",
    fontsize=8.5,
    style="italic",
    color=AUDIT,
)

# reporting arrows: proxy -> audit DB (left) and connector -> audit DB (right)
arrow([(100, 528), (40, 528), (40, SYM), (SX0, SYM)], AUDIT, lw=2.4, scale=18)
arrow([(1000, 528), (1060, 528), (1060, SYM), (SX1, SYM)], AUDIT, lw=2.4, scale=18)
ax.text(
    230, SYM + 8, "reports: llm.request event", ha="center", va="bottom", fontsize=9, color=AUDIT, family="monospace"
)
ax.text(
    870, SYM + 8, "reports: axis.toolcall event", ha="center", va="bottom", fontsize=9, color=AUDIT, family="monospace"
)

# ---------------------------------------------------------------- banner
rbox(70, 48, 1030, 108, BANNER_E, BANNER_F, lw=2.0, rnd=12, z=1)
icon(104, 78, ORANGE_E, "!")
ax.text(
    128,
    78,
    "tool plane -> AXIS sandbox;  both planes -> SQLite audit DB",
    ha="left",
    va="center",
    fontsize=12,
    color="#5b4636",
)

# ---------------------------------------------------------------- save
out = os.path.join(os.path.dirname(__file__), "architecture.png")
fig.savefig(out, dpi=100, facecolor="white")
print("wrote", out)
