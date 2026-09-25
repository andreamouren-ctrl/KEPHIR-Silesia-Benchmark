from pathlib import Path
import os

src=Path("KEPHIR_SPEED_SOURCE.cpp").read_text()
mode=os.environ.get("K2_FASTD_LITERAL_VARIANT","full")

def bypass_predictor(s):
    old=''' uint8_t pr=kp.predict(d,p), x=d[p], r=(uint8_t)(x-pr);'''
    new=''' uint8_t x=d[p]; uint8_t pr=0, r=x;'''
    if old not in s: raise SystemExit("ENC_LITERAL_PATTERN_NOT_FOUND")
    s=s.replace(old,new,1)
    old=''' uint8_t pr=kp.predict(o,p);'''
    new=''' uint8_t pr=0;'''
    if old not in s: raise SystemExit("DEC_LITERAL_PATTERN_NOT_FOUND")
    return s.replace(old,new,1)

def force_raw(s):
    n=s.count('bool rawMode=kp.use_raw(p);')
    if n<2: raise SystemExit(f"RAW_MODE_PATTERN_COUNT={n}")
    return s.replace('bool rawMode=kp.use_raw(p);','bool rawMode=true;',2)

if mode=="baseline":
    src=bypass_predictor(src)
    src=force_raw(src)
elif mode=="predictor_only":
    src=force_raw(src)
elif mode=="model_only":
    src=bypass_predictor(src)
elif mode=="full":
    pass
else:
    raise SystemExit("BAD_LITERAL_VARIANT")

Path("KEPHIR_SPEED_D_SOURCE.cpp").write_text(src)
print("FAST_D_LITERAL_VARIANT_OK",mode,len(src))
