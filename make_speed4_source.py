from pathlib import Path
import os,re
s=Path("KEPHIR_2_EXP39_FUSED2.cpp").read_text()
mode=int(os.environ["FAST_LITERAL_MODE"])

for old,new in [
 ("#define CHAIN_DEPTH 42","#define CHAIN_DEPTH 4"),
 ("#define LAZY_DEPTH 19","#define LAZY_DEPTH 2"),
 ("#define PRED_SAMPLE_MASK 31u","#define PRED_SAMPLE_MASK 255u")]:
    if old not in s: raise SystemExit("PATCH_FAIL "+old)
    s=s.replace(old,new,1)

if mode==1:
    # Keep current entropy experts, replace only expensive predictor evaluation.
    s=s.replace("uint8_t pr=kp.predict(d,p); uint8_t x=d[p]; uint8_t r=(uint8_t)(x-pr);",
                "uint8_t pr=p?d[p-1]:0; uint8_t x=d[p]; uint8_t r=(uint8_t)(x-pr);",1)
    s=s.replace("uint8_t pr=kp.predict(o,p); uint8_t cx=",
                "uint8_t pr=p?o[p-1]:0; uint8_t cx=",1)
elif mode in (2,3):
    enc_pat=r'if\(!t\.dist\)\{\n.*?\n \}else\{uint8_t sh='
    dec_pat=r'if\(!ty\)\{ size_t p=o\.size\(\);\n.*?\n o\.push_back\(x\);.*?\}else\{uint8_t sh='
    if mode==2:
        epr='p?d[p-1]:0'
        dpr='p?o[p-1]:0'
    else:
        epr='p>=16?(uint8_t)(((unsigned)d[p-1]+(unsigned)d[p-16]+1u)>>1):(p?d[p-1]:0)'
        dpr='p>=16?(uint8_t)(((unsigned)o[p-1]+(unsigned)o[p-16]+1u)>>1):(p?o[p-1]:0)'
    enc_repl=f'''if(!t.dist){{
 uint8_t x=d[p]; uint8_t pr={epr}; uint8_t r=(uint8_t)(x-pr);
 ml.enc(a,r); ++p;
 }}else{{uint8_t sh='''
    dec_repl=f'''if(!ty){{ size_t p=o.size();
 uint8_t pr={dpr}; uint8_t r=decsym(a,ml); uint8_t x=(uint8_t)(r+pr);
 o.push_back(x);
 }}else{{uint8_t sh='''
    s,n=re.subn(enc_pat,enc_repl,s,count=1,flags=re.S)
    if n!=1: raise SystemExit("ENC_LITERAL_PATCH_FAIL")
    s,n=re.subn(dec_pat,dec_repl,s,count=1,flags=re.S)
    if n!=1: raise SystemExit("DEC_LITERAL_PATCH_FAIL")
else:
    raise SystemExit("BAD_MODE")

Path("KEPHIR_SPEED4.cpp").write_text(s)
print("FAST_LITERAL_MODE",mode,"bytes",len(s))
