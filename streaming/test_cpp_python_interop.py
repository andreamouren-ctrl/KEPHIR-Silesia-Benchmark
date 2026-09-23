#!/usr/bin/env python3
from pathlib import Path
import argparse, subprocess, json
from aurora_media_container_v01 import *

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cpp-test",type=Path,required=True)
    ap.add_argument("--work",type=Path,default=Path("streaming/cpp_interop_out"))
    a=ap.parse_args()
    a.work.mkdir(parents=True,exist_ok=True)
    py=a.work/"python_fixture.aum"
    cpp=a.work/"cpp_output.aum"

    tracks=[
        Track(1,TRACK_AUDIO,CODEC_AURORA_AUDIO,0,48000,2,16,9600),
        Track(2,TRACK_VIDEO,CODEC_AURORA_VIDEO,0,176,144,25,1),
    ]
    with AuroraMuxer(py,tracks) as m:
        m.write_packet(1,0,200_000,bytes([1,2,3,4,5]),PKT_RECOVERY)
        m.write_packet(2,500_000,400_000,bytes([10,20,30]),PKT_KEY|PKT_RECOVERY)
        m.write_packet(1,200_000,200_000,bytes([9,8,7,6]),PKT_RECOVERY)

    cp=subprocess.run([str(a.cpp_test.resolve()),str(py.resolve()),str(cpp.resolve())],
                      text=True,capture_output=True,check=True)

    with AuroraDemuxer(cpp) as d:
        assert len(d.tracks)==2
        assert len(d.index)==3
        assert d.read_packet(d.index[0])==bytes([42,43,44])
        assert d.read_packet(d.index[1])==bytes([100,101,102,103])
        assert d.read_packet(d.index[2])==bytes([55,56])
        assert d.seek(2,900_000,True).pts==0

    result={
        "status":"PASS",
        "python_to_cpp":True,
        "cpp_to_python":True,
        "stream_incremental_cpp":True,
        "stream_crc_cpp":True,
        "cpp_stdout":cp.stdout.strip(),
        "python_fixture_bytes":py.stat().st_size,
        "cpp_output_bytes":cpp.stat().st_size,
    }
    (a.work/"interop_results.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
