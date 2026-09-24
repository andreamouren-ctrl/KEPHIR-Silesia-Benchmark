from pathlib import Path
p=Path("KEPHIR_SPEED_SOURCE.cpp")
s=p.read_text()

# FAST-D diagnostic: bypass expensive predictive literal modeling symmetrically.
# Encoder literal branch.
old=''' uint8_t pr=kp.predict(d,p), x=d[p], r=(uint8_t)(x-pr);'''
new=''' uint8_t x=d[p]; uint8_t pr=0, r=x;'''
if old not in s:
    raise SystemExit("ENC_LITERAL_PATTERN_NOT_FOUND")
s=s.replace(old,new,1)

# Decoder literal branch.
old=''' uint8_t pr=kp.predict(o,p);'''
new=''' uint8_t pr=0;'''
if old not in s:
    raise SystemExit("DEC_LITERAL_PATTERN_NOT_FOUND")
s=s.replace(old,new,1)

# Force raw literal model in both encoder and decoder.
s=s.replace('bool rawMode=kp.use_raw(p);','bool rawMode=true;',2)

Path("KEPHIR_SPEED_D_SOURCE.cpp").write_text(s)
print("FAST_D_PATCH_OK",len(s))
