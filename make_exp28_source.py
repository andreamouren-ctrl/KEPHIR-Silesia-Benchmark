from pathlib import Path
p=Path("KEPHIR_2_EXP27_LAZY_ADAPT.cpp")
s=p.read_text()

# Insert compile-time mode.
s=s.replace('#ifndef K2_LAZY_MODE\n#define K2_LAZY_MODE 0\n#endif',
'''#ifndef K2_LAZY_MODE
#define K2_LAZY_MODE 1
#endif
#ifndef K2_TOKEN_COUPLE_MODE
#define K2_TOKEN_COUPLE_MODE 0
#endif''',1)

# Encoder declarations: add conditioned models and token state.
old='array<SmallModel<2>,2> ms; SmallModel<4> msl; EncModel mlehi,mlelow; LongModel mlng;size_t p=0;K2TemporalField tf;uint32_t cache[8]={0}; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0;'
new='''array<SmallModel<2>,2> ms; SmallModel<4> msl; EncModel mlehi,mlelow; LongModel mlng;
array<SmallModel<4>,4> msl_c; array<LongModel,4> mlng_c;
array<array<EncModel,3>,4> md0_c; array<array<EncModel,2>,4> md1_c; array<EncModel,4> md2_c;
array<SmallModel<9>,4> dm_c; array<SmallModel<3>,4> dnb_c;
size_t p=0;K2TemporalField tf;uint32_t cache[8]={0}; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0; uint8_t prevMatchClass=0;'''
assert old in s
s=s.replace(old,new,1)

# Replace encoder match branch as one exact block.
old='''}else{uint8_t sh=(t.len<=7?0:1); ms[msctx].enc(a,sh); msctx=sh; if(t.len<=7) msl.enc(a,(uint8_t)(t.len-4)); else if(t.len<=255) mlng.enc(a,(uint8_t)(t.len-8)); else { mlng.enc(a,248u); uint32_t ex=(uint32_t)(t.len-256); mlehi.enc(a,(uint8_t)(ex>>8)); mlelow.enc(a,(uint8_t)ex); } uint32_t x=t.dist;int ci=-1;for(int j=0;j<8;j++) if(cache[j]==x){ci=j;break;}uint8_t dmode=(uint8_t)(ci<0?8:ci); dm[dmctx].enc(a,dmode); dmctx=(dmode==8);
 if(ci<0){
 uint8_t nb=(x<256u)?1:((x<65536u)?2:3);
 dnb[dnbctx].enc(a,nb-1); dnbctx=nb-1; md0w[nb-1].enc(a,(uint8_t)x);
 if(nb>=2) md1w[nb-2].enc(a,(uint8_t)(x>>8));
 if(nb>=3) md2w.enc(a,(uint8_t)(x>>16));
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}
 else if(ci>0){for(int j=ci;j>0;j--)cache[j]=cache[j-1];cache[0]=x;}
for(size_t q=(p+PRED_SAMPLE_MASK)&~(size_t)PRED_SAMPLE_MASK, e=p+(size_t)t.len; q<e; q+=(PRED_SAMPLE_MASK+1u)) kp.observe_sampled(d,q); p+=t.len;}}return a.finish();}'''
new='''}else{
 uint32_t x=t.dist; int ci=-1; for(int j=0;j<8;j++) if(cache[j]==x){ci=j;break;}
 uint8_t dmode=(uint8_t)(ci<0?8:ci);
 uint8_t distClass=(uint8_t)(ci>=0?0:(x<256u?1:(x<65536u?2:3)));
 uint8_t sh=(t.len<=7?0:1);
 uint8_t lenClass=(uint8_t)(t.len<=7?0:(t.len<=31?1:(t.len<=255?2:3)));

 ms[msctx].enc(a,sh); msctx=sh;
 uint8_t lctx=(K2_TOKEN_COUPLE_MODE==2 || K2_TOKEN_COUPLE_MODE==3)?distClass:prevMatchClass;
 if(t.len<=7){
   if(K2_TOKEN_COUPLE_MODE==2 || K2_TOKEN_COUPLE_MODE==3) msl_c[lctx].enc(a,(uint8_t)(t.len-4));
   else msl.enc(a,(uint8_t)(t.len-4));
 } else if(t.len<=255){
   if(K2_TOKEN_COUPLE_MODE==2 || K2_TOKEN_COUPLE_MODE==3) mlng_c[lctx].enc(a,(uint8_t)(t.len-8));
   else mlng.enc(a,(uint8_t)(t.len-8));
 } else {
   if(K2_TOKEN_COUPLE_MODE==2 || K2_TOKEN_COUPLE_MODE==3) mlng_c[lctx].enc(a,248u);
   else mlng.enc(a,248u);
   uint32_t ex=(uint32_t)(t.len-256); mlehi.enc(a,(uint8_t)(ex>>8)); mlelow.enc(a,(uint8_t)ex);
 }

 if(K2_TOKEN_COUPLE_MODE==1 || K2_TOKEN_COUPLE_MODE==3) dm_c[lenClass].enc(a,dmode);
 else dm[dmctx].enc(a,dmode);
 dmctx=(dmode==8);

 if(ci<0){
   uint8_t nb=(x<256u)?1:((x<65536u)?2:3);
   if(K2_TOKEN_COUPLE_MODE==1 || K2_TOKEN_COUPLE_MODE==3){
     dnb_c[lenClass].enc(a,nb-1);
     md0_c[lenClass][nb-1].enc(a,(uint8_t)x);
     if(nb>=2) md1_c[lenClass][nb-2].enc(a,(uint8_t)(x>>8));
     if(nb>=3) md2_c[lenClass].enc(a,(uint8_t)(x>>16));
   }else{
     dnb[dnbctx].enc(a,nb-1); dnbctx=nb-1; md0w[nb-1].enc(a,(uint8_t)x);
     if(nb>=2) md1w[nb-2].enc(a,(uint8_t)(x>>8));
     if(nb>=3) md2w.enc(a,(uint8_t)(x>>16));
   }
   dnbctx=nb-1;
   for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
 } else if(ci>0){for(int j=ci;j>0;j--)cache[j]=cache[j-1];cache[0]=x;}

 prevMatchClass=lenClass;
 for(size_t q=(p+PRED_SAMPLE_MASK)&~(size_t)PRED_SAMPLE_MASK, e=p+(size_t)t.len; q<e; q+=(PRED_SAMPLE_MASK+1u)) kp.observe_sampled(d,q); p+=t.len;
}}return a.finish();}'''
assert old in s
s=s.replace(old,new,1)

