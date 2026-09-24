from pathlib import Path
import os

src=Path("KEPHIR_SPEED_D_SOURCE.cpp")
s=src.read_text()
mode=int(os.environ.get("K2_MEDIA_EARLY_MODE","0"))

profiles={
    0: None,
    1: (5,64),
    2: (4,48),
    3: (3,32),
}
if mode not in profiles:
    raise SystemExit("BAD_MEDIA_EARLY_MODE")

cfg=profiles[mode]
if cfg is not None:
    depth_gate,length_gate=cfg
    old="                if(stop) break;"
    if s.count(old)!=1:
        raise SystemExit(f"EARLY_STOP_PATTERN_COUNT={s.count(old)}")
    new=(
        f"                if(depth>={depth_gate} && bestL>={length_gate}) stop=true;\n"
        "                if(stop) break;"
    )
    s=s.replace(old,new,1)

Path("KEPHIR_SPEED_MEDIA_SOURCE.cpp").write_text(s)
print("FAST_D_MEDIA_PATCH_OK",mode,cfg,len(s))
