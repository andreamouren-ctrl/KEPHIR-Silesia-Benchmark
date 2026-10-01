#!/usr/bin/env python3
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

MiB = 1024 * 1024

FULL_CANDIDATES = {
    "adaptive": ["adaptive"],
    "grain4": ["4096", "4096", "1"],
    "grain8": ["8192", "8192", "1"],
}
BUDGETS = [1 * MiB, 2 * MiB, 4 * MiB]
SAMPLERS = ["center", "stratified"]
MARGINS = [0, 64, 256, 1024]


def run(cmd):
    p = subprocess.run(cmd, check=True, text=True, capture_output=True)
    out = {}
    for line in p.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dataset_files():
    silesia = sorted(p for p in Path("corpora/silesia").rglob("*") if p.is_file())
    external = []
    for root_name in ("canterbury", "calgary", "large"):
        root = Path("corpora") / root_name
        external.extend(sorted(p for p in root.rglob("*") if p.is_file()))
    return {"silesia": silesia, "external": external}


def file_id(dataset, path):
    if dataset == "silesia":
        return path.name
    return str(path.relative_to("corpora"))


def sample_bytes(data, budget, sampler):
    if len(data) <= budget:
        return data
    if sampler == "center":
        start = (len(data) - budget) // 2
        return data[start:start + budget]
    if sampler == "stratified":
        parts = 4
        chunk = max(1, budget // parts)
        maxoff = len(data) - chunk
        offsets = [(maxoff * i) // (parts - 1) for i in range(parts)]
        out = bytearray()
        for off in offsets:
            remain = budget - len(out)
            if remain <= 0:
                break
            out.extend(data[off:off + min(chunk, remain)])
        return bytes(out[:budget])
    raise ValueError(sampler)


def compress(cli, src, archive, extra):
    result = run([str(cli), "c", str(src), str(archive), "4", *extra])
    return {
        "bytes": int(result["OUTPUT_BYTES"]),
        "seconds": float(result["SECONDS"]),
    }


def measure_full(cli, dataset, path, work, index):
    source_sha = sha256(path)
    rows = {}
    for name, extra in FULL_CANDIDATES.items():
        archive = work / f"full_{index:03d}_{name}.kpf"
        outdir = work / f"full_{index:03d}_{name}_out"
        shutil.rmtree(outdir, ignore_errors=True)
        enc = compress(cli, path, archive, extra)
        dec = run([str(cli), "d", str(archive), str(outdir), "4"])
        restored = outdir / path.name
        ok = restored.is_file() and sha256(restored) == source_sha
        if not ok:
            raise RuntimeError(f"full roundtrip failed: {dataset}/{file_id(dataset, path)} {name}")
        rows[name] = {
            **enc,
            "decompress_seconds": float(dec["SECONDS"]),
            "sha_ok": True,
        }
        archive.unlink(missing_ok=True)
        shutil.rmtree(outdir, ignore_errors=True)

    oracle = min(FULL_CANDIDATES, key=lambda k: (rows[k]["bytes"], list(FULL_CANDIDATES).index(k)))
    return rows, oracle


def measure_probes(cli, path, work, index):
    data = path.read_bytes()
    probes = {}
    for budget in BUDGETS:
        for sampler in SAMPLERS:
            key = f"{budget // MiB}m_{sampler}"
            sample = work / f"sample_{index:03d}_{key}.bin"
            sample.write_bytes(sample_bytes(data, budget, sampler))
            candidate_rows = {}
            for name, extra in FULL_CANDIDATES.items():
                archive = work / f"probe_{index:03d}_{key}_{name}.kpf"
                candidate_rows[name] = compress(cli, sample, archive, extra)
                archive.unlink(missing_ok=True)
            sample.unlink(missing_ok=True)
            probes[key] = candidate_rows
    return probes


def choose_from_probe(probe, margin):
    adaptive = probe["adaptive"]["bytes"]
    grain = min(("grain4", "grain8"), key=lambda k: (probe[k]["bytes"], 0 if k == "grain4" else 1))
    if probe[grain]["bytes"] + margin < adaptive:
        return grain
    return "adaptive"


def summarize_policy(rows, probe_key, margin, dataset=None):
    selected_rows = [r for r in rows if dataset is None or r["dataset"] == dataset]
    raw = sum(r["raw_bytes"] for r in selected_rows)
    adaptive_bytes = sum(r["full"]["adaptive"]["bytes"] for r in selected_rows)
    oracle_bytes = sum(r["full"][r["oracle"]]["bytes"] for r in selected_rows)
    selected_bytes = 0
    harmful = []
    choices = {"adaptive": 0, "grain4": 0, "grain8": 0}
    regret = 0
    for r in selected_rows:
        choice = choose_from_probe(r["probes"][probe_key], margin)
        choices[choice] += 1
        b = r["full"][choice]["bytes"]
        selected_bytes += b
        regret += b - r["full"][r["oracle"]]["bytes"]
        if b > r["full"]["adaptive"]["bytes"]:
            harmful.append({
                "file": r["file"],
                "delta": b - r["full"]["adaptive"]["bytes"],
                "choice": choice,
            })
    available_gain = adaptive_bytes - oracle_bytes
    captured = adaptive_bytes - selected_bytes
    return {
        "dataset": dataset or "combined",
        "probe": probe_key,
        "margin": margin,
        "raw_bytes": raw,
        "adaptive_bytes": adaptive_bytes,
        "oracle_bytes": oracle_bytes,
        "selected_bytes": selected_bytes,
        "selected_ratio": selected_bytes / raw,
        "gain_vs_adaptive": captured,
        "oracle_available_gain": available_gain,
        "oracle_capture": (captured / available_gain) if available_gain else 1.0,
        "regret_bytes": regret,
        "harmful_count": len(harmful),
        "harmful": harmful,
        "choices": choices,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: exp118b_grain_probe_router.py <kephir2_native_k75_cli>")
    cli = Path(sys.argv[1]).resolve()
    if not cli.is_file():
        raise SystemExit(f"CLI not found: {cli}")

    work = Path("exp118b_work")
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    rows = []
    index = 0
    for dataset, files in dataset_files().items():
        for path in files:
            full, oracle = measure_full(cli, dataset, path, work, index)
            probes = measure_probes(cli, path, work, index)
            row = {
                "dataset": dataset,
                "file": file_id(dataset, path),
                "raw_bytes": path.stat().st_size,
                "full": full,
                "oracle": oracle,
                "probes": probes,
            }
            rows.append(row)
            print(
                "EXP118B_FILE", dataset, row["file"],
                "RAW", row["raw_bytes"],
                "ADAPT", full["adaptive"]["bytes"],
                "G4", full["grain4"]["bytes"],
                "G8", full["grain8"]["bytes"],
                "ORACLE", oracle, full[oracle]["bytes"],
                flush=True,
            )
            index += 1

    policies = []
    for budget in BUDGETS:
        for sampler in SAMPLERS:
            key = f"{budget // MiB}m_{sampler}"
            for margin in MARGINS:
                combined = summarize_policy(rows, key, margin)
                combined["silesia"] = summarize_policy(rows, key, margin, "silesia")
                combined["external"] = summarize_policy(rows, key, margin, "external")
                policies.append(combined)
                print(
                    "EXP118B_POLICY", key, "MARGIN", margin,
                    "GAIN", combined["gain_vs_adaptive"],
                    "REGRET", combined["regret_bytes"],
                    "HARM", combined["harmful_count"],
                    "CAPTURE", combined["oracle_capture"],
                    "SILESIA", combined["silesia"]["selected_bytes"],
                    "EXTERNAL", combined["external"]["selected_bytes"],
                    flush=True,
                )

    zero_harm = [p for p in policies if p["harmful_count"] == 0]
    zero_harm.sort(key=lambda p: (-p["gain_vs_adaptive"], p["regret_bytes"], p["probe"], p["margin"]))
    best = zero_harm[0] if zero_harm else None

    result = {
        "experiment": "EXP-118B",
        "purpose": "evaluate bounded sample-compression probes for grain routing",
        "candidates": list(FULL_CANDIDATES),
        "budgets_bytes": BUDGETS,
        "samplers": SAMPLERS,
        "margins_bytes": MARGINS,
        "files": rows,
        "policies": policies,
        "best_zero_harm_on_measured_set": best,
    }
    Path("exp118b_results.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    shutil.rmtree(work, ignore_errors=True)

    if best:
        print(
            "EXP118B_BEST_ZERO_HARM",
            best["probe"], "MARGIN", best["margin"],
            "GAIN", best["gain_vs_adaptive"],
            "REGRET", best["regret_bytes"],
            "CAPTURE", best["oracle_capture"],
            "SILESIA", best["silesia"]["selected_bytes"],
            "EXTERNAL", best["external"]["selected_bytes"],
            flush=True,
        )
    print("EXP118B_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
