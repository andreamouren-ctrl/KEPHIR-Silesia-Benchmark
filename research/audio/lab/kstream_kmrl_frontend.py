#!/usr/bin/env python3
"""
KMRL-0: KHEPRI Media Residual Lattice research frontend.

This is an experimental reversible representation. It is not a patent claim.
The individual predictors and generic residual coding ideas are background
techniques; the research subject is the coupling of media residual geometry
to KHEPRI's 16/256 distance topology.
"""
import argparse
import struct
import zlib
from pathlib import Path

MAGIC = b"KMR1"
VERSION = 1
TILE_FRAMES = 256

HDR = struct.Struct("<4sBBHIIQ")
CHUNK = struct.Struct("<III")


def zz_enc(v: int) -> int:
    return (v << 1) ^ (v >> 63)


def zz_dec(u: int) -> int:
    return (u >> 1) ^ -(u & 1)


def predictor(mode: int, hist):
    n = len(hist)
    if mode == 0:
        return hist[-1] if n else 0
    if mode == 1:
        if n >= 2:
            return 2 * hist[-1] - hist[-2]
        return hist[-1] if n else 0
    if mode == 2:
        if n >= 3:
            return 3 * hist[-1] - 3 * hist[-2] + hist[-3]
        if n >= 2:
            return 2 * hist[-1] - hist[-2]
        return hist[-1] if n else 0
    raise ValueError("bad predictor mode")


def residuals_for(values, mode: int):
    hist = []
    out = []
    for x in values:
        p = predictor(mode, hist)
        out.append(x - p)
        hist.append(x)
    return out


def residual_class(u: int) -> int:
    if u < 16:
        return 0
    if u < 256:
        return 1
    if u < 65536:
        return 2
    if u < (1 << 32):
        return 3
    raise ValueError("residual exceeds KMRL-0 range")


