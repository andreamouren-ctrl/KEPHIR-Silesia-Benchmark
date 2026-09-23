#!/usr/bin/env python3
"""
AURORA Stream Protocol v0.1

Original project framing for transporting AURORA Media packets over an ordered
byte stream. This is not a complete network stack; it defines deterministic
packet framing, sequencing, timing and integrity independently from TCP/UDP.
"""
from __future__ import annotations
import struct,zlib
from dataclasses import dataclass

MAGIC=b"AUS1"
VERSION=1
HDR=struct.Struct("<4sBBBBIQQIII")
# magic,ver,track,flags,reserved,seq,pts,duration,size,crc,reserved2

@dataclass(frozen=True)
class StreamPacket:
    sequence:int
    track_id:int
    flags:int
    pts:int
    duration:int
    payload:bytes

def encode_packet(p:StreamPacket)->bytes:
    if not (0<=p.sequence<=0xffffffff): raise ValueError("sequence")
    if not (0<=p.track_id<=255): raise ValueError("track")
    crc=zlib.crc32(p.payload)&0xffffffff
    return HDR.pack(MAGIC,VERSION,p.track_id,p.flags,0,p.sequence,p.pts,p.duration,len(p.payload),crc,0)+p.payload

def decode_packet(buf:bytes)->StreamPacket:
    if len(buf)<HDR.size: raise ValueError("truncated stream packet")
    m,v,tid,flags,_,seq,pts,dur,sz,crc,_=HDR.unpack_from(buf,0)
    if m!=MAGIC or v!=VERSION: raise ValueError("unsupported stream packet")
    if len(buf)!=HDR.size+sz: raise ValueError("stream packet size")
    payload=buf[HDR.size:]
    if zlib.crc32(payload)&0xffffffff!=crc: raise ValueError("stream packet CRC")
    return StreamPacket(seq,tid,flags,pts,dur,payload)

class StreamReceiver:
    def __init__(self):
        self.next_sequence=0
    def accept(self,wire:bytes)->StreamPacket:
        p=decode_packet(wire)
        if p.sequence!=self.next_sequence:
            raise ValueError(f"sequence gap: expected {self.next_sequence}, got {p.sequence}")
        self.next_sequence=(self.next_sequence+1)&0xffffffff
        return p
