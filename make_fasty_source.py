from pathlib import Path
p=Path("KEPHIR_FAST_V.cpp")
s=p.read_text()

old='''static vector<uint8_t> encode(const vector<uint8_t>&d,const vector<Tok>&ts){AE a;K2Predictor kp;EncModel ml,mraw,mll; array<EncModel,3> md0w; array<EncModel,2> md1w; EncModel md2w; array<EncModel,RES_CTX_N> mlctx; array<EncModel,16> mlt; array<uint32_t,RES_CTX_N> ctxn{}; array<uint32_t,16> tctxn{}; array<double,RES_CTX_N> gl,cl; array<double,16> tl; gl.fill(8.0); cl.fill(8.0); tl.fill(8.0);'''
new='''static vector<uint8_t> encode(const vector<uint8_t>&d,const vector<Tok>&ts){AE a;EncModel mraw; array<EncModel,3> md0w; array<EncModel,2> md1w; EncModel md2w;'''
if old not in s: raise SystemExit("ENC_DECL_NOT_FOUND")
s=s.replace(old,new,1)

old=''' LongModel mlng;size_t p=0;K2TemporalField tf;uint32_t cache[8]={0};'''
new=''' LongModel mlng;size_t p=0;uint32_t cache[8]={0};'''
if old not in s: raise SystemExit("ENC_TF_DECL_NOT_FOUND")
s=s.replace(old,new,1)

start=s.find('if(!t.dist){')
end=s.find('}else{uint8_t sh=',start)
if start<0 or end<0: raise SystemExit("ENC_LITERAL_RANGE_NOT_FOUND")
s=s[:start]+'if(!t.dist){ uint8_t x=d[p]; mraw.enc(a,x); ++p;'+s[end:]

old='''for(size_t q=(p+PRED_SAMPLE_MASK)&~(size_t)PRED_SAMPLE_MASK, e=p+(size_t)t.len; q<e; q+=(PRED_SAMPLE_MASK+1u)) kp.observe_sampled(d,q); p+=t.len;'''
if old not in s: raise SystemExit("ENC_MATCH_PRED_NOT_FOUND")
s=s.replace(old,'p+=t.len;',1)

old='''static vector<uint8_t> decode(const vector<uint8_t>&in,size_t n){AD a(in);K2Predictor kp;DecModel ml,mraw,mll; array<DecModel,3> md0w; array<DecModel,2> md1w; DecModel md2w; array<DecModel,RES_CTX_N> mlctx; array<DecModel,16> mlt; array<uint32_t,RES_CTX_N> ctxn{}; array<uint32_t,16> tctxn{}; array<double,RES_CTX_N> gl,cl; array<double,16> tl; gl.fill(8.0); cl.fill(8.0); tl.fill(8.0);'''
new='''static vector<uint8_t> decode(const vector<uint8_t>&in,size_t n){AD a(in);DecModel mraw; array<DecModel,3> md0w; array<DecModel,2> md1w; DecModel md2w;'''
if old not in s: raise SystemExit("DEC_DECL_NOT_FOUND")
s=s.replace(old,new,1)

old=''' LongModel mlng;K2TemporalField tf;uint32_t cache[8]={0};'''
new=''' LongModel mlng;uint32_t cache[8]={0};'''
if old not in s: raise SystemExit("DEC_TF_DECL_NOT_FOUND")
s=s.replace(old,new,1)

start=s.find('if(!ty){ size_t p=o.size();')
end=s.find('}else{uint8_t sh=',start)
if start<0 or end<0: raise SystemExit("DEC_LITERAL_RANGE_NOT_FOUND")
s=s[:start]+'if(!ty){ uint8_t x=decsym(a,mraw); o.push_back(x); '+s[end:]

old='''for(size_t q=(old+PRED_SAMPLE_MASK)&~(size_t)PRED_SAMPLE_MASK, e=old+(size_t)len;
     q<e; q+=(PRED_SAMPLE_MASK+1u)) kp.observe_sampled(o,q);'''
if old not in s: raise SystemExit("DEC_MATCH_PRED_NOT_FOUND")
s=s.replace(old,'/* FAST-Y: predictor state removed in raw-literal profile */',1)

Path("KEPHIR_FAST_Y.cpp").write_text(s)
print("FAST_Y_READY",len(s))
