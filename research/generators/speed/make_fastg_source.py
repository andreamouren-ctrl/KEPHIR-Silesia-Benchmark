from pathlib import Path
import re

p=Path("KEPHIR_SPEED_D_SOURCE.cpp")
s=p.read_text()

needle='static vector<Tok> parse(const vector<uint8_t>&d,double LIT,double MC,double maxDistPenalty){'
helper=r'''
static inline int k2_match_len64(const vector<uint8_t>& d,int a,int b,int l,int lim){
    while(l+8<=lim){
        uint64_t x,y;
        memcpy(&x,d.data()+a+l,8);
        memcpy(&y,d.data()+b+l,8);
        uint64_t z=x^y;
        if(z){
            l += (int)(__builtin_ctzll(z)>>3);
            return l;
        }
        l+=8;
    }
    while(l<lim && d[(size_t)a+l]==d[(size_t)b+l]) ++l;
    return l;
}
'''
if needle not in s:
    raise SystemExit("PARSE_ANCHOR_NOT_FOUND")
s=s.replace(needle,helper+"\n"+needle,1)

patterns=[
    (r'while\(l<lim && d\[q\+l\]==d\[p\+l\]\)\s*\+\+l;', 'l=k2_match_len64(d,(int)q,p,l,lim);'),
    (r'while\(l<lim && d\[q\+l\]==d\[p\+l\]\)\s*\+\+l', 'l=k2_match_len64(d,(int)q,p,l,lim)'),
]
total=0
for pat,repl in patterns:
    s,n=re.subn(pat,repl,s)
    total+=n

print("MATCH_LOOPS_PATCHED",total)
if total<1:
    raise SystemExit("NO_MATCH_LOOP_PATCHED")

Path("KEPHIR_FAST_G.cpp").write_text(s)
