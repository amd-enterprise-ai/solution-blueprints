# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

from typing import List, Optional

from docarray import BaseDoc


class TopologyConfig:
    """Node forwarding configuration."""

    downstream_exclusions: Optional[List[str]] = None


class TextDoc(BaseDoc, TopologyConfig):
    """Document model with topology metadata."""
