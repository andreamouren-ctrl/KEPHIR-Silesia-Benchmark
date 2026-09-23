from pathlib import Path
p=Path("KEPHIR_FAST_U.cpp")
s=p.read_text()

old='''    const auto dualLitPref=k2_psg_literal_prefix_cost(d,LIT,K2_PSG_MODE);
    auto dualLcost=[&](int p,int len)->double{
        int e=min(n,p+len);
        return dualLitPref[(size_t)e]-dualLitPref[(size_t)p];
    };'''
new='''#if K2_PSG_MODE==0
    auto dualLcost=[&](int p,int len)->double{
        (void)p;
        return LIT*(double)len;
    };
#else
    const auto dualLitPref=k2_psg_literal_prefix_cost(d,LIT,K2_PSG_MODE);
    auto dualLcost=[&](int p,int len)->double{
        int e=min(n,p+len);
        return dualLitPref[(size_t)e]-dualLitPref[(size_t)p];
    };
#endif'''
if old not in s: raise SystemExit("DUAL_LIT_PREF_BLOCK_NOT_FOUND")
s=s.replace(old,new,1)

Path("KEPHIR_FAST_V.cpp").write_text(s)
print("FAST_V_LITERAL_COST_FASTPATH_READY")
