from pathlib import Path
p=Path("KEPHIR_2_EXP33_DISTANCE_TOPOLOGY.cpp")
s=p.read_text()

anchor='#ifndef K2_DIST_TOPO_MODE\n#define K2_DIST_TOPO_MODE 0\n#endif'
insert='''\n#ifndef K2_SPATIAL_MODE\n#define K2_SPATIAL_MODE 0\n#endif\n'''
assert anchor in s
s=s.replace(anchor,anchor+insert,1)

old='''array<EncModel,RES_CTX_N> mlctx; array<EncModel,16> mlt; array<uint32_t,RES_CTX_N> ctxn{}; array<uint32_t,16> tctxn{}; array<double,RES_CTX_N> gl,cl; array<double,16> tl; gl.fill(8.0); cl.fill(8.0); tl.fill(8.0);'''
new='''array<EncModel,RES_CTX_N> mlctx; array<EncModel,16> mlt; array<EncModel,16> mls;
 array<uint32_t,RES_CTX_N> ctxn{}; array<uint32_t,16> tctxn{}; array<uint32_t,16> sctxn{};
 array<double,RES_CTX_N> gl,cl; array<double,16> tl,sl; gl.fill(8.0); cl.fill(8.0); tl.fill(8.0); sl.fill(8.0);'''
assert old in s
s=s.replace(old,new,1)

old=''' uint8_t cx=p?(uint8_t)(((pr>>6)<<1) | (pr>=d[p-1])):(uint8_t)((pr>>6)<<1); uint8_t tcx=(uint8_t)(cx | (tf.bin2()<<3));
 double cg=K2LOG2(ml.total)-K2LOG2(ml.f[r]), cc=K2LOG2(mlctx[cx].total)-K2LOG2(mlctx[cx].f[r]); bool tactive=tf.confident(); double ct=tactive?(K2LOG2(mlt[tcx].total)-K2LOG2(mlt[tcx].f[r])):8.0;
 bool rawMode=kp.use_raw(p);
 if(rawMode){ mraw.enc(a,x); }
 else { int sel=0; double best=gl[cx]; if(ctxn[cx]>=CTX_WARM && cl[cx]+CTX_MARGIN<best){sel=1;best=cl[cx];} if(tactive && tctxn[tcx]>=CTX_WARM && tl[tcx]+0.03<best){sel=2;best=tl[tcx];}
   if(sel==0){ml.enc(a,r);mlctx[cx].learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);} else if(sel==1){mlctx[cx].enc(a,r);ml.learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);} else {mlt[tcx].enc(a,r);ml.learn_lazy(r);mlctx[cx].learn_lazy(r);}
   if((ctxn[cx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;gl[cx]=(1.0-CA)*gl[cx]+CA*cg;cl[cx]=(1.0-CA)*cl[cx]+CA*cc;}
   if(tactive){if((tctxn[tcx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;tl[tcx]=(1.0-CA)*tl[tcx]+CA*ct;}++tctxn[tcx];} ++ctxn[cx]; }'''

