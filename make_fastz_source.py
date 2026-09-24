from pathlib import Path
p=Path("KEPHIR_FAST_Y.cpp")
s=p.read_text()
old='''    const int localChainDepth=k2_fast_adaptive_chain(d);'''
new='''    const int localChainDepth=1; // FAST-Z: speed ceiling probe, most-recent match only'''
if old not in s: raise SystemExit("CHAIN_DEPTH_ANCHOR_NOT_FOUND")
s=s.replace(old,new,1)
Path("KEPHIR_FAST_Z.cpp").write_text(s)
print("FAST_Z_SINGLE_CANDIDATE_READY")
