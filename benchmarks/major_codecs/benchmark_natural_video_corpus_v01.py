#!/usr/bin/env python3
"""
AURORA Media Natural Video Corpus v1.

Compression-first validation on real uncompressed YUV420p sequences.
All decoded outputs are SHA-256 verified against the exact raw input.

Timing is recorded for diagnostics but is NOT a normalized speed comparison:
the current AURORA full-stack reference path still includes Python orchestration
and subprocess-backed KHEPRI, while external codecs use ffmpeg wrappers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from aurora_media_container import (
    AuroraMuxer, AuroraDemuxer, Track,
    TRACK_VIDEO, CODEC_AURORA_VIDEO,
    PKT_KEY, PKT_RECOVERY,
)
from aurora_media_codec_bridge import encode_video_packet, decode_video_packet

OUT = Path("results/benchmarks/natural_video_corpus_v1")
GOP = 10
VIDEO_PACKET_FRAMES = 20
TIMESCALE = 1_000_000


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timed(cmd):
    t0 = time.perf_counter()
    cp = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cp.returncode, time.perf_counter() - t0


def us_video(frames: int, fpsn: int, fpsd: int) -> int:
    return frames * TIMESCALE * fpsd // fpsn


def parse_clip(spec: str):
    parts = spec.split(":")
    if len(parts) != 7:
        raise argparse.ArgumentTypeError(
            "--clip must be name:path:width:height:fps_num:fps_den:motion_class"
        )
    name, raw, w, h, fpsn, fpsd, motion_class = parts
    return {
        "name": name,
        "path": Path(raw).resolve(),
        "width": int(w),
        "height": int(h),
        "fpsn": int(fpsn),
        "fpsd": int(fpsd),
        "motion_class": motion_class,
    }


def aurora_video_file(clip, exe: Path):
    raw = clip["path"]
    w = clip["width"]
    h = clip["height"]
    fpsn = clip["fpsn"]
    fpsd = clip["fpsd"]
    frame_bytes = w * h * 3 // 2

    yuv = raw.read_bytes()
    if len(yuv) % frame_bytes:
        raise RuntimeError(f"{clip['name']}: raw input is not frame aligned")
    frames = len(yuv) // frame_bytes
    out = OUT / f"{clip['name']}_aurora.aum"

    encode_seconds = 0.0
    with AuroraMuxer(
        out,
        [Track(2, TRACK_VIDEO, CODEC_AURORA_VIDEO, 0, w, h, fpsn, fpsd)],
    ) as mux:
        for f0 in range(0, frames, VIDEO_PACKET_FRAMES):
            n = min(VIDEO_PACKET_FRAMES, frames - f0)
            chunk = yuv[f0 * frame_bytes:(f0 + n) * frame_bytes]
            t0 = time.perf_counter()
            payload = encode_video_packet(
                chunk, exe, w, h, fpsn, fpsd, GOP, VIDEO_PACKET_FRAMES
            )
            encode_seconds += time.perf_counter() - t0
            mux.write_packet(
                2,
                us_video(f0, fpsn, fpsd),
                us_video(n, fpsn, fpsd),
                payload,
                PKT_KEY | PKT_RECOVERY,
            )

    restored = bytearray()
    decode_seconds = 0.0
    with AuroraDemuxer(out) as demux:
        for _, payload in demux.packets(2):
            t0 = time.perf_counter()
            restored.extend(decode_video_packet(payload, exe))
            decode_seconds += time.perf_counter() - t0

    if sha_bytes(bytes(restored)) != sha_bytes(yuv):
        raise RuntimeError(f"{clip['name']}: AURORA SHA mismatch")

    return {
        "codec": "AURORA Media",
        "available": True,
        "bytes": out.stat().st_size,
        "encode_seconds": encode_seconds,
        "decode_seconds": decode_seconds,
        "sha_ok": True,
        "packets": (frames + VIDEO_PACKET_FRAMES - 1) // VIDEO_PACKET_FRAMES,
    }


def video_ref(clip, label: str, args):
    raw = clip["path"]
    w = clip["width"]
    h = clip["height"]
    fpsn = clip["fpsn"]
    fpsd = clip["fpsd"]
    out = OUT / f"{clip['name']}_{label}.mkv"
    dec = OUT / f"{clip['name']}_{label}.yuv"

    inp = [
        "-f", "rawvideo",
        "-pix_fmt", "yuv420p",
        "-s:v", f"{w}x{h}",
        "-r", f"{fpsn}/{fpsd}",
        "-i", str(raw),
    ]
    rc, encode_seconds = timed([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *inp, *args, str(out),
    ])
    if rc:
        return {"codec": label, "available": False}

    rc, decode_seconds = timed([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(out),
        "-pix_fmt", "yuv420p",
        "-f", "rawvideo",
        str(dec),
    ])
    ok = rc == 0 and sha_file(dec) == sha_file(raw)

    return {
        "codec": label,
        "available": True,
        "bytes": out.stat().st_size,
        "encode_seconds": encode_seconds,
        "decode_seconds": decode_seconds,
        "sha_ok": ok,
    }


def benchmark_clip(clip, exe: Path):
    raw = clip["path"]
    w = clip["width"]
    h = clip["height"]
    fpsn = clip["fpsn"]
    fpsd = clip["fpsd"]
    frame_bytes = w * h * 3 // 2
    raw_bytes = raw.stat().st_size
    if raw_bytes % frame_bytes:
        raise RuntimeError(f"{clip['name']}: raw size/frame geometry mismatch")
    frames = raw_bytes // frame_bytes
    duration = frames * fpsd / fpsn

    rows = [
        aurora_video_file(clip, exe),
        video_ref(
            clip,
            "FFV1",
            ["-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-g", str(GOP)],
        ),
        video_ref(
            clip,
            "H264_lossless",
            ["-c:v", "libx264", "-preset", "medium", "-qp", "0", "-g", str(GOP)],
        ),
        video_ref(
            clip,
            "HEVC_lossless",
            ["-c:v", "libx265", "-preset", "medium",
             "-x265-params", f"lossless=1:keyint={GOP}:log-level=error"],
        ),
        video_ref(
            clip,
            "VP9_lossless",
            ["-c:v", "libvpx-vp9", "-lossless", "1",
             "-deadline", "good", "-cpu-used", "2", "-g", str(GOP)],
        ),
        video_ref(
            clip,
            "AV1_lossless",
            ["-c:v", "libaom-av1", "-crf", "0", "-b:v", "0",
             "-cpu-used", "6", "-g", str(GOP)],
        ),
    ]

    for row in rows:
        if row.get("available", True) and "bytes" in row:
            row["ratio_percent"] = 100.0 * row["bytes"] / raw_bytes
            row["bits_per_pixel"] = 8.0 * row["bytes"] / (w * h * frames)
            row["encode_realtime_x"] = duration / row["encode_seconds"]
            row["decode_realtime_x"] = duration / row["decode_seconds"]

    return {
        "name": clip["name"],
        "motion_class": clip["motion_class"],
        "width": w,
        "height": h,
        "fps": f"{fpsn}/{fpsd}",
        "frames": frames,
        "raw_bytes": raw_bytes,
        "sha256": sha_file(raw),
        "rows": rows,
    }


def make_aggregate(clips):
    totals = {}
    total_raw = sum(c["raw_bytes"] for c in clips)

    for clip in clips:
        for row in clip["rows"]:
            if not row.get("available", True) or "bytes" not in row or not row.get("sha_ok", False):
                continue
            item = totals.setdefault(row["codec"], {
                "codec": row["codec"],
                "bytes": 0,
                "source_count": 0,
            })
            item["bytes"] += row["bytes"]
            item["source_count"] += 1

    aggregate = []
    for item in totals.values():
        item["ratio_percent"] = 100.0 * item["bytes"] / total_raw
        aggregate.append(item)
    aggregate.sort(key=lambda x: x["bytes"])
    return total_raw, aggregate


def write_markdown(result):
    lines = [
        "# AURORA Media Natural Video Corpus v1",
        "",
        "Compression-first real-content benchmark. All reported codec outputs are losslessly SHA verified.",
        "",
        "Timing values are diagnostic only and are not treated as normalized speed comparisons.",
        "",
        "## Aggregate",
        "",
        "| Codec | Bytes | Ratio to raw | Sources |",
        "|---|---:|---:|---:|",
    ]
    for row in result["aggregate"]:
        lines.append(
            f"| {row['codec']} | {row['bytes']:,} | "
            f"{row['ratio_percent']:.3f}% | {row['source_count']} |"
        )

    for clip in result["clips"]:
        lines.extend([
            "",
            f"## {clip['name']} ({clip['motion_class']})",
            "",
            f"{clip['width']}x{clip['height']}, {clip['frames']} frames, raw {clip['raw_bytes']:,} bytes.",
            "",
            "| Codec | Bytes | Ratio | SHA |",
            "|---|---:|---:|---:|",
        ])
        for row in clip["rows"]:
            if not row.get("available", True):
                lines.append(f"| {row['codec']} | unavailable | - | - |")
            else:
                lines.append(
                    f"| {row['codec']} | {row['bytes']:,} | "
                    f"{row['ratio_percent']:.3f}% | {'PASS' if row['sha_ok'] else 'FAIL'} |"
                )

    (OUT / "NATURAL_VIDEO_CORPUS_V1_RESULTS.md").write_text(
        "\n".join(lines) + "\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kephir", type=Path, required=True)
    ap.add_argument("--clip", action="append", type=parse_clip, required=True)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    clips = []
    for clip in args.clip:
        row = benchmark_clip(clip, args.kephir)
        clips.append(row)
        print(
            "NATURAL_CLIP_PASS",
            clip["name"],
            clip["motion_class"],
            "raw_bytes", row["raw_bytes"],
            flush=True,
        )

    total_raw, aggregate = make_aggregate(clips)
    if not aggregate:
        raise RuntimeError("no complete codec results")

    result = {
        "experiment": "AURORA Media Natural Video Corpus v1",
        "date": "2026-09-26",
        "scope": "Final file sizes including AUM/MKV and codec/container overhead",
        "source_format": "uncompressed YUV420p derived from Xiph YUV4MPEG test media",
        "gop": GOP,
        "aurora_video_packet_frames": VIDEO_PACKET_FRAMES,
        "aggregate_raw_bytes": total_raw,
        "aggregate": aggregate,
        "clips": clips,
        "notes": [
            "All available lossless outputs are SHA-256 verified.",
            "Compression/file size is the primary comparison in this workflow.",
            "Timing is diagnostic because AURORA still uses Python/subprocess orchestration in this full-stack reference path.",
        ],
    }

    (OUT / "NATURAL_VIDEO_CORPUS_V1_RESULTS.json").write_text(
        json.dumps(result, indent=2)
    )
    write_markdown(result)

    print("AURORA_NATURAL_VIDEO_CORPUS_V1_PASS")
    for row in aggregate:
        print(
            "AGGREGATE",
            row["codec"],
            "bytes", row["bytes"],
            "ratio_percent", f"{row['ratio_percent']:.6f}",
            "sources", row["source_count"],
        )


if __name__ == "__main__":
    main()
