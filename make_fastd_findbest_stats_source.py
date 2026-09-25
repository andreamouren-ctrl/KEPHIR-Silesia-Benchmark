from pathlib import Path

s=Path("KEPHIR_SPEED_D_SOURCE.cpp").read_text()

anchor='''        while(q!=NIL && depth<maxDepth){'''
if anchor not in s: raise SystemExit("LOOP_ANCHOR_NOT_FOUND")

insert='''        thread_local unsigned long long st_nodes=0,st_h4=0,st_prefilter=0,st_extended=0,st_stop_lim=0,st_stop128=0,st_stop64=0,st_stop32=0;
        st_nodes=st_h4=st_prefilter=st_extended=st_stop_lim=st_stop128=st_stop64=st_stop32=0;
'''
sig='''    auto findbest=[&](int p,int maxDepth)->pair<int,int>{'''
if sig not in s: raise SystemExit("FINDBEST_SIG_NOT_FOUND")
s=s.replace(sig,sig+"\n"+insert,1)

s=s.replace(anchor,anchor+"\n            ++st_nodes;",1)

h4='''            if(dd>0 && dd<=W && q+3<n && h4(q)==hp){'''
s=s.replace(h4,h4+"\n                ++st_h4;",1)

pref='''                    if(d[q+bestL]!=d[p+bestL] || d[q+mid]!=d[p+mid]){
                        q=prev[q]; ++depth; continue;
                    }'''
if pref not in s: raise SystemExit("PREFILTER_NOT_FOUND")
s=s.replace(pref,'''                    if(d[q+bestL]!=d[p+bestL] || d[q+mid]!=d[p+mid]){
                        ++st_prefilter;
                        q=prev[q]; ++depth; continue;
                    }''',1)

ext='''                int l=4;'''
s=s.replace(ext,'''                ++st_extended;
                int l=4;''',1)

stop='''                bool stop=(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));'''
if stop not in s: raise SystemExit("STOP_NOT_FOUND")
s=s.replace(stop,'''                bool stop=(l==lim || (depth>=7 && bestL>=128) || (depth>=15 && bestL>=64) || (depth>=31 && bestL>=32));
                if(stop){
                    if(l==lim) ++st_stop_lim;
                    else if(depth>=7 && bestL>=128) ++st_stop128;
                    else if(depth>=15 && bestL>=64) ++st_stop64;
                    else if(depth>=31 && bestL>=32) ++st_stop32;
                }''',1)

ret='''        return {bestL,bestD};
    }'''
if ret not in s: raise SystemExit("RETURN_NOT_FOUND")
s=s.replace(ret,'''        if(k2_stats_enabled){
            k2_stats_nodes+=st_nodes; k2_stats_h4+=st_h4; k2_stats_prefilter+=st_prefilter; k2_stats_extended+=st_extended;
            k2_stats_stop_lim+=st_stop_lim; k2_stats_stop128+=st_stop128; k2_stats_stop64+=st_stop64; k2_stats_stop32+=st_stop32;
        }
        return {bestL,bestD};
    }''',1)

global_anchor='''using namespace std;'''
if global_anchor not in s: raise SystemExit("USING_NOT_FOUND")
globals='''using namespace std;
thread_local bool k2_stats_enabled=false;
thread_local unsigned long long k2_stats_nodes=0,k2_stats_h4=0,k2_stats_prefilter=0,k2_stats_extended=0,k2_stats_stop_lim=0,k2_stats_stop128=0,k2_stats_stop64=0,k2_stats_stop32=0;'''
s=s.replace(global_anchor,globals,1)

Path("KEPHIR_SPEED_D_STATS_SOURCE.cpp").write_text(s)
print("FAST_D_FINDBEST_STATS_OK",len(s))
