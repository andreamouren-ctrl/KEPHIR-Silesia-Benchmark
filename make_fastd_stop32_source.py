from pathlib import Path
import argparse
ap=argparse.ArgumentParser()
ap.add_argument("mode",choices=["baseline","stop32"])
ap.add_argument("--output",required=True)
args=ap.parse_args()
s=Path("KEPHIR_SPEED_D_SOURCE.cpp").read_text()
old='''(depth>=31 && bestL>=32)'''
if s.count(old)<1: raise SystemExit("STOP32_PATTERN_NOT_FOUND")
if args.mode=="stop32":
    s=s.replace(old,'''(depth>=15 && bestL>=32)''')
Path(args.output).write_text(s)
print("FAST_D_STOP32_OK",args.mode,len(s))
