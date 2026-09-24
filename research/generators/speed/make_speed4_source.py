from pathlib import Path
import os
s=Path("KEPHIR_2_EXP39_FUSED2.cpp").read_text()
mode=int(os.environ["FAST_LITERAL_MODE"])

for old,new in [
 ("#define CHAIN_DEPTH 42","#define CHAIN_DEPTH 4"),
 ("#define LAZY_DEPTH 19","#define LAZY_DEPTH 2"),
 ("#define PRED_SAMPLE_MASK 31u","#define PRED_SAMPLE_MASK 255u")]:
    if old not in s: raise SystemExit("PATCH_FAIL "+old)
    s=s.replace(old,new,1)

if mode==1:
    a="uint8_t pr=kp.predict(d,p); uint8_t x=d[p]; uint8_t r=(uint8_t)(x-pr);"
    b="uint8_t pr=p?d[p-1]:0; uint8_t x=d[p]; uint8_t r=(uint8_t)(x-pr);"
    if a not in s: raise SystemExit("FAST_F_ENC_PRED_FAIL")
    s=s.replace(a,b,1)
    a="uint8_t pr=kp.predict(o,p); uint8_t cx="
    b="uint8_t pr=p?o[p-1]:0; uint8_t cx="
    if a not in s: raise SystemExit("FAST_F_DEC_PRED_FAIL")
    s=s.replace(a,b,1)

elif mode in (2,3):
    enc_start=s.find("if(!t.dist){")
    enc_end=s.find("}else{uint8_t sh=",enc_start)
    if enc_start<0 or enc_end<0: raise SystemExit("ENC_LITERAL_PATCH_FAIL")
    enc_end += len("}else{uint8_t sh=")

    dec_start=s.find("if(!ty){ size_t p=o.size();")
    dec_end=s.find("}else{uint8_t sh=",dec_start)
    if dec_start<0 or dec_end<0: raise SystemExit("DEC_LITERAL_PATCH_FAIL")
    dec_end += len("}else{uint8_t sh=")

    if mode==2:
        epr="p?d[p-1]:0"
        dpr="p?o[p-1]:0"
    else:
        epr="p>=16?(uint8_t)(((unsigned)d[p-1]+(unsigned)d[p-16]+1u)>>1):(p?d[p-1]:0)"
        dpr="p>=16?(uint8_t)(((unsigned)o[p-1]+(unsigned)o[p-16]+1u)>>1):(p?o[p-1]:0)"

    enc_repl=f'''if(!t.dist){{
 uint8_t x=d[p]; uint8_t pr={epr}; uint8_t r=(uint8_t)(x-pr);
 ml.enc(a,r); ++p;
 }}else{{uint8_t sh='''
    dec_repl=f'''if(!ty){{ size_t p=o.size();
 uint8_t pr={dpr}; uint8_t r=decsym(a,ml); uint8_t x=(uint8_t)(r+pr);
 o.push_back(x);
 }}else{{uint8_t sh='''

    s=s[:enc_start]+enc_repl+s[enc_end:]
    # recompute decoder anchors after encoder replacement changed offsets
    dec_start=s.find("if(!ty){ size_t p=o.size();")
    dec_end=s.find("}else{uint8_t sh=",dec_start)
    if dec_start<0 or dec_end<0: raise SystemExit("DEC_LITERAL_PATCH_FAIL_2")
    dec_end += len("}else{uint8_t sh=")
    s=s[:dec_start]+dec_repl+s[dec_end:]
else:
    raise SystemExit("BAD_MODE")

Path("KEPHIR_SPEED4.cpp").write_text(s)
print("FAST_LITERAL_MODE",mode,"bytes",len(s))
