#!/usr/bin/env python3
"""
EXP-117B — Public C API profile qualification.

Black-box qualification through kephir2_c_api_cli only. FAST must retain the
qualified 512 KiB baseline. AUTO must reproduce the EXP-116 adaptive-context
candidate. Every produced archive is explicitly decoded with the opposite
public profile and SHA-256 verified.
"""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path.cwd()

SILESIA_FILES = [
    "dickens", "mozilla", "mr", "nci", "ooffice", "osdb",
    "reymont", "samba", "sao", "webster", "x-ray", "xml",
]

EXTERNAL = {
    "canterbury": [
        "alice29.txt", "asyoulik.txt", "cp.html", "fields.c",
        "grammar.lsp", "kennedy.xls", "lcet10.txt", "plrabn12.txt",
        "ptt5", "sum", "xargs.1",
    ],
    "calgary": [
        "bib", "book1", "book2", "geo", "news", "obj1", "obj2",
        "paper1", "paper2", "paper3", "paper4", "paper5", "paper6",
        "pic", "progc", "progl", "progp", "trans",
    ],
    "large": ["E.coli", "bible.txt", "world192.txt"],
}

EXPECTED = {
    "silesia": {
        "raw_bytes": 211_938_580,
        "fast_bytes": 62_925_489,
        "auto_bytes": 61_677_233,
    },
    "external": {
        "raw_bytes": 17_221_759,
        "fast_bytes": 4_915_548,
        "auto_bytes": 4_855_203,
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_cli(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def run(cli: Path, *args: str) -> dict[str, str]:
    cp = subprocess.run(
        [str(cli), *map(str, args)],
        check=True,
        text=True,
        capture_output=True,
    )
    values = parse_cli(cp.stdout)
    if values.get("STATUS") != "OK":
        raise RuntimeError(f"public API call failed: {cp.stdout}\n{cp.stderr}")
    return values


def qualify_file(cli: Path, dataset: str, src: Path, work: Path) -> dict:
    tag = f"{dataset}_{src.name}".replace("/", "_")
    source_sha = sha256(src)
    measured = {}

    for profile in ("fast", "auto"):
        arc = work / f"{tag}_{profile}.kpf"
        comp = run(cli, "c", profile, src, arc, "4", "1")
        archive_bytes = arc.stat().st_size

        if int(comp["INPUT_BYTES"]) != src.stat().st_size:
            raise RuntimeError(f"input byte accounting mismatch: {src}")
        if int(comp["OUTPUT_BYTES"]) != archive_bytes:
            raise RuntimeError(f"output byte accounting mismatch: {src}")

        # Cross-profile decode proves that decode is format-driven rather than
        # dependent on the profile used during encoding.
        decode_profile = "auto" if profile == "fast" else "fast"
        out = work / f"out_{tag}_{profile}"
        if out.exists():
            shutil.rmtree(out)
        run(cli, "d", decode_profile, arc, out, "4", "1")

        restored = out / src.name
        if not restored.is_file() or sha256(restored) != source_sha:
            raise RuntimeError(f"SHA mismatch: {dataset}/{src.name}/{profile}")

        measured[profile] = {
            "archive_bytes": archive_bytes,
            "archive_sha256": sha256(arc),
            "comp_seconds_with_verify": float(comp["SECONDS"]),
            "sha_pass": True,
        }

        shutil.rmtree(out)
        arc.unlink()

    delta = measured["auto"]["archive_bytes"] - measured["fast"]["archive_bytes"]
    print(
        "EXP117B_FILE", dataset, src.name,
        "RAW", src.stat().st_size,
        "FAST", measured["fast"]["archive_bytes"],
        "AUTO", measured["auto"]["archive_bytes"],
        "DELTA", delta,
        "SHA", 1,
        flush=True,
    )

    return {
        "file": src.name,
        "raw_bytes": src.stat().st_size,
        "delta_auto_vs_fast": delta,
        "measured": measured,
    }


def qualify_dataset(cli: Path, name: str, files: list[Path], work: Path) -> dict:
    rows = [qualify_file(cli, name, src, work) for src in files]
    raw = sum(r["raw_bytes"] for r in rows)
    fast = sum(r["measured"]["fast"]["archive_bytes"] for r in rows)
    auto = sum(r["measured"]["auto"]["archive_bytes"] for r in rows)
    harmful = [
        {"file": r["file"], "delta": r["delta_auto_vs_fast"]}
        for r in rows if r["delta_auto_vs_fast"] > 0
    ]
    result = {
        "dataset": name,
        "file_count": len(rows),
        "raw_bytes": raw,
        "fast_bytes": fast,
        "auto_bytes": auto,
        "auto_ratio": auto / raw,
        "gain_vs_fast": fast - auto,
        "harmful": harmful,
        "files": rows,
    }
    print(
        "EXP117B_DATASET", name,
        "RAW", raw,
        "FAST", fast,
        "AUTO", auto,
        "RATIO", result["auto_ratio"],
        "GAIN", result["gain_vs_fast"],
        "HARM", len(harmful),
        flush=True,
    )
    return result


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: exp117b_public_api_profiles.py C_API_CLI")

    cli = Path(sys.argv[1]).resolve()
    work = ROOT / "exp117b_public_api"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()

    silesia_files = [ROOT / "corpora" / "silesia" / n for n in SILESIA_FILES]
    external_files = [
        ROOT / "corpora" / dataset / name
        for dataset, names in EXTERNAL.items()
        for name in names
    ]

    datasets = [
        qualify_dataset(cli, "silesia", silesia_files, work),
        qualify_dataset(cli, "external", external_files, work),
    ]

    for ds in datasets:
        expected = EXPECTED[ds["dataset"]]
        assert ds["raw_bytes"] == expected["raw_bytes"]
        assert ds["fast_bytes"] == expected["fast_bytes"]
        assert ds["auto_bytes"] == expected["auto_bytes"]
        assert not ds["harmful"]
        assert all(
            mode["sha_pass"]
            for row in ds["files"]
            for mode in row["measured"].values()
        )

    result = {
        "experiment": "EXP-117B",
        "surface": "public-c-api-v1",
        "profiles": {"fast": "qualified-baseline", "auto": "adaptive-context"},
        "datasets": datasets,
    }
    Path("exp117b_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)
    )

    print(
        "EXP117B_COMPLETE",
        "SILESIA_AUTO", datasets[0]["auto_bytes"],
        "SILESIA_GAIN", datasets[0]["gain_vs_fast"],
        "EXTERNAL_AUTO", datasets[1]["auto_bytes"],
        "EXTERNAL_GAIN", datasets[1]["gain_vs_fast"],
        flush=True,
    )


if __name__ == "__main__":
    main()