def pack_classes(classes):
    out = bytearray((len(classes) + 3) // 4)
    for i, c in enumerate(classes):
        out[i // 4] |= (c & 3) << ((i & 3) * 2)
    return bytes(out)


def unpack_classes(buf: bytes, n: int):
    out = []
    need = (n + 3) // 4
    if len(buf) < need:
        raise ValueError("truncated class field")
    for i in range(n):
        out.append((buf[i // 4] >> ((i & 3) * 2)) & 3)
    return out, need


def representation_cost(us):
    classes = [residual_class(u) for u in us]
    counts = [classes.count(i) for i in range(4)]
    # Exact serialized bytes for class field + magnitude fields.
    return ((len(us) + 3) // 4
            + (counts[0] + 1) // 2
            + counts[1]
            + 2 * counts[2]
            + 4 * counts[3])


def encode_component(values):
    candidates = []
    for mode in (0, 1, 2):
        rs = residuals_for(values, mode)
        us = [zz_enc(r) for r in rs]
        candidates.append((representation_cost(us), mode, us))
    _, mode, us = min(candidates, key=lambda x: (x[0], x[1]))

    classes = [residual_class(u) for u in us]
    out = bytearray([mode])
    out.extend(pack_classes(classes))

    c0 = [u for u, c in zip(us, classes) if c == 0]
    c1 = [u for u, c in zip(us, classes) if c == 1]
    c2 = [u for u, c in zip(us, classes) if c == 2]
    c3 = [u for u, c in zip(us, classes) if c == 3]

    # 4-bit field.
    for i in range(0, len(c0), 2):
        a = c0[i] & 0xF
        b = (c0[i + 1] & 0xF) if i + 1 < len(c0) else 0
        out.append(a | (b << 4))

    # 8-bit field.
    out.extend(u & 0xFF for u in c1)

    # 16-bit values serialized as byte-significance planes.
    out.extend(u & 0xFF for u in c2)
    out.extend((u >> 8) & 0xFF for u in c2)

    # 32-bit values serialized as four byte-significance planes.
    for shift in (0, 8, 16, 24):
        out.extend((u >> shift) & 0xFF for u in c3)

    return bytes(out)


def decode_component(buf: bytes, pos: int, n: int):
    if pos >= len(buf):
        raise ValueError("truncated component")
    mode = buf[pos]
    pos += 1
    if mode not in (0, 1, 2):
        raise ValueError("bad predictor mode")

    classes, used = unpack_classes(buf[pos:], n)
    pos += used
    counts = [classes.count(i) for i in range(4)]

    n0b = (counts[0] + 1) // 2
    if pos + n0b > len(buf):
        raise ValueError("truncated class-0 field")
    packed0 = buf[pos:pos + n0b]
    pos += n0b
    c0 = []
    for i in range(counts[0]):
        c0.append((packed0[i // 2] >> (4 * (i & 1))) & 0xF)

    if pos + counts[1] > len(buf):
        raise ValueError("truncated class-1 field")
    c1 = list(buf[pos:pos + counts[1]])
    pos += counts[1]

    if pos + 2 * counts[2] > len(buf):
        raise ValueError("truncated class-2 field")
    lo2 = buf[pos:pos + counts[2]]
    pos += counts[2]
    hi2 = buf[pos:pos + counts[2]]
    pos += counts[2]
    c2 = [lo2[i] | (hi2[i] << 8) for i in range(counts[2])]

    if pos + 4 * counts[3] > len(buf):
        raise ValueError("truncated class-3 field")
    planes = []
    for _ in range(4):
        planes.append(buf[pos:pos + counts[3]])
        pos += counts[3]
    c3 = [
        planes[0][i]
        | (planes[1][i] << 8)
        | (planes[2][i] << 16)
        | (planes[3][i] << 24)
        for i in range(counts[3])
    ]

    idx = [0, 0, 0, 0]
    pools = [c0, c1, c2, c3]
    hist = []
    values = []
    for c in classes:
        u = pools[c][idx[c]]
        idx[c] += 1
        r = zz_dec(u)
        x = predictor(mode, hist) + r
        hist.append(x)
        values.append(x)

    return values, pos


def split_components(samples, channels):
    if channels == 2:
        a, b = [], []
        for i in range(0, len(samples), 2):
            left, right = samples[i], samples[i + 1]
            side = left - right
            mid = right + (side >> 1)
            a.append(mid)
            b.append(side)
        return [a, b]

    comps = [[] for _ in range(channels)]
    for i, x in enumerate(samples):
        comps[i % channels].append(x)
    return comps


def merge_components(comps, channels):
    if channels == 2:
        out = []
        for mid, side in zip(comps[0], comps[1]):
            right = mid - (side >> 1)
            left = side + right
            if not (-32768 <= left <= 32767 and -32768 <= right <= 32767):
                raise ValueError("decoded stereo sample out of range")
            out.extend((left, right))
        return out

    out = []
    for i in range(len(comps[0])):
        for c in range(channels):
            x = comps[c][i]
            if not -32768 <= x <= 32767:
                raise ValueError("decoded sample out of range")
            out.append(x)
    return out


def encode_payload(samples, channels, frames):
    out = bytearray()
    frame_pos = 0
    while frame_pos < frames:
        tile_frames = min(TILE_FRAMES, frames - frame_pos)
        begin = frame_pos * channels
        end = (frame_pos + tile_frames) * channels
        comps = split_components(samples[begin:end], channels)
        for comp in comps:
            out.extend(encode_component(comp))
        frame_pos += tile_frames
    return bytes(out)


def decode_payload(payload: bytes, channels: int, frames: int):
    pos = 0
    out = []
    frame_pos = 0
    while frame_pos < frames:
        tile_frames = min(TILE_FRAMES, frames - frame_pos)
        comps = []
        for _ in range(channels):
            comp, pos = decode_component(payload, pos, tile_frames)
            comps.append(comp)
        out.extend(merge_components(comps, channels))
        frame_pos += tile_frames
    if pos != len(payload):
        raise ValueError("trailing KMRL payload")
    return out


def encode_file(src: Path, dst: Path, channels: int, rate: int, block_ms: int):
    raw = src.read_bytes()
    frame_bytes = 2 * channels
    if channels < 1 or len(raw) % frame_bytes:
        raise SystemExit("input is not whole s16le frames")

    total_frames = len(raw) // frame_bytes
    block_frames = max(1, rate * block_ms // 1000)

    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC, VERSION, channels, 16, rate, block_ms, total_frames))
        offset = 0
        while offset < total_frames:
            frames = min(block_frames, total_frames - offset)
            block = raw[offset * frame_bytes:(offset + frames) * frame_bytes]
            samples = list(struct.unpack("<" + "h" * (frames * channels), block))
            payload = encode_payload(samples, channels, frames)
            f.write(CHUNK.pack(frames, len(payload), zlib.crc32(payload) & 0xFFFFFFFF))
            f.write(payload)
            offset += frames


def decode_file(src: Path, dst: Path):
    data = src.read_bytes()
    if len(data) < HDR.size:
        raise SystemExit("truncated header")

    magic, version, channels, bits, rate, block_ms, total_frames = HDR.unpack_from(data, 0)
    if magic != MAGIC or version != VERSION or bits != 16 or channels < 1:
        raise SystemExit("unsupported KMRL stream")

    pos = HDR.size
    got_frames = 0
    out = bytearray()
    while got_frames < total_frames:
        if pos + CHUNK.size > len(data):
            raise SystemExit("truncated chunk header")
        frames, payload_size, crc = CHUNK.unpack_from(data, pos)
        pos += CHUNK.size
        if frames < 1 or got_frames + frames > total_frames or pos + payload_size > len(data):
            raise SystemExit("invalid chunk")
        payload = data[pos:pos + payload_size]
        pos += payload_size
        if (zlib.crc32(payload) & 0xFFFFFFFF) != crc:
            raise SystemExit("chunk CRC mismatch")

        samples = decode_payload(payload, channels, frames)
        out.extend(struct.pack("<" + "h" * len(samples), *samples))
        got_frames += frames

    if pos != len(data):
        raise SystemExit("trailing stream data")
    dst.write_bytes(out)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)

    enc = sp.add_parser("encode")
    enc.add_argument("src", type=Path)
    enc.add_argument("dst", type=Path)
    enc.add_argument("--channels", type=int, required=True)
    enc.add_argument("--rate", type=int, required=True)
    enc.add_argument("--block-ms", type=int, default=20)

    dec = sp.add_parser("decode")
    dec.add_argument("src", type=Path)
    dec.add_argument("dst", type=Path)

    args = ap.parse_args()
    if args.cmd == "encode":
        encode_file(args.src, args.dst, args.channels, args.rate, args.block_ms)
    else:
        decode_file(args.src, args.dst)


if __name__ == "__main__":
    main()
