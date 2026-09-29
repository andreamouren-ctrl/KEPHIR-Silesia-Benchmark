#!/usr/bin/env python3
"""
EXP-115 — Native Context Uncertainty Resolver

Qualification of a denser bounded spatial sampler:
- 4 quarters
- 64 windows per quarter
- 1 KiB per window
- maximum 256 KiB sampled per logical stream

The context policy thresholds remain unchanged from EXP-112.
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

    data = json.loads(Path("exp113_results.json").read_text())
    data["experiment"] = "EXP-115"
    data["purpose"] = "native-context-dense-spatial-sampling"
    data["sample_budget_max_bytes_per_stream"] = 256 * 1024
    data["sampling_geometry"] = {
        "quarters": 4,
        "windows_per_quarter": 64,
        "window_bytes": 1024,
        "total_reads_max": 256,
    }

    Path("exp115_results.json").write_text(
        json.dumps(data, indent=2, sort_keys=True)
    )

    s, h = data["datasets"]
    print(
        "EXP115_COMPLETE",
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
