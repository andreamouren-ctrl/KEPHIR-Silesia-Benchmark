from pathlib import Path
p=Path("KEPHIR_FAST_K.cpp")
s=p.read_text()
old='''    vector<uint32_t> links((size_t)HS+(size_t)n,NIL);
    uint32_t* head=links.data();
    uint32_t* prev=links.data()+HS;'''
new='''    unique_ptr<uint32_t[]> links(new uint32_t[(size_t)HS+(size_t)n]);
    uint32_t* head=links.get();
    uint32_t* prev=links.get()+HS;
    fill_n(head,(size_t)HS,NIL);'''
if old not in s: raise SystemExit("LINKS_BLOCK_NOT_FOUND")
s=s.replace(old,new,1)
Path("KEPHIR_FAST_Q.cpp").write_text(s)
print("FAST_Q_UNINIT_PREV_READY")