new=''' uint8_t cx=p?(uint8_t)(((pr>>6)<<1) | (pr>=d[p-1])):(uint8_t)((pr>>6)<<1); uint8_t tcx=(uint8_t)(cx | (tf.bin2()<<3));
 uint8_t scx=0; if(K2_SPATIAL_MODE==1) scx=(uint8_t)(p&15u); else if(K2_SPATIAL_MODE==2) scx=(uint8_t)((p>>4)&15u); else if(K2_SPATIAL_MODE==3) scx=(uint8_t)(((p&15u)^((p>>4)&15u))&15u);
 double cg=K2LOG2(ml.total)-K2LOG2(ml.f[r]), cc=K2LOG2(mlctx[cx].total)-K2LOG2(mlctx[cx].f[r]); bool tactive=tf.confident(); double ct=tactive?(K2LOG2(mlt[tcx].total)-K2LOG2(mlt[tcx].f[r])):8.0;
 double cs=K2_SPATIAL_MODE?(K2LOG2(mls[scx].total)-K2LOG2(mls[scx].f[r])):8.0;
 bool rawMode=kp.use_raw(p);
 if(rawMode){ mraw.enc(a,x); }
 else { int sel=0; double best=gl[cx]; if(ctxn[cx]>=CTX_WARM && cl[cx]+CTX_MARGIN<best){sel=1;best=cl[cx];} if(tactive && tctxn[tcx]>=CTX_WARM && tl[tcx]+0.03<best){sel=2;best=tl[tcx];} if(K2_SPATIAL_MODE && sctxn[scx]>=CTX_WARM && sl[scx]+0.03<best){sel=3;best=sl[scx];}
   if(sel==0){ml.enc(a,r);mlctx[cx].learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);if(K2_SPATIAL_MODE)mls[scx].learn_lazy(r);}
   else if(sel==1){mlctx[cx].enc(a,r);ml.learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);if(K2_SPATIAL_MODE)mls[scx].learn_lazy(r);}
   else if(sel==2){mlt[tcx].enc(a,r);ml.learn_lazy(r);mlctx[cx].learn_lazy(r);if(K2_SPATIAL_MODE)mls[scx].learn_lazy(r);}
   else {mls[scx].enc(a,r);ml.learn_lazy(r);mlctx[cx].learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);}
   if((ctxn[cx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;gl[cx]=(1.0-CA)*gl[cx]+CA*cg;cl[cx]=(1.0-CA)*cl[cx]+CA*cc;}
   if(tactive){if((tctxn[tcx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;tl[tcx]=(1.0-CA)*tl[tcx]+CA*ct;}++tctxn[tcx];}
   if(K2_SPATIAL_MODE){if((sctxn[scx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;sl[scx]=(1.0-CA)*sl[scx]+CA*cs;}++sctxn[scx];}
   ++ctxn[cx]; }'''
assert old in s
s=s.replace(old,new,1)

old='''array<DecModel,RES_CTX_N> mlctx; array<DecModel,16> mlt; array<uint32_t,RES_CTX_N> ctxn{}; array<uint32_t,16> tctxn{}; array<double,RES_CTX_N> gl,cl; array<double,16> tl; gl.fill(8.0); cl.fill(8.0); tl.fill(8.0);'''
new='''array<DecModel,RES_CTX_N> mlctx; array<DecModel,16> mlt; array<DecModel,16> mls;
 array<uint32_t,RES_CTX_N> ctxn{}; array<uint32_t,16> tctxn{}; array<uint32_t,16> sctxn{};
 array<double,RES_CTX_N> gl,cl; array<double,16> tl,sl; gl.fill(8.0); cl.fill(8.0); tl.fill(8.0); sl.fill(8.0);'''
assert old in s
s=s.replace(old,new,1)

old=''' uint8_t pr=kp.predict(o,p); uint8_t cx=p?(uint8_t)(((pr>>6)<<1) | (pr>=o[p-1])):(uint8_t)((pr>>6)<<1); uint8_t tcx=(uint8_t)(cx | (tf.bin2()<<3)); uint8_t x,r;
 bool rawMode=kp.use_raw(p); bool tactive=tf.confident(); int sel=0; if(!rawMode){double best=gl[cx];if(ctxn[cx]>=CTX_WARM && cl[cx]+CTX_MARGIN<best){sel=1;best=cl[cx];}if(tactive && tctxn[tcx]>=CTX_WARM && tl[tcx]+0.03<best){sel=2;best=tl[tcx];}}
 if(rawMode){x=decsym(a,mraw);r=(uint8_t)(x-pr);} else if(sel==1){r=decsym_no_learn(a,mlctx[cx]);x=(uint8_t)(r+pr);} else if(sel==2){r=decsym_no_learn(a,mlt[tcx]);x=(uint8_t)(r+pr);} else {r=decsym_no_learn(a,ml);x=(uint8_t)(r+pr);}
 if(!rawMode){double cg=K2LOG2(ml.total)-K2LOG2(ml.f[r]),cc=K2LOG2(mlctx[cx].total)-K2LOG2(mlctx[cx].f[r]),ct=tactive?(K2LOG2(mlt[tcx].total)-K2LOG2(mlt[tcx].f[r])):8.0;
   if(sel==0){ml.learn(r);mlctx[cx].learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);}else if(sel==1){mlctx[cx].learn(r);ml.learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);}else{mlt[tcx].learn(r);ml.learn_lazy(r);mlctx[cx].learn_lazy(r);}
   if((ctxn[cx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;gl[cx]=(1.0-CA)*gl[cx]+CA*cg;cl[cx]=(1.0-CA)*cl[cx]+CA*cc;} if(tactive){if((tctxn[tcx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;tl[tcx]=(1.0-CA)*tl[tcx]+CA*ct;}++tctxn[tcx];}++ctxn[cx];}'''

