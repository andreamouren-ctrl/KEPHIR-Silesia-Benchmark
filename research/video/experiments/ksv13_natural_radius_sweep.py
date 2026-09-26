#!/usr/bin/env python3
"""
KSV-13 Natural Motion Radius Sweep.

Research goal:
measure how much of AURORA Media's natural-video compression gap is caused by
the current MC8R4 search radius.

For every routing window, KSV-13 builds:
- TEMP
- MC MOD8 radius 4
- MC ZZ_INTER radius 4
- MC MOD8 radius 6
- MC ZZ_INTER radius 6

Three fully decodable bit-exact streams are emitted:
- R4 policy: best of TEMP / R4 MOD8 / R4 ZZ
- R6 policy: best of TEMP / R6 MOD8 / R6 ZZ
- ORACLE policy: best of all five candidates

The oracle is research-only and intentionally expensive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from collections import Counter
from pathlib import Path

from kstream_video_baseline import (
    encode_file as temp_encode,
    decode_file as temp_decode,
)
from kstream_video_motion_control import (
    spatial_frame,
    motion_residual,
    frame_sizes,
    decode_file as mc_decode,
    MAGIC as MC_MAGIC,
    VERSION as MC_VERSION,
    FMT_YUV420P8 as MC_FMT,
    HDR as MC_HDR,
    CHUNK as MC_CHUNK,
)
from kstream_video_residual_symbols_v7 import (
    map_residual,
    decode_file as zz_decode,
    ZZ_INTER,
    MAGIC as ZZ_MAGIC,
    VERSION as ZZ_VERSION,
    FMT_YUV420P8 as ZZ_FMT,
    HDR as ZZ_HDR,
    CHUNK as ZZ_CHUNK,
)

OUT = Path("results/video/ksv13_radius_sweep")

MAGIC = b"K13R"
VERSION = 1
HDR = struct.Struct("<4sBHHIIII")
ENT = struct.Struct("<BBII")

MODE_TEMP = 0
MODE_MC_MOD8 = 1
MODE_MC_ZZ = 2

BLOCK = 8
R4 = 4
R6 = 6


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame_size(w: int, h: int) -> int:
    y, c, _, _ = frame_sizes(w, h)
    return y + 2 * c


def run(cmd):
    t0 = time.perf_counter()
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return time.perf_counter() - t0


def kcp(exe: Path, src: Path, arc: Path):
    return run([
        str(exe.resolve()), "cp", str(src), str(arc),
        "6", "6.55", "9.42", "1.20",
    ])


def kdp(exe: Path, arc: Path, outdir: Path):
    if outdir.exists():
        shutil.rmtree(outdir)
    return run([str(exe.resolve()), "dp", str(arc), str(outdir), "6"])


def build_motion_records(raw_chunk: bytes, w: int, h: int, gop: int, radius: int):
    ys, cs, _, _ = frame_sizes(w, h)
    fs = ys + 2 * cs
    total = len(raw_chunk) // fs

    chunks = []
    mag_sum = 0
    mag_count = 0
    t0 = time.perf_counter()

    off = 0
    while off < total:
        n = min(gop, total - off)
        records = []
        prev = None
        for j in range(n):
            frame = raw_chunk[(off + j) * fs:(off + j + 1) * fs]
            if prev is None:
                records.append(("I", spatial_frame(frame, w, h)))
            else:
                mv, residual = motion_residual(
                    frame, prev, w, h, BLOCK, radius
                )
                mag_sum += sum((b if b < 128 else 256 - b) for b in residual)
                mag_count += len(residual)
                records.append(("P", mv, residual))
            prev = frame
        chunks.append((n, records))
        off += n

    seconds = time.perf_counter() - t0
    mean_mag = mag_sum / mag_count if mag_count else 0.0
    return chunks, mean_mag, seconds


def serialize_mod8(chunks, w, h, fpsn, fpsd, gop, radius):
    out = bytearray()
    out.extend(
        MC_HDR.pack(
            MC_MAGIC, MC_VERSION, MC_FMT,
            gop, BLOCK, radius, w, h, fpsn, fpsd
        )
    )
    for n, records in chunks:
        payload = bytearray()
        for rec in records:
            if rec[0] == "I":
                payload.extend(rec[1])
            else:
                payload.extend(rec[1])
                payload.extend(rec[2])
        p = bytes(payload)
        out.extend(MC_CHUNK.pack(n, len(p), zlib.crc32(p) & 0xFFFFFFFF))
        out.extend(p)
    return bytes(out)


def serialize_zz(chunks, w, h, fpsn, fpsd, gop):
    out = bytearray()
    out.extend(
        ZZ_HDR.pack(
            ZZ_MAGIC, ZZ_VERSION, ZZ_FMT,
            gop, BLOCK, ZZ_INTER, w, h, fpsn, fpsd
        )
    )
    for n, records in chunks:
        payload = bytearray()
        for rec in records:
            if rec[0] == "I":
                payload.extend(rec[1])
            else:
                payload.extend(rec[1])
                payload.extend(map_residual(rec[2], ZZ_INTER))
        p = bytes(payload)
        out.extend(ZZ_CHUNK.pack(n, len(p), zlib.crc32(p) & 0xFFFFFFFF))
        out.extend(p)
    return bytes(out)


def compress_bytes(front: bytes, exe: Path, tmp: Path, tag: str):
    src = tmp / f"{tag}.front"
    arc = tmp / f"{tag}.aur"
    src.write_bytes(front)
    seconds = kcp(exe, src, arc)
    return arc.read_bytes(), seconds


def temp_candidate(
    raw_chunk: bytes, exe: Path, tmp: Path,
    w: int, h: int, fpsn: int, fpsd: int, gop: int, tag: str
):
    raw = tmp / f"{tag}.yuv"
    front = tmp / f"{tag}.temp.front"
    arc = tmp / f"{tag}.temp.aur"
    raw.write_bytes(raw_chunk)

    t0 = time.perf_counter()
    temp_encode(raw, front, w, h, fpsn, fpsd, gop, 3)
    frontend_s = time.perf_counter() - t0
    backend_s = kcp(exe, front, arc)
    return {
        "mode": MODE_TEMP,
        "radius": 0,
        "label": "TEMP",
        "payload": arc.read_bytes(),
        "frontend_seconds": frontend_s,
        "backend_seconds": backend_s,
    }


def radius_candidates(
    raw_chunk: bytes, exe: Path, tmp: Path,
    w: int, h: int, fpsn: int, fpsd: int, gop: int,
    radius: int, tag: str
):
    records, mean_mag, search_s = build_motion_records(
        raw_chunk, w, h, gop, radius
    )

    t0 = time.perf_counter()
    mod_front = serialize_mod8(records, w, h, fpsn, fpsd, gop, radius)
    mod_serialize_s = time.perf_counter() - t0
    mod_payload, mod_backend_s = compress_bytes(
        mod_front, exe, tmp, f"{tag}.r{radius}.mod8"
    )

    t0 = time.perf_counter()
    zz_front = serialize_zz(records, w, h, fpsn, fpsd, gop)
    zz_serialize_s = time.perf_counter() - t0
    zz_payload, zz_backend_s = compress_bytes(
        zz_front, exe, tmp, f"{tag}.r{radius}.zz"
    )

    shared_search = search_s
    return [
        {
            "mode": MODE_MC_MOD8,
            "radius": radius,
            "label": f"MC_R{radius}_MOD8",
            "payload": mod_payload,
            "frontend_seconds": shared_search + mod_serialize_s,
            "backend_seconds": mod_backend_s,
            "mean_mag": mean_mag,
        },
        {
            "mode": MODE_MC_ZZ,
            "radius": radius,
            "label": f"MC_R{radius}_ZZ",
            "payload": zz_payload,
            "frontend_seconds": shared_search + zz_serialize_s,
            "backend_seconds": zz_backend_s,
            "mean_mag": mean_mag,
        },
    ], search_s


def choose(candidates):
    return min(
        candidates,
        key=lambda x: (len(x["payload"]), x["mode"], x["radius"])
    )


def write_stream(
    dst: Path,
    w: int, h: int, fpsn: int, fpsd: int, gop: int, route_span: int,
    entries,
):
    with dst.open("wb") as f:
        f.write(HDR.pack(
            MAGIC, VERSION, w, h, fpsn, fpsd, gop, route_span
        ))
        for entry in entries:
            payload = entry["payload"]
            f.write(ENT.pack(
                entry["mode"], entry["radius"],
                entry["frames"], len(payload)
            ))
            f.write(payload)


def decode_stream(src: Path, dst: Path, exe: Path):
    data = src.read_bytes()
    if len(data) < HDR.size:
        raise RuntimeError("truncated KSV-13 header")

    pos = 0
    magic, ver, w, h, fpsn, fpsd, gop, route_span = HDR.unpack_from(data, pos)
    pos += HDR.size
    if magic != MAGIC or ver != VERSION:
        raise RuntimeError("bad KSV-13 stream")

    out = bytearray()
    with tempfile.TemporaryDirectory(prefix="ksv13_dec_") as td:
        tmp = Path(td)
        idx = 0
        while pos < len(data):
            if pos + ENT.size > len(data):
                raise RuntimeError("truncated KSV-13 entry")
            mode, radius, frames, payload_size = ENT.unpack_from(data, pos)
            pos += ENT.size
            if pos + payload_size > len(data):
                raise RuntimeError("truncated KSV-13 payload")

            payload = data[pos:pos + payload_size]
            pos += payload_size

            arc = tmp / f"{idx}.aur"
            outdir = tmp / f"{idx}.out"
            front = tmp / f"{idx}.front"
            raw = tmp / f"{idx}.yuv"
            arc.write_bytes(payload)
            kdp(exe, arc, outdir)

            files = [p for p in outdir.rglob("*") if p.is_file()]
            if len(files) != 1:
                raise RuntimeError("unexpected KHEPRI decode output")
            shutil.copyfile(files[0], front)

            if mode == MODE_TEMP:
                if radius != 0:
                    raise RuntimeError("TEMP entry with radius")
                temp_decode(front, raw)
            elif mode == MODE_MC_MOD8:
                mc_decode(front, raw)
            elif mode == MODE_MC_ZZ:
                if radius not in (R4, R6):
                    raise RuntimeError("bad ZZ radius")
                zz_decode(front, raw, radius)
            else:
                raise RuntimeError("bad KSV-13 mode")

            chunk = raw.read_bytes()
            if len(chunk) != frames * frame_size(w, h):
                raise RuntimeError("KSV-13 decoded frame count mismatch")
            out.extend(chunk)
            idx += 1

    dst.write_bytes(out)


def policy_stats(entries):
    counts = Counter(e["label"] for e in entries)
    return dict(sorted(counts.items()))


def encode_source(
    src: Path, out_prefix: Path, exe: Path,
    w: int, h: int, fpsn: int, fpsd: int,
    gop: int = 10, route_span: int = 20,
):
    raw = src.read_bytes()
    fs = frame_size(w, h)
    if len(raw) % fs:
        raise RuntimeError("incomplete source frames")
    total = len(raw) // fs

    entries_r4 = []
    entries_r6 = []
    entries_oracle = []
    windows = []

    time_r4 = 0.0
    time_r6 = 0.0
    time_oracle = 0.0

    with tempfile.TemporaryDirectory(prefix="ksv13_enc_") as td:
        tmp = Path(td)

        for gi, off in enumerate(range(0, total, route_span)):
            n = min(route_span, total - off)
            chunk = raw[off * fs:(off + n) * fs]

            temp = temp_candidate(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, f"w{gi}"
            )
            r4, r4_search_s = radius_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, R4, f"w{gi}"
            )
            r6, r6_search_s = radius_candidates(
                chunk, exe, tmp, w, h, fpsn, fpsd, gop, R6, f"w{gi}"
            )

            c4 = choose([temp, *r4])
            c6 = choose([temp, *r6])
            co = choose([temp, *r4, *r6])

            for e in (c4, c6, co):
                e["frames"] = n

            entries_r4.append(dict(c4))
            entries_r6.append(dict(c6))
            entries_oracle.append(dict(co))

            temp_cost = temp["frontend_seconds"] + temp["backend_seconds"]
            r4_cost = (
                r4_search_s
                + sum(x["backend_seconds"] for x in r4)
            )
            r6_cost = (
                r6_search_s
                + sum(x["backend_seconds"] for x in r6)
            )
            time_r4 += temp_cost + r4_cost
            time_r6 += temp_cost + r6_cost
            time_oracle += temp_cost + r4_cost + r6_cost

            windows.append({
                "window": gi,
                "frames": n,
                "temp_bytes": len(temp["payload"]),
                "r4_mod8_bytes": len(r4[0]["payload"]),
                "r4_zz_bytes": len(r4[1]["payload"]),
                "r6_mod8_bytes": len(r6[0]["payload"]),
                "r6_zz_bytes": len(r6[1]["payload"]),
                "r4_mean_mag": r4[0]["mean_mag"],
                "r6_mean_mag": r6[0]["mean_mag"],
                "r4_selected": c4["label"],
                "r6_selected": c6["label"],
                "oracle_selected": co["label"],
            })

    paths = {
        "r4": out_prefix.with_suffix(".r4.k13"),
        "r6": out_prefix.with_suffix(".r6.k13"),
        "oracle": out_prefix.with_suffix(".oracle.k13"),
    }
    write_stream(paths["r4"], w, h, fpsn, fpsd, gop, route_span, entries_r4)
    write_stream(paths["r6"], w, h, fpsn, fpsd, gop, route_span, entries_r6)
    write_stream(
        paths["oracle"], w, h, fpsn, fpsd, gop, route_span, entries_oracle
    )

    return {
        "paths": paths,
        "r4": {
            "bytes": paths["r4"].stat().st_size,
            "encode_research_seconds": time_r4,
            "modes": policy_stats(entries_r4),
        },
        "r6": {
            "bytes": paths["r6"].stat().st_size,
            "encode_research_seconds": time_r6,
            "modes": policy_stats(entries_r6),
        },
        "oracle": {
            "bytes": paths["oracle"].stat().st_size,
            "encode_research_seconds": time_oracle,
            "modes": policy_stats(entries_oracle),
        },
        "windows": windows,
    }


def parse_clip(spec: str):
    p = spec.split(":")
    if len(p) != 6:
        raise argparse.ArgumentTypeError(
            "--clip must be name:path:width:height:fps_num:fps_den"
        )
    return {
        "name": p[0],
        "path": Path(p[1]).resolve(),
        "w": int(p[2]),
        "h": int(p[3]),
        "fpsn": int(p[4]),
        "fpsd": int(p[5]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kephir", type=Path, required=True)
    ap.add_argument("--clip", action="append", type=parse_clip, required=True)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    rows = []
    for clip in args.clip:
        src = clip["path"]
        prefix = OUT / clip["name"]
        enc = encode_source(
            src, prefix, args.kephir,
            clip["w"], clip["h"], clip["fpsn"], clip["fpsd"],
        )

        dec_info = {}
        for policy in ("r4", "r6", "oracle"):
            dec = OUT / f"{clip['name']}.{policy}.decoded.yuv"
            t0 = time.perf_counter()
            decode_stream(enc["paths"][policy], dec, args.kephir)
            seconds = time.perf_counter() - t0
            ok = sha_file(dec) == sha_file(src)
            if not ok:
                raise RuntimeError(f"{clip['name']} {policy}: SHA mismatch")
            dec_info[policy] = {
                "decode_seconds": seconds,
                "sha_ok": True,
            }

        raw_bytes = src.stat().st_size
        row = {
            "name": clip["name"],
            "raw_bytes": raw_bytes,
            "sha256": sha_file(src),
            "r4": {**enc["r4"], **dec_info["r4"]},
            "r6": {**enc["r6"], **dec_info["r6"]},
            "oracle": {**enc["oracle"], **dec_info["oracle"]},
            "windows": enc["windows"],
        }

        for policy in ("r4", "r6", "oracle"):
            row[policy]["ratio_percent"] = (
                100.0 * row[policy]["bytes"] / raw_bytes
            )

        row["r6_delta_vs_r4_bytes"] = row["r6"]["bytes"] - row["r4"]["bytes"]
        row["r6_delta_vs_r4_percent"] = (
            100.0 * (row["r6"]["bytes"] / row["r4"]["bytes"] - 1.0)
        )
        row["oracle_delta_vs_r4_bytes"] = (
            row["oracle"]["bytes"] - row["r4"]["bytes"]
        )
        row["oracle_delta_vs_r4_percent"] = (
            100.0 * (row["oracle"]["bytes"] / row["r4"]["bytes"] - 1.0)
        )

        rows.append(row)
        print(
            "KSV13_SOURCE_PASS",
            clip["name"],
            "r4", row["r4"]["bytes"],
            "r6", row["r6"]["bytes"],
            "oracle", row["oracle"]["bytes"],
            "r6_delta_pct", f"{row['r6_delta_vs_r4_percent']:.6f}",
            "oracle_delta_pct", f"{row['oracle_delta_vs_r4_percent']:.6f}",
            flush=True,
        )

    aggregate = {}
    for policy in ("r4", "r6", "oracle"):
        total = sum(r[policy]["bytes"] for r in rows)
        aggregate[policy] = {
            "bytes": total,
            "ratio_percent": 100.0 * total / sum(r["raw_bytes"] for r in rows),
            "encode_research_seconds": sum(
                r[policy]["encode_research_seconds"] for r in rows
            ),
        }

    aggregate["r6_delta_vs_r4_bytes"] = (
        aggregate["r6"]["bytes"] - aggregate["r4"]["bytes"]
    )
    aggregate["r6_delta_vs_r4_percent"] = (
        100.0 * (aggregate["r6"]["bytes"] / aggregate["r4"]["bytes"] - 1.0)
    )
    aggregate["oracle_delta_vs_r4_bytes"] = (
        aggregate["oracle"]["bytes"] - aggregate["r4"]["bytes"]
    )
    aggregate["oracle_delta_vs_r4_percent"] = (
        100.0 * (
            aggregate["oracle"]["bytes"] / aggregate["r4"]["bytes"] - 1.0
        )
    )

    result = {
        "experiment": "KSV-13 natural motion radius sweep",
        "block": BLOCK,
        "radii": [R4, R6],
        "route_span": 20,
        "gop": 10,
        "rows": rows,
        "aggregate": aggregate,
        "notes": [
            "R4 and R6 policies each compare TEMP, MOD8 and ZZ_INTER for their radius.",
            "ORACLE compares all five candidates and is research-only.",
            "All three emitted streams are independently decoded and SHA verified.",
            "Research encode seconds include duplicate candidate work and are not production throughput.",
        ],
    }

    (OUT / "KSV13_RESULTS.json").write_text(json.dumps(result, indent=2))

    print("KSV13_RADIUS_SWEEP_PASS")
    print(
        "KSV13_AGGREGATE",
        "r4", aggregate["r4"]["bytes"],
        "r6", aggregate["r6"]["bytes"],
        "oracle", aggregate["oracle"]["bytes"],
        "r6_delta_pct", f"{aggregate['r6_delta_vs_r4_percent']:.6f}",
        "oracle_delta_pct", f"{aggregate['oracle_delta_vs_r4_percent']:.6f}",
    )


if __name__ == "__main__":
    main()
