#!/usr/bin/env python3
"""
AURORA Media Container v0.1

Original project implementation for AURORA Media research.
No external muxer/demuxer dependency.

Design goals:
- deterministic binary format
- audio/video tracks
- packet timestamps + durations
- independent recovery/key flags
- per-packet CRC32
- final random-access index
- complete-file footer locating the index
- simple forward-compatible versioning

This is a research container implementation, not a patentability claim.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import io, struct, zlib

MAGIC=b"AUM1"
VERSION=1
INDEX_MAGIC=b"AUI1"
FOOTER_MAGIC=b"AUF1"

FILE_HDR=struct.Struct("<4sBBHII")      # magic,ver,flags,track_count,timescale,reserved
TRACK_HDR=struct.Struct("<BBBBIIII")     # id,type,codec,flags,p1,p2,p3,p4
PACKET_HDR=struct.Struct("<BBHQQIII")    # track,flags,reserved,pts,duration,size,crc,reserved2
INDEX_HDR=struct.Struct("<4sI")
INDEX_ENT=struct.Struct("<BBHQQQI")      # track,flags,reserved,pts,duration,file_offset,size
FOOTER=struct.Struct("<4sQQI")           # magic,index_offset,index_size,index_crc

TRACK_AUDIO=1
TRACK_VIDEO=2

CODEC_AURORA_AUDIO=1
CODEC_AURORA_VIDEO=2

PKT_KEY=1
PKT_RECOVERY=2

@dataclass(frozen=True)
class Track:
    track_id:int
    track_type:int
    codec:int
    flags:int=0
    p1:int=0
    p2:int=0
    p3:int=0
    p4:int=0

@dataclass(frozen=True)
class PacketInfo:
    track_id:int
    flags:int
    pts:int
    duration:int
    file_offset:int
    size:int

class AuroraMuxer:
    def __init__(self,path:Path,tracks:list[Track],timescale:int=1_000_000):
        if not tracks or len(tracks)>255:
            raise ValueError("invalid tracks")
        ids=[t.track_id for t in tracks]
        if len(ids)!=len(set(ids)) or any(i<0 or i>255 for i in ids):
            raise ValueError("invalid track ids")
        self.path=Path(path)
        self.f=self.path.open("wb")
        self.tracks={t.track_id:t for t in tracks}
        self.timescale=timescale
        self.index=[]
        self.closed=False
        self.f.write(FILE_HDR.pack(MAGIC,VERSION,0,len(tracks),timescale,0))
        for t in tracks:
            self.f.write(TRACK_HDR.pack(t.track_id,t.track_type,t.codec,t.flags,t.p1,t.p2,t.p3,t.p4))

    def write_packet(self,track_id:int,pts:int,duration:int,payload:bytes,flags:int=0):
        if self.closed: raise ValueError("muxer closed")
        if track_id not in self.tracks: raise ValueError("unknown track")
        if pts<0 or duration<0: raise ValueError("negative time")
        crc=zlib.crc32(payload)&0xffffffff
        off=self.f.tell()
        self.f.write(PACKET_HDR.pack(track_id,flags,0,pts,duration,len(payload),crc,0))
        self.f.write(payload)
        self.index.append(PacketInfo(track_id,flags,pts,duration,off,len(payload)))

    def close(self):
        if self.closed:return
        idx_off=self.f.tell()
        b=io.BytesIO()
        b.write(INDEX_HDR.pack(INDEX_MAGIC,len(self.index)))
        for e in self.index:
            b.write(INDEX_ENT.pack(e.track_id,e.flags,0,e.pts,e.duration,e.file_offset,e.size))
        ib=b.getvalue()
        self.f.write(ib)
        self.f.write(FOOTER.pack(FOOTER_MAGIC,idx_off,len(ib),zlib.crc32(ib)&0xffffffff))
        self.f.close()
        self.closed=True

    def __enter__(self): return self
    def __exit__(self,*exc): self.close()

class AuroraDemuxer:
    def __init__(self,path:Path):
        self.path=Path(path)
        self.f=self.path.open("rb")
        raw=self.f.read(FILE_HDR.size)
        if len(raw)!=FILE_HDR.size: raise ValueError("truncated file")
        magic,ver,flags,ntracks,self.timescale,_=FILE_HDR.unpack(raw)
        if magic!=MAGIC or ver!=VERSION: raise ValueError("unsupported AURORA Media file")
        self.tracks={}
        for _ in range(ntracks):
            r=self.f.read(TRACK_HDR.size)
            if len(r)!=TRACK_HDR.size: raise ValueError("truncated track table")
            vals=TRACK_HDR.unpack(r)
            t=Track(*vals)
            self.tracks[t.track_id]=t
        self.data_start=self.f.tell()
        self.index=self._read_index()

    def _read_index(self):
        self.f.seek(0,2); end=self.f.tell()
        if end<FOOTER.size: raise ValueError("missing footer")
        self.f.seek(end-FOOTER.size)
        m,off,sz,crc=FOOTER.unpack(self.f.read(FOOTER.size))
        if m!=FOOTER_MAGIC or off+sz>end-FOOTER.size: raise ValueError("bad footer")
        self.f.seek(off); ib=self.f.read(sz)
        if zlib.crc32(ib)&0xffffffff!=crc: raise ValueError("index CRC")
        bio=io.BytesIO(ib)
        m,n=INDEX_HDR.unpack(bio.read(INDEX_HDR.size))
        if m!=INDEX_MAGIC: raise ValueError("bad index")
        out=[]
        for _ in range(n):
            vals=INDEX_ENT.unpack(bio.read(INDEX_ENT.size))
            out.append(PacketInfo(vals[0],vals[1],vals[3],vals[4],vals[5],vals[6]))
        if bio.tell()!=len(ib): raise ValueError("index trailing data")
        return out

    def read_packet(self,e:PacketInfo)->bytes:
        self.f.seek(e.file_offset)
        r=self.f.read(PACKET_HDR.size)
        if len(r)!=PACKET_HDR.size: raise ValueError("truncated packet")
        tid,flags,_,pts,dur,sz,crc,_=PACKET_HDR.unpack(r)
        if (tid,flags,pts,dur,sz)!=(e.track_id,e.flags,e.pts,e.duration,e.size):
            raise ValueError("packet/index mismatch")
        p=self.f.read(sz)
        if len(p)!=sz or (zlib.crc32(p)&0xffffffff)!=crc:
            raise ValueError("packet CRC")
        return p

    def packets(self,track_id:int|None=None):
        for e in self.index:
            if track_id is None or e.track_id==track_id:
                yield e,self.read_packet(e)

    def seek(self,track_id:int,pts:int,recovery_only:bool=True):
        candidates=[e for e in self.index if e.track_id==track_id and e.pts<=pts and
                    (not recovery_only or (e.flags&(PKT_KEY|PKT_RECOVERY)))]
        return max(candidates,key=lambda e:e.pts) if candidates else None

    def close(self): self.f.close()
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
