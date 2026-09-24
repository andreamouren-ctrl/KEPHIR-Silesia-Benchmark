from pathlib import Path

p=Path("KEPHIR_2_EXP37_DUAL_MATCH.cpp")
s=p.read_text()

s=s.replace("    double ema=LIT;\n", "    double ema=LIT;\n    double fastEma=LIT;\n", 1)

old='''        } else {
            // Conservative three-zone gate.
            w = pcost>=7.0 ? 0.68 : (pcost<=4.5 ? 0.38 : 0.50);
        }
        double c=(1.0-w)*LIT+w*pcost;'''

new='''        } else if(mode==6){
            // ULTRA transition-aware gate.
            // A fast and a slow residual-cost EMA expose local regime shifts.
            // The base three-zone prior is adjusted by both instantaneous
            // surprise and the short-vs-long trend.
            double base = pcost>=7.0 ? 0.68 : (pcost<=4.5 ? 0.38 : 0.50);
            double z = surprise / 3.0;
            if(z>1.0) z=1.0;
            if(z<-1.0) z=-1.0;
            double trend = (fastEma-ema) / 2.0;
            if(trend>1.0) trend=1.0;
            if(trend<-1.0) trend=-1.0;
            w = base + 0.08*z + 0.08*trend;
            if(w<0.24) w=0.24;
            if(w>0.82) w=0.82;
        } else {
            // Conservative three-zone gate.
            w = pcost>=7.0 ? 0.68 : (pcost<=4.5 ? 0.38 : 0.50);
        }
        double c=(1.0-w)*LIT+w*pcost;'''

assert old in s
s=s.replace(old,new,1)

old2='''        ema=0.97*ema+0.03*pcost;
        rm.learn_lazy(r);'''
new2='''        ema=0.97*ema+0.03*pcost;
        fastEma=0.85*fastEma+0.15*pcost;
        rm.learn_lazy(r);'''
assert old2 in s
s=s.replace(old2,new2,1)

Path("KEPHIR_2_EXP55_ULTRA_TRANSITION_PSG.cpp").write_text(s)
print("EXP55_SOURCE_BYTES",len(s.encode()))
