#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Select 50 tau-bench tasks (25 retail + 25 airline) with a fixed seed.
Writes data/tasks_retail.json and data/tasks_airline.json with task indices,
and data/tasks_summary.txt for audit.

Usage: select_tasks.py [seed]
"""
import json
import random
import sys
import warnings

warnings.filterwarnings("ignore")

from tau_bench.envs.airline.tasks_test import TASKS as airline_tasks  # noqa: E402
from tau_bench.envs.retail.tasks_test import TASKS_TEST as retail_tasks  # noqa: E402

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 42
N_RETAIL = 25
N_AIRLINE = 25

rng = random.Random(SEED)

retail_idx = sorted(rng.sample(range(len(retail_tasks)), N_RETAIL))
airline_idx = sorted(rng.sample(range(len(airline_tasks)), N_AIRLINE))

with open("data/tasks_retail.json", "w") as f:
    json.dump({"indices": retail_idx, "seed": SEED, "env": "retail"}, f, indent=2)
with open("data/tasks_airline.json", "w") as f:
    json.dump({"indices": airline_idx, "seed": SEED, "env": "airline"}, f, indent=2)

with open("data/tasks_summary.txt", "w") as f:
    f.write(f"seed={SEED}  retail={N_RETAIL}  airline={N_AIRLINE}  total={N_RETAIL+N_AIRLINE}\n")
    f.write(f"retail indices: {retail_idx}\n")
    f.write(f"airline indices: {airline_idx}\n")
    f.write("\n--- retail samples ---\n")
    for i in retail_idx[:3]:
        f.write(f"  [{i}] {retail_tasks[i].instruction[:100]}\n")
    f.write("\n--- airline samples ---\n")
    for i in airline_idx[:3]:
        f.write(f"  [{i}] {airline_tasks[i].instruction[:100]}\n")

print(f"Selected {N_RETAIL} retail + {N_AIRLINE} airline tasks (seed={SEED})")
print(f"Retail indices: {retail_idx}")
print(f"Airline indices: {airline_idx}")
