from pathlib import Path
p=Path("KEPHIR_2_EXP33_DISTANCE_TOPOLOGY.cpp")
s=p.read_text()

insert='''\n#ifndef K2_LDT_MODE\n#define K2_LDT_MODE 0\n#endif\n'''
anchor='#ifndef K2_DIST_TOPO_MODE\n#define K2_DIST_TOPO_MODE 0\n#endif'
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

old='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb; array<SmallModel<2>,4> mt;'''
new='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb;
 SmallModel<9> ldt; SmallModel<2> ldtqnb; EncModel ldtq0,ldtq1;
 array<SmallModel<2>,4> mt;'''
assert old in s
s=s.replace(old,new,1)

old=''' if(ci<0){
 uint8_t nb=(x<256u)?1:((x<65536u)?2:3);
 dnb[dnbctx].enc(a,nb-1); dnbctx=nb-1; md0w[nb-1].enc(a,(uint8_t)x);
 if(nb>=2) md1w[nb-2].enc(a,(uint8_t)(x>>8));
 if(nb>=3) md2w.enc(a,(uint8_t)(x>>16));
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}'''
new=''' if(ci<0){
 uint8_t lc=0; uint32_t q=0;
 if(K2_LDT_MODE==1){
   if(x==15) lc=1; else if(x==16) lc=2; else if(x==17) lc=3;
   else if(x==255) lc=4; else if(x==256) lc=5; else if(x==257) lc=6;
 } else if(K2_LDT_MODE==2){
   if((x%256u)==0u && x/256u<=255u){lc=1;q=x/256u;}
   else if((x%16u)==0u && x/16u<=65535u){lc=2;q=x/16u;}
 } else if(K2_LDT_MODE==3){
   if(x==15) lc=1; else if(x==16) lc=2; else if(x==17) lc=3;
   else if(x==255) lc=4; else if(x==256) lc=5; else if(x==257) lc=6;
   else if((x%256u)==0u && x/256u<=255u){lc=7;q=x/256u;}
   else if((x%16u)==0u && x/16u<=65535u){lc=8;q=x/16u;}
 }
 if(K2_LDT_MODE) ldt.enc(a,lc);
 if(lc>=1 && lc<=6){
   // exact lattice anchors carry no payload
 } else if((K2_LDT_MODE==2 && (lc==1||lc==2)) || (K2_LDT_MODE==3 && (lc==7||lc==8))){
   bool two=q>255u; ldtqnb.enc(a,(uint8_t)two); ldtq0.enc(a,(uint8_t)q); if(two) ldtq1.enc(a,(uint8_t)(q>>8));
 } else {
   uint8_t nb=(x<256u)?1:((x<65536u)?2:3);
   dnb[dnbctx].enc(a,nb-1); dnbctx=nb-1; md0w[nb-1].enc(a,(uint8_t)x);
   if(nb>=2) md1w[nb-2].enc(a,(uint8_t)(x>>8));
   if(nb>=3) md2w.enc(a,(uint8_t)(x>>16));
 }
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}'''
assert old in s
s=s.replace(old,new,1)

old='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb; array<SmallModel<2>,4> mt;'''
new='''array<SmallModel<9>,2> dm; array<SmallModel<3>,3> dnb;
 SmallModel<9> ldt; SmallModel<2> ldtqnb; DecModel ldtq0,ldtq1;
 array<SmallModel<2>,4> mt;'''
assert old in s
s=s.replace(old,new,1)

old=''' else{
 uint8_t nb=(uint8_t)(decsmall(a,dnb[dnbctx])+1); dnbctx=nb-1; x=decsym(a,md0w[nb-1]);
 if(nb>=2) x|=(uint32_t)decsym(a,md1w[nb-2])<<8;
 if(nb>=3) x|=(uint32_t)decsym(a,md2w)<<16;
 if(x==0 || x>(1u<<22)) return {};
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}'''
new=''' else{
 uint8_t lc=K2_LDT_MODE?decsmall(a,ldt):0;
 if(K2_LDT_MODE==2 && (lc==1||lc==2)){
   uint8_t two=decsmall(a,ldtqnb); uint32_t q=decsym(a,ldtq0); if(two) q|=(uint32_t)decsym(a,ldtq1)<<8;
   x=(lc==1)?q*256u:q*16u;
 } else if((K2_LDT_MODE==1 || K2_LDT_MODE==3) && lc>=1 && lc<=6){
   static const uint32_t anchors[7]={0,15,16,17,255,256,257};
   x=anchors[lc];
 } else if(K2_LDT_MODE==3 && (lc==7||lc==8)){
   uint8_t two=decsmall(a,ldtqnb); uint32_t q=decsym(a,ldtq0); if(two) q|=(uint32_t)decsym(a,ldtq1)<<8;
   x=(lc==7)?q*256u:q*16u;
 } else {
   uint8_t nb=(uint8_t)(decsmall(a,dnb[dnbctx])+1); dnbctx=nb-1; x=decsym(a,md0w[nb-1]);
   if(nb>=2) x|=(uint32_t)decsym(a,md1w[nb-2])<<8;
   if(nb>=3) x|=(uint32_t)decsym(a,md2w)<<16;
 }
 if(x==0 || x>(1u<<22)) return {};
 for(int j=7;j>0;--j) cache[j]=cache[j-1]; cache[0]=x;
}'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP34_LDT.cpp").write_text(s)
print("EXP34_SOURCE_BYTES",len(s.encode()))
