#!/usr/bin/env python3
"""Guard the channel-name tables.

These tables are reference data for PC-Tool's channel-name ids; they cannot be
re-derived from a tune file, since any one tune uses only a handful of them.
What is worth pinning is that they stay *complete and self-consistent* - every
id PC-Tool defines, contiguous, with the known landmarks in the right slots. A
silent edit that drops or renumbers an entry is exactly the failure that
mislabels a channel, and it is invisible in a tune that happens not to use that
id.

Run: python3 tests/test_channel_types.py
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pct6_extract import INPUT_CHANNEL_NAMES, OUTPUT_CHANNEL_NAMES  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EXTRACT = os.path.join(HERE, "..", "pct6_extract.py")
FIXTURE = os.path.join(HERE, "fixtures", "sample-tune.pct6")

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


# --- completeness ---------------------------------------------------------
# 57 output ids 0-56, no gaps; 77 input ids 0-77 with 9 unused (PC-Tool skips
# it - the input list jumps Front R Low to Front Center Full).
check(len(OUTPUT_CHANNEL_NAMES) == 57, f"output table has {len(OUTPUT_CHANNEL_NAMES)} entries, expected 57")
check(sorted(OUTPUT_CHANNEL_NAMES) == list(range(57)), "output ids are not contiguous 0-56")

check(len(INPUT_CHANNEL_NAMES) == 77, f"input table has {len(INPUT_CHANNEL_NAMES)} entries, expected 77")
check(sorted(INPUT_CHANNEL_NAMES) == [i for i in range(78) if i != 9],
      "input ids are not 0-77 with exactly 9 missing")

# --- landmarks ------------------------------------------------------------
# Spot-check the ids where the stored id diverges from the order PC-Tool
# displays these in, since transcribing the displayed order is the easy mistake.
for cid, name in {
    0: "Not assigned", 3: "Front L High", 8: "Front R Low",
    25: "Subwoofer 1", 29: "Line Out 1", 37: "Subwoofer L",
    39: "Pass Through 1", 44: "Pass Through 6", 45: "Bridge Mode",
    48: "Front Subwoofer L", 50: "Pass Through 7", 55: "Pass Through 12",
    56: "User defined Name",
}.items():
    check(OUTPUT_CHANNEL_NAMES.get(cid) == name,
          f"output id {cid} is {OUTPUT_CHANNEL_NAMES.get(cid)!r}, expected {name!r}")

for cid, name in {
    0: "Not assigned", 10: "Front Center Full", 14: "Rear L Full",
    26: "Subwoofer 1", 38: "Digital In L", 54: "AUX L", 77: "USB R",
}.items():
    check(INPUT_CHANNEL_NAMES.get(cid) == name,
          f"input id {cid} is {INPUT_CHANNEL_NAMES.get(cid)!r}, expected {name!r}")

# The two directions are genuinely different id spaces; if someone collapses
# them back into one table this catches it.
check(OUTPUT_CHANNEL_NAMES[38] == "Subwoofer R" and INPUT_CHANNEL_NAMES[38] == "Digital In L",
      "id 38 should differ between output and input tables")

# --- no duplicate names within a direction --------------------------------
for label, table in (("output", OUTPUT_CHANNEL_NAMES), ("input", INPUT_CHANNEL_NAMES)):
    dupes = {n for n in table.values() if list(table.values()).count(n) > 1}
    check(not dupes, f"{label} table has duplicate names: {sorted(dupes)}")

# --- the fixture still resolves as expected -------------------------------
if os.path.exists(FIXTURE):
    import json

    data = json.loads(subprocess.check_output([sys.executable, EXTRACT, "--json", FIXTURE]))
    got = {o["index"]: o["channel_name"] for o in data["outputs"]}
    for idx, name in {
        6: "Pass Through 1", 9: "Pass Through 4", 12: "Not assigned",
        17: "Front L High", 22: "Front R Low", 24: "Subwoofer 1",
    }.items():
        check(got.get(idx) == name, f"fixture output {idx} is {got.get(idx)!r}, expected {name!r}")

    ins = {i["index"]: i["channel_name"] for i in data["inputs"]}
    for idx, name in {0: "Front L Full", 8: "Digital In L", 10: "AUX L"}.items():
        check(ins.get(idx) == name, f"fixture input {idx} is {ins.get(idx)!r}, expected {name!r}")
else:
    print("note: fixture missing, skipped decode checks")

if failures:
    print(f"FAIL ({len(failures)})")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"ok - {len(OUTPUT_CHANNEL_NAMES)} output and {len(INPUT_CHANNEL_NAMES)} input channel types")