# Decoder declarations.
old='array<SmallModel<2>,2> ms; SmallModel<4> msl; DecModel mlehi,mlelow; LongModel mlng;K2TemporalField tf;uint32_t cache[8]={0}; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0;'
new='''array<SmallModel<2>,2> ms; SmallModel<4> msl; DecModel mlehi,mlelow; LongModel mlng;
array<SmallModel<4>,4> msl_c; array<LongModel,4> mlng_c;
array<array<DecModel,3>,4> md0_c; array<array<DecModel,2>,4> md1_c; array<DecModel,4> md2_c;
array<SmallModel<9>,4> dm_c; array<SmallModel<3>,4> dnb_c;
K2TemporalField tf;uint32_t cache[8]={0}; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0; uint8_t prevMatchClass=0;'''
assert old in s
s=s.replace(old,new,1)

# Replace decoder match beginning + distance block.
old='''}else{uint8_t sh=decsmall(a,ms[msctx]); msctx=sh; int len; if(!sh) len=(int)decsmall(a,msl)+4; else { uint8_t lv=declong(a,mlng); if(lv<248u) len=(int)lv+8; else { uint32_t hi=decsym(a,mlehi), lo=decsym(a,mlelow); len=256+(int)((hi<<8)|lo); } } uint8_t mode=decsmall(a,dm[dmctx]); dmctx=(mode==8); uint32_t x=0;
 if(mode<8){x=cache[mode]; for(int j=mode;j>0;j--)cache[j]=cache[j-1]; cache[0]=x;}
 else{
 uint8_t nb=(uint8_t)(decsmall(a,dnb[dnbctx])+1); dnbctx=nb-1; x=decsym(a,md0w[nb-1]);
 if(nb>=2) x|=(uint32_t)decsym(a,md1w[nb-2])<<8;
 if(nb>=3) x|=(uint32_t)decsym(a,md2w)<<16;
 if(x==0 || x>(1u<<22)) return {};
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}if(x==0||x>o.size()||o.size()+len>n) return {};'''
new='''}else{
 uint8_t sh=decsmall(a,ms[msctx]); msctx=sh; int len;
 uint8_t tentativeDistClass=prevMatchClass;
 uint8_t lctx=(K2_TOKEN_COUPLE_MODE==2 || K2_TOKEN_COUPLE_MODE==3)?tentativeDistClass:prevMatchClass;

 // For distance-conditioned length we cannot know the current distance class before decoding it,
 // so mode 2/3 conditions length on the previous match distance class. This is causal and symmetric.
 if(!sh){
   len=(int)((K2_TOKEN_COUPLE_MODE==2 || K2_TOKEN_COUPLE_MODE==3)?decsmall(a,msl_c[lctx]):decsmall(a,msl))+4;
 } else {
   uint8_t lv=(K2_TOKEN_COUPLE_MODE==2 || K2_TOKEN_COUPLE_MODE==3)?declong(a,mlng_c[lctx]):declong(a,mlng);
   if(lv<248u) len=(int)lv+8; else { uint32_t hi=decsym(a,mlehi), lo=decsym(a,mlelow); len=256+(int)((hi<<8)|lo); }
 }
 uint8_t lenClass=(uint8_t)(len<=7?0:(len<=31?1:(len<=255?2:3)));
 uint8_t mode=(K2_TOKEN_COUPLE_MODE==1 || K2_TOKEN_COUPLE_MODE==3)?decsmall(a,dm_c[lenClass]):decsmall(a,dm[dmctx]);
 dmctx=(mode==8); uint32_t x=0; uint8_t distClass=0;
 if(mode<8){
   x=cache[mode]; distClass=0; for(int j=mode;j>0;j--)cache[j]=cache[j-1]; cache[0]=x;
 } else {
   uint8_t nb;
   if(K2_TOKEN_COUPLE_MODE==1 || K2_TOKEN_COUPLE_MODE==3){
     nb=(uint8_t)(decsmall(a,dnb_c[lenClass])+1);
     x=decsym(a,md0_c[lenClass][nb-1]);
     if(nb>=2) x|=(uint32_t)decsym(a,md1_c[lenClass][nb-2])<<8;
     if(nb>=3) x|=(uint32_t)decsym(a,md2_c[lenClass])<<16;
   }else{
     nb=(uint8_t)(decsmall(a,dnb[dnbctx])+1); x=decsym(a,md0w[nb-1]);
     if(nb>=2) x|=(uint32_t)decsym(a,md1w[nb-2])<<8;
     if(nb>=3) x|=(uint32_t)decsym(a,md2w)<<16;
   }
   dnbctx=nb-1; distClass=nb;
   if(x==0 || x>(1u<<22)) return {};
   for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
 }
 prevMatchClass=distClass?distClass:lenClass;
 if(x==0||x>o.size()||o.size()+len>n) return {};'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP28_TOKEN_COUPLE.cpp").write_text(s)
print("EXP28_SOURCE_BYTES",len(s.encode()))
