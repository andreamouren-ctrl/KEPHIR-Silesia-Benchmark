#!/usr/bin/env python3
"""
EXP-114 — Native Context Sampling Refinement

Reuses the EXP-113 qualification matrix after changing only the spatial
distribution of the bounded context sample:

EXP-113:
  4 windows/quarter x 16 KiB = 256 KiB total

EXP-114:
  16 windows/quarter x 4 KiB = 256 KiB total

The byte budget is unchanged. Only sample coverage is made more spatially
representative.

No production default is changed.
"""

from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exp113_native_context_router as E113


def main():
    E113.main()

    src = Path("exp113_results.json")
    data = json.loads(src.read_text())
    data["experiment"] = "EXP-114"
    data["purpose"] = "native-context-spatial-sampling-refinement"
    data["sample_budget_max_bytes_per_stream"] = 256 * 1024
    data["sampling_geometry"] = {
        "quarters": 4,
        "windows_per_quarter": 16,
        "window_bytes": 4 * 1024,
        "total_reads_max": 64,
    }

    Path("exp114_results.json").write_text(
        json.dumps(data, indent=2, sort_keys=True)
    )

    s, h = data["datasets"]
    print(
        "EXP114_COMPLETE",
        "SILESIA_GAIN", s["gain_vs_baseline"],
        "SILESIA_REGRET", s["regret_vs_oracle"],
        "SILESIA_MATCH", f'{s["policy_match_count"]}/{s["file_count"]}',
        "SILESIA_HARM", len(s["harmful_selections"]),
        "HOLDOUT_GAIN", h["gain_vs_baseline"],
        "HOLDOUT_REGRET", h["regret_vs_oracle"],
        "HOLDOUT_MATCH", f'{h["policy_match_count"]}/{h["file_count"]}',
        "HOLDOUT_HARM", len(h["harmful_selections"]),
        flush=True,
    )


if __name__ == "__main__":
    main()
