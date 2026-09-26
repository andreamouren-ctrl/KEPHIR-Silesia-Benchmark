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
VERSION = 2
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


def pack_classes_rle(classes):
    out = bytearray()
    i = 0
    while i < len(classes):
        c = classes[i]
        j = i + 1
        while j < len(classes) and classes[j] == c and j - i < 64:
            j += 1
        out.append(((c & 3) << 6) | ((j - i - 1) & 0x3F))
        i = j
    return bytes(out)


def unpack_classes_rle(buf: bytes, pos: int, n: int):
    out = []
    while len(out) < n:
        if pos >= len(buf):
            raise ValueError("truncated RLE class field")
        b = buf[pos]
        pos += 1
        c = (b >> 6) & 3
        run = (b & 0x3F) + 1
        if len(out) + run > n:
            raise ValueError("RLE class overflow")
        out.extend([c] * run)
    return out, pos


def encode_component(values, classmap_mode="adaptive"):
    candidates = []
    for mode in (0, 1, 2):
        rs = residuals_for(values, mode)
        us = [zz_enc(r) for r in rs]
        candidates.append((representation_cost(us), mode, us))
    _, mode, us = min(candidates, key=lambda x: (x[0], x[1]))

    classes = [residual_class(u) for u in us]
    raw_classes = pack_classes(classes)
    rle_classes = pack_classes_rle(classes)
    if classmap_mode == "raw":
        use_rle = False
    elif classmap_mode == "rle":
        use_rle = True
    elif classmap_mode == "adaptive":
        use_rle = len(rle_classes) < len(raw_classes)
    else:
        raise ValueError("bad class-map mode")

    # Predictor byte: low 2 bits predictor, bit 7 class-map RLE flag.
    out = bytearray([mode | (0x80 if use_rle else 0)])
    out.extend(rle_classes if use_rle else raw_classes)

    c0 = [u for u, c in zip(us, classes) if c == 0]
    c1 = [u for u, c in zip(us, classes) if c == 1]
    c2 = [u for u, c in zip(us, classes) if c == 2]
    c3 = [u for u, c in zip(us, classes) if c == 3]

    for i in range(0, len(c0), 2):
        a = c0[i] & 0xF
        b = (c0[i + 1] & 0xF) if i + 1 < len(c0) else 0
        out.append(a | (b << 4))

    out.extend(u & 0xFF for u in c1)
    out.extend(u & 0xFF for u in c2)
    out.extend((u >> 8) & 0xFF for u in c2)

    for shift in (0, 8, 16, 24):
        out.extend((u >> shift) & 0xFF for u in c3)

    return bytes(out)


def decode_component(buf: bytes, pos: int, n: int):
    if pos >= len(buf):
        raise ValueError("truncated component")
    control = buf[pos]
    pos += 1
    mode = control & 0x03
    use_rle = bool(control & 0x80)
    if control & 0x7C:
        raise ValueError("bad component control flags")
    if mode not in (0, 1, 2):
        raise ValueError("bad predictor mode")

    if use_rle:
        classes, pos = unpack_classes_rle(buf, pos, n)
    else:
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


def sample_limits(bits: int):
    if bits not in (16, 24, 32):
        raise ValueError("unsupported PCM bit depth")
    lo = -(1 << (bits - 1))
    hi = (1 << (bits - 1)) - 1
    return lo, hi


