from pathlib import Path
p=Path("KEPHIR_2_EXP33_DISTANCE_TOPOLOGY.cpp")
s=p.read_text()

anchor='#ifndef K2_DIST_TOPO_MODE\n#define K2_DIST_TOPO_MODE 0\n#endif'
insert='''\n#ifndef K2_DRS_MODE\n#define K2_DRS_MODE 0\n#endif\n'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

old='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb; array<SmallModel<2>,4> mt;'''
new='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb;
 SmallModel<2> drgate; SmallModel<3> drnb; EncModel dr0,dr1,dr2;
 array<SmallModel<2>,4> mt;'''
assert old in s
s=s.replace(old,new,1)

old='''LongModel mlng;size_t p=0;K2TemporalField tf;uint32_t cache[8]={0}; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0;'''
new='''LongModel mlng;size_t p=0;K2TemporalField tf;uint32_t cache[8]={0}; uint32_t prevDist=0; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0;'''
assert old in s
s=s.replace(old,new,1)

old=''' if(ci<0){
 uint8_t nb=(x<256u)?1:((x<65536u)?2:3);
 dnb[dnbctx].enc(a,nb-1); dnbctx=nb-1; md0w[nb-1].enc(a,(uint8_t)x);
 if(nb>=2) md1w[nb-2].enc(a,(uint8_t)(x>>8));
 if(nb>=3) md2w.enc(a,(uint8_t)(x>>16));
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}
 else if(ci>0){for(int j=ci;j>0;j--)cache[j]=cache[j-1];cache[0]=x;}
for(size_t q='''

new=''' if(ci<0){
 int64_t delta=(int64_t)x-(int64_t)prevDist;
 uint32_t lim=K2_DRS_MODE==1?255u:(K2_DRS_MODE==2?4095u:(K2_DRS_MODE==3?65535u:0u));
 bool useDelta=K2_DRS_MODE && prevDist>0 && delta>=-(int64_t)lim && delta<=(int64_t)lim;
 if(K2_DRS_MODE) drgate.enc(a,(uint8_t)useDelta);
 if(useDelta){
   uint32_t zz=(uint32_t)(((uint64_t)(delta<0?-delta:delta)<<1) - (delta<0?1u:0u));
   uint8_t nb=(zz<256u)?1:((zz<65536u)?2:3);
   drnb.enc(a,nb-1); dr0.enc(a,(uint8_t)zz);
   if(nb>=2) dr1.enc(a,(uint8_t)(zz>>8));
   if(nb>=3) dr2.enc(a,(uint8_t)(zz>>16));
 }else{
   uint8_t nb=(x<256u)?1:((x<65536u)?2:3);
   dnb[dnbctx].enc(a,nb-1); dnbctx=nb-1; md0w[nb-1].enc(a,(uint8_t)x);
   if(nb>=2) md1w[nb-2].enc(a,(uint8_t)(x>>8));
   if(nb>=3) md2w.enc(a,(uint8_t)(x>>16));
 }
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}
 else if(ci>0){for(int j=ci;j>0;j--)cache[j]=cache[j-1];cache[0]=x;}
prevDist=x;
for(size_t q='''

assert old in s
s=s.replace(old,new,1)

old='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb; array<SmallModel<2>,4> mt;'''
new='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb;
 SmallModel<2> drgate; SmallModel<3> drnb; DecModel dr0,dr1,dr2;
 array<SmallModel<2>,4> mt;'''
assert old in s
s=s.replace(old,new,1)

old='''LongModel mlng;K2TemporalField tf;uint32_t cache[8]={0}; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0;'''
new='''LongModel mlng;K2TemporalField tf;uint32_t cache[8]={0}; uint32_t prevDist=0; uint8_t mtctx=0, msctx=0, dmctx=0, dnbctx=0;'''
assert old in s
s=s.replace(old,new,1)

old=''' else{
 uint8_t nb=(uint8_t)(decsmall(a,dnb[dnbctx])+1); dnbctx=nb-1; x=decsym(a,md0w[nb-1]);
 if(nb>=2) x|=(uint32_t)decsym(a,md1w[nb-2])<<8;
 if(nb>=3) x|=(uint32_t)decsym(a,md2w)<<16;
 if(x==0 || x>(1u<<22)) return {};
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}if(x==0||x>o.size()||o.size()+len>n) return {};'''

new=''' else{
 bool useDelta=K2_DRS_MODE?decsmall(a,drgate):false;
 if(useDelta){
   uint8_t nb=(uint8_t)(decsmall(a,drnb)+1); uint32_t zz=decsym(a,dr0);
   if(nb>=2) zz|=(uint32_t)decsym(a,dr1)<<8;
   if(nb>=3) zz|=(uint32_t)decsym(a,dr2)<<16;
   int64_t delta=(zz&1u)?-(int64_t)((zz+1u)>>1):(int64_t)(zz>>1);
   int64_t nx=(int64_t)prevDist+delta;
   if(nx<=0 || nx>(1u<<22)) return {};
   x=(uint32_t)nx;
 }else{
   uint8_t nb=(uint8_t)(decsmall(a,dnb[dnbctx])+1); dnbctx=nb-1; x=decsym(a,md0w[nb-1]);
   if(nb>=2) x|=(uint32_t)decsym(a,md1w[nb-2])<<8;
   if(nb>=3) x|=(uint32_t)decsym(a,md2w)<<16;
 }
 if(x==0 || x>(1u<<22)) return {};
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}
prevDist=x;
if(x==0||x>o.size()||o.size()+len>n) return {};'''

assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP35_DRS.cpp").write_text(s)
print("EXP35_SOURCE_BYTES",len(s.encode()))