new=''' uint8_t pr=kp.predict(o,p); uint8_t cx=p?(uint8_t)(((pr>>6)<<1) | (pr>=o[p-1])):(uint8_t)((pr>>6)<<1); uint8_t tcx=(uint8_t)(cx | (tf.bin2()<<3)); uint8_t scx=0; if(K2_SPATIAL_MODE==1) scx=(uint8_t)(p&15u); else if(K2_SPATIAL_MODE==2) scx=(uint8_t)((p>>4)&15u); else if(K2_SPATIAL_MODE==3) scx=(uint8_t)(((p&15u)^((p>>4)&15u))&15u); uint8_t x,r;
 bool rawMode=kp.use_raw(p); bool tactive=tf.confident(); int sel=0; if(!rawMode){double best=gl[cx];if(ctxn[cx]>=CTX_WARM && cl[cx]+CTX_MARGIN<best){sel=1;best=cl[cx];}if(tactive && tctxn[tcx]>=CTX_WARM && tl[tcx]+0.03<best){sel=2;best=tl[tcx];}if(K2_SPATIAL_MODE && sctxn[scx]>=CTX_WARM && sl[scx]+0.03<best){sel=3;best=sl[scx];}}
 if(rawMode){x=decsym(a,mraw);r=(uint8_t)(x-pr);} else if(sel==1){r=decsym_no_learn(a,mlctx[cx]);x=(uint8_t)(r+pr);} else if(sel==2){r=decsym_no_learn(a,mlt[tcx]);x=(uint8_t)(r+pr);} else if(sel==3){r=decsym_no_learn(a,mls[scx]);x=(uint8_t)(r+pr);} else {r=decsym_no_learn(a,ml);x=(uint8_t)(r+pr);}
 if(!rawMode){double cg=K2LOG2(ml.total)-K2LOG2(ml.f[r]),cc=K2LOG2(mlctx[cx].total)-K2LOG2(mlctx[cx].f[r]),ct=tactive?(K2LOG2(mlt[tcx].total)-K2LOG2(mlt[tcx].f[r])):8.0,cs=K2_SPATIAL_MODE?(K2LOG2(mls[scx].total)-K2LOG2(mls[scx].f[r])):8.0;
   if(sel==0){ml.learn(r);mlctx[cx].learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);if(K2_SPATIAL_MODE)mls[scx].learn_lazy(r);}
   else if(sel==1){mlctx[cx].learn(r);ml.learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);if(K2_SPATIAL_MODE)mls[scx].learn_lazy(r);}
   else if(sel==2){mlt[tcx].learn(r);ml.learn_lazy(r);mlctx[cx].learn_lazy(r);if(K2_SPATIAL_MODE)mls[scx].learn_lazy(r);}
   else {mls[scx].learn(r);ml.learn_lazy(r);mlctx[cx].learn_lazy(r);if(tactive)mlt[tcx].learn_lazy(r);}
   if((ctxn[cx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;gl[cx]=(1.0-CA)*gl[cx]+CA*cg;cl[cx]=(1.0-CA)*cl[cx]+CA*cc;}
   if(tactive){if((tctxn[tcx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;tl[tcx]=(1.0-CA)*tl[tcx]+CA*ct;}++tctxn[tcx];}
   if(K2_SPATIAL_MODE){if((sctxn[scx]&CTX_SCORE_MASK)==0u){constexpr double CA=CTX_ALPHA;sl[scx]=(1.0-CA)*sl[scx]+CA*cs;}++sctxn[scx];}
   ++ctxn[cx];}'''
assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP36_SPATIAL_RESIDUAL.cpp").write_text(s)
print("EXP36_SOURCE_BYTES",len(s.encode()))
