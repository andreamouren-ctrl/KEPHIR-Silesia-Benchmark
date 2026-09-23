#!/usr/bin/env python3
import argparse
import struct
import zlib
from pathlib import Path

MAGIC = b"KSP0"
VERSION = 1
HDR = struct.Struct("<4sBBHIIQ")
CHUNK = struct.Struct("<III")


def zz_enc(v: int) -> int:
    return (v << 1) ^ (v >> 63)


def zz_dec(u: int) -> int:
    return (u >> 1) ^ -(u & 1)


def put_varint(out: bytearray, u: int):
    if u < 0:
        raise ValueError("negative varint")
    while u >= 0x80:
        out.append((u & 0x7F) | 0x80)
        u >>= 7
    out.append(u)


def get_varint(buf: bytes, pos: int):
    u = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        b = buf[pos]
        pos += 1
        u |= (b & 0x7F) << shift
        if not (b & 0x80):
            return u, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint overflow")


def encode_block(samples, channels):
    out = bytearray()
    if channels == 2:
        prev = [0, 0]
        for i in range(0, len(samples), 2):
            left, right = samples[i], samples[i + 1]
            side = left - right
            mid = right + (side >> 1)
            for c, x in enumerate((mid, side)):
                delta = x - prev[c]
                prev[c] = x
                put_varint(out, zz_enc(delta))
    else:
        prev = [0] * channels
        for i, x in enumerate(samples):
            c = i % channels
            delta = x - prev[c]
            prev[c] = x
            put_varint(out, zz_enc(delta))
    return bytes(out)


def decode_block(payload, channels, frames):
    values = []
    pos = 0
    if channels == 2:
        prev = [0, 0]
        for _ in range(frames):
            cur = []
            for c in range(2):
                u, pos = get_varint(payload, pos)
                x = prev[c] + zz_dec(u)
                prev[c] = x
                cur.append(x)
            mid, side = cur
            right = mid - (side >> 1)
            left = side + right
            if not (-32768 <= left <= 32767 and -32768 <= right <= 32767):
                raise ValueError("decoded sample out of s16 range")
            values.extend((left, right))
    else:
        prev = [0] * channels
        for i in range(frames * channels):
            c = i % channels
            u, pos = get_varint(payload, pos)
            x = prev[c] + zz_dec(u)
            prev[c] = x
            if not -32768 <= x <= 32767:
                raise ValueError("decoded sample out of s16 range")
            values.append(x)

    if pos != len(payload):
        raise ValueError("trailing bytes in chunk")
    return values


def encode_file(src: Path, dst: Path, channels: int, rate: int, block_ms: int):
    raw = src.read_bytes()
    frame_bytes = 2 * channels
    if len(raw) % frame_bytes:
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
            payload = encode_block(samples, channels)
            f.write(CHUNK.pack(frames, len(payload), zlib.crc32(payload) & 0xFFFFFFFF))
            f.write(payload)
            offset += frames


def decode_file(src: Path, dst: Path):
    data = src.read_bytes()
    if len(data) < HDR.size:
        raise SystemExit("truncated header")

    magic, version, channels, bits, rate, block_ms, total_frames = HDR.unpack_from(data, 0)
    if magic != MAGIC or version != VERSION or bits != 16 or channels < 1:
        raise SystemExit("unsupported stream")

    pos = HDR.size
    out = bytearray()
    got_frames = 0

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

        samples = decode_block(payload, channels, frames)
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
