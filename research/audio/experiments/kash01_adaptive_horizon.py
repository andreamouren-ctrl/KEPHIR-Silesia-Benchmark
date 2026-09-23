#!/usr/bin/env python3
"""
KASH-01 adaptive audio recovery horizon.
Candidate horizons: 1 s or 2 s. Maximum recovery horizon remains 2 s.
"""
import argparse, hashlib, json, time
from pathlib import Path
from aurora_media_container import AuroraMuxer,AuroraDemuxer,Track,TRACK_AUDIO,CODEC_AURORA_AUDIO,PKT_RECOVERY
from aurora_media_codec_bridge import encode_audio_packet,decode_audio_packet
RATE=48000; CH=2; BITS=16; TS=1_000_000; FB=CH*(BITS//8); META=64
OUT=Path("results/audio/kash01")
def sha(b): return hashlib.sha256(b).hexdigest()
def us(s): return s*TS//RATE
def enc(pcm,s,n,exe):
    t=time.perf_counter(); p=encode_audio_packet(pcm[s*FB:(s+n)*FB],exe,CH,RATE)
    return p,time.perf_counter()-t
def fixed(pcm,exe):
    total=len(pcm)//FB; step=2*RATE; e=[]; et=0.0
    for s in range(0,total,step):
        n=min(step,total-s); p,dt=enc(pcm,s,n,exe); et+=dt; e.append((s,n,p))
    return e,et
def adaptive(pcm,exe):
    total=len(pcm)//FB
    pos=sorted(set(list(range(0,total,RATE))+[total]))
    cache={}; et=0.0
    for s in pos[:-1]:
        for sec in (1,2):
            t=min(total,s+sec*RATE)
            if t<=s: continue
            p,dt=enc(pcm,s,t-s,exe); cache[(s,t)]=p; et+=dt
    dp={total:(0,[])}
    for s in reversed(pos[:-1]):
        best=None
        for sec in (1,2):
            t=min(total,s+sec*RATE)
            if t not in dp or (s,t) not in cache: continue
            p=cache[(s,t)]; cand=(len(p)+META+dp[t][0],[(s,t-s,p)]+dp[t][1])
            if best is None or cand[0]<best[0]: best=cand
        if best is None: raise RuntimeError("no KASH path")
        dp[s]=best
    return dp[0][1],et,dp[0][0]
def write_verify(name,entries,pcm,exe):
    path=OUT/f"{name}.aum"
    with AuroraMuxer(path,[Track(1,TRACK_AUDIO,CODEC_AURORA_AUDIO,0,RATE,CH,BITS,2*RATE)]) as m:
        for s,n,p in entries: m.write_packet(1,us(s),us(n),p,PKT_RECOVERY)
    dec=bytearray(); dt=0.0
    with AuroraDemuxer(path) as d:
        for _,p in d.packets(1):
            t=time.perf_counter(); dec.extend(decode_audio_packet(p,exe)); dt+=time.perf_counter()-t
    if sha(bytes(dec))!=sha(pcm): raise SystemExit("SHA FAIL")
    hs=[round(n/RATE,3) for _,n,_ in entries]
    return {"bytes":path.stat().st_size,"packets":len(entries),"horizons":hs,"decode_seconds":dt,"sha_ok":True}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--audio",type=Path,required=True); ap.add_argument("--kephir",type=Path,required=True)
    a=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True); pcm=a.audio.read_bytes()
    fe,fet=fixed(pcm,a.kephir); fr=write_verify("fixed_2s",fe,pcm,a.kephir); fr["encode_seconds"]=fet
    ae,aet,obj=adaptive(pcm,a.kephir); ar=write_verify("adaptive_1_2s",ae,pcm,a.kephir); ar["encode_seconds"]=aet; ar["objective"]=obj
    ar["count_1s"]=sum(h<=1.001 for h in ar["horizons"]); ar["count_2s"]=sum(h>1.001 for h in ar["horizons"])
    r={"experiment":"KASH-01 adaptive 1s/2s recovery horizon","fixed_2s":fr,"adaptive":ar,
       "delta_bytes":ar["bytes"]-fr["bytes"],"delta_percent":100*(ar["bytes"]-fr["bytes"])/fr["bytes"]}
    (OUT/"KASH01_RESULTS.json").write_text(json.dumps(r,indent=2)); print(json.dumps(r,indent=2))
if __name__=="__main__": main()