def unpack_pcm_le(raw: bytes, bits: int):
    if bits == 16:
        if len(raw) % 2:
            raise ValueError("unaligned s16le payload")
        return list(struct.unpack("<" + "h" * (len(raw) // 2), raw))
    if bits == 24:
        if len(raw) % 3:
            raise ValueError("unaligned s24le payload")
        out = []
        for i in range(0, len(raw), 3):
            u = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if u & 0x800000:
                u -= 1 << 24
            out.append(u)
        return out
    if bits == 32:
        if len(raw) % 4:
            raise ValueError("unaligned s32le payload")
        return list(struct.unpack("<" + "i" * (len(raw) // 4), raw))
    raise ValueError("unsupported PCM bit depth")


def pack_pcm_le(samples, bits: int):
    lo, hi = sample_limits(bits)
    for x in samples:
        if not lo <= x <= hi:
            raise ValueError("decoded sample out of range")
    if bits == 16:
        return struct.pack("<" + "h" * len(samples), *samples)
    if bits == 24:
        out = bytearray()
        for x in samples:
            u = x & 0xFFFFFF
            out.extend((u & 0xFF, (u >> 8) & 0xFF, (u >> 16) & 0xFF))
        return bytes(out)
    if bits == 32:
        return struct.pack("<" + "i" * len(samples), *samples)
    raise ValueError("unsupported PCM bit depth")


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


def pair_forward(a, b):
    side = [x - y for x, y in zip(a, b)]
    mid = [y + (s >> 1) for y, s in zip(b, side)]
    return mid, side


def pair_inverse(mid, side):
    b = [m - (s >> 1) for m, s in zip(mid, side)]
    a = [s + y for s, y in zip(side, b)]
    return a, b


def hierarchical_components(comps):
    out = [list(x) for x in comps]
    if len(out) >= 2:
        out[0], out[1] = pair_forward(out[0], out[1])
    if len(out) >= 6:
        out[4], out[5] = pair_forward(out[4], out[5])
    if len(out) >= 8:
        out[6], out[7] = pair_forward(out[6], out[7])
    if len(out) >= 3:
        out[0], out[2] = pair_forward(out[0], out[2])
    return out


def inverse_hierarchical_components(comps):
    out = [list(x) for x in comps]
    if len(out) >= 3:
        out[0], out[2] = pair_inverse(out[0], out[2])
    if len(out) >= 8:
        out[6], out[7] = pair_inverse(out[6], out[7])
    if len(out) >= 6:
        out[4], out[5] = pair_inverse(out[4], out[5])
    if len(out) >= 2:
        out[0], out[1] = pair_inverse(out[0], out[1])
    return out


def quick_predictive_cost(comps):
    cost = 0
    for values in comps:
        if not values:
            continue
        prev = values[0]
        for i in range(8, len(values), 16):
            x = values[i]
            cost += abs(x - prev)
            prev = x
    return cost


def choose_multichannel_transform(comps, bits, mode="adaptive"):
    if bits != 32 or len(comps) < 6:
        return 0, comps
    if mode == "independent":
        return 0, comps
    transformed = hierarchical_components(comps)
    if mode == "hierarchical":
        return 1, transformed
    base_cost = quick_predictive_cost(comps)
    hier_cost = quick_predictive_cost(transformed)
    if hier_cost * 1000 < base_cost * 995:
        return 1, transformed
    return 0, comps


def merge_components(comps, channels, bits):
    lo, hi = sample_limits(bits)
    if channels == 2:
        out = []
        for mid, side in zip(comps[0], comps[1]):
            right = mid - (side >> 1)
            left = side + right
            if not (lo <= left <= hi and lo <= right <= hi):
                raise ValueError("decoded stereo sample out of range")
            out.extend((left, right))
        return out

    out = []
    for i in range(len(comps[0])):
        for c in range(channels):
            x = comps[c][i]
            if not lo <= x <= hi:
                raise ValueError("decoded sample out of range")
            out.append(x)
    return out


def encode_payload(samples, channels, frames, bits, multichannel_mode="adaptive",
                   classmap_mode="adaptive"):
    out = bytearray()
    frame_pos = 0
    while frame_pos < frames:
        tile_frames = min(TILE_FRAMES, frames - frame_pos)
        begin = frame_pos * channels
        end = (frame_pos + tile_frames) * channels
        comps = split_components(samples[begin:end], channels)
        transform, comps = choose_multichannel_transform(
            comps, bits, multichannel_mode
        )
        if bits == 32 and channels >= 6:
            out.append(transform)
        for comp in comps:
            out.extend(encode_component(comp, classmap_mode))
        frame_pos += tile_frames
    return bytes(out)


def decode_payload(payload: bytes, channels: int, frames: int, bits: int, version=VERSION):
    pos = 0
    out = []
    frame_pos = 0
    while frame_pos < frames:
        tile_frames = min(TILE_FRAMES, frames - frame_pos)
        transform = 0
        if version >= 2 and bits == 32 and channels >= 6:
            if pos >= len(payload):
                raise ValueError("truncated multichannel transform mode")
            transform = payload[pos]
            pos += 1
            if transform not in (0, 1):
                raise ValueError("bad multichannel transform mode")
        comps = []
        for _ in range(channels):
            comp, pos = decode_component(payload, pos, tile_frames)
            comps.append(comp)
        if transform == 1:
            comps = inverse_hierarchical_components(comps)
        out.extend(merge_components(comps, channels, bits))
        frame_pos += tile_frames
    if pos != len(payload):
        raise ValueError("trailing KMRL payload")
    return out


def encode_file(src: Path, dst: Path, channels: int, rate: int, bits: int, block_ms: int,
                multichannel_mode="adaptive", classmap_mode="adaptive"):
    raw = src.read_bytes()
    if channels < 1:
        raise SystemExit("invalid channel count")
    if bits not in (16, 24, 32):
        raise SystemExit("unsupported PCM bit depth")
    bytes_per_sample = bits // 8
    frame_bytes = bytes_per_sample * channels
    if len(raw) % frame_bytes:
        raise SystemExit("input is not whole PCM frames")

    total_frames = len(raw) // frame_bytes
    block_frames = max(1, rate * block_ms // 1000)

    with dst.open("wb") as f:
        f.write(HDR.pack(MAGIC, VERSION, channels, bits, rate, block_ms, total_frames))
        offset = 0
        while offset < total_frames:
            frames = min(block_frames, total_frames - offset)
            block = raw[offset * frame_bytes:(offset + frames) * frame_bytes]
            samples = unpack_pcm_le(block, bits)
            payload = encode_payload(samples, channels, frames, bits,
                                     multichannel_mode, classmap_mode)
            f.write(CHUNK.pack(frames, len(payload), zlib.crc32(payload) & 0xFFFFFFFF))
            f.write(payload)
            offset += frames


def decode_file(src: Path, dst: Path):
    data = src.read_bytes()
    if len(data) < HDR.size:
        raise SystemExit("truncated header")

    magic, version, channels, bits, rate, block_ms, total_frames = HDR.unpack_from(data, 0)
    if magic != MAGIC or version not in (1, 2) or bits not in (16, 24, 32) or channels < 1:
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

        samples = decode_payload(payload, channels, frames, bits, version)
        out.extend(pack_pcm_le(samples, bits))
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
    enc.add_argument("--bits", type=int, choices=(16, 24, 32), required=True)
    enc.add_argument("--block-ms", type=int, default=20)
    enc.add_argument("--multichannel-mode", choices=("adaptive", "independent", "hierarchical"), default="adaptive")
    enc.add_argument("--classmap-mode", choices=("adaptive", "raw", "rle"), default="adaptive")

    dec = sp.add_parser("decode")
    dec.add_argument("src", type=Path)
    dec.add_argument("dst", type=Path)

    args = ap.parse_args()
    if args.cmd == "encode":
        encode_file(args.src, args.dst, args.channels, args.rate, args.bits,
                    args.block_ms, args.multichannel_mode, args.classmap_mode)
    else:
        decode_file(args.src, args.dst)


if __name__ == "__main__":
    main()
