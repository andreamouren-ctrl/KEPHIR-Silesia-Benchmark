from pathlib import Path
p=Path("KEPHIR_FAST_O.cpp")
s=p.read_text()

old='''    static constexpr uint32_t NIL=0xFFFFFFFFu;
    vector<uint32_t> links((size_t)HS+(size_t)n,NIL);
    uint32_t* head=links.data();
    uint32_t* prev=links.data()+HS;'''
new='''    static constexpr uint32_t NIL=0xFFFFFFFFu;
    // FAST-R: persistent per-worker parser scratch.
    // Avoids clearing HS+n uint32_t entries for every chunk.
    thread_local vector<uint32_t> k2_head;
    thread_local vector<uint32_t> k2_stamp;
    thread_local vector<uint32_t> k2_prev;
    thread_local uint32_t k2_epoch=0;
    if(k2_head.size()<(size_t)HS) k2_head.resize((size_t)HS);
    if(k2_stamp.size()<(size_t)HS) k2_stamp.resize((size_t)HS,0);
    if(k2_prev.size()<(size_t)n) k2_prev.resize((size_t)n);
    ++k2_epoch;
    if(k2_epoch==0){
        fill(k2_stamp.begin(),k2_stamp.end(),0);
        k2_epoch=1;
    }
    uint32_t* head=k2_head.data();
    uint32_t* stamp=k2_stamp.data();
    uint32_t* prev=k2_prev.data();
    auto gethead=[&](uint32_t s)->uint32_t{
        return stamp[s]==k2_epoch ? head[s] : NIL;
    };'''
if old not in s: raise SystemExit("ALLOC_PATTERN_NOT_FOUND")
s=s.replace(old,new,1)

old='''    auto insert=[&](int p){ if(p+MINL<=n){uint32_t s=slot(h4(p)); prev[(uint32_t)p]=head[s]; head[s]=(uint32_t)p;} };'''
new='''    auto insert=[&](int p){ if(p+MINL<=n){uint32_t s=slot(h4(p)); prev[(uint32_t)p]=gethead(s); head[s]=(uint32_t)p; stamp[s]=k2_epoch;} };'''
if old not in s: raise SystemExit("INSERT_PATTERN_NOT_FOUND")
s=s.replace(old,new,1)

old='''        uint32_t s=slot(hp), q=head[s]; int depth=0;'''
new='''        uint32_t s=slot(hp), q=gethead(s); int depth=0;'''
if old not in s: raise SystemExit("FINDBEST_HEAD_NOT_FOUND")
s=s.replace(old,new,1)

old='''        uint32_t ss=slot(hp), q=head[ss]; int depth=0;'''
new='''        uint32_t ss=slot(hp), q=gethead(ss); int depth=0;'''
if old in s:
    s=s.replace(old,new,1)

Path("KEPHIR_FAST_R.cpp").write_text(s)
print("FAST_R_PERSISTENT_SCRATCH_READY")
