from pathlib import Path

p=Path("KEPHIR_2_EXP37_DUAL_MATCH.cpp")
s=p.read_text()

old='''        } else {
            // Conservative three-zone gate.
            w = pcost>=7.0 ? 0.68 : (pcost<=4.5 ? 0.38 : 0.50);
        }
        double c=(1.0-w)*LIT+w*pcost;'''

new='''        } else if(mode==5){
            // ULTRA local-surprise gate.
            // Keep the proven three-zone PSG prior, then adjust trust using
            // how surprising the current predictive residual is relative
            // to the recent local residual-cost EMA.
            double base = pcost>=7.0 ? 0.68 : (pcost<=4.5 ? 0.38 : 0.50);
            double z = surprise / 3.0;
            if(z>1.0) z=1.0;
            if(z<-1.0) z=-1.0;
            w = base + 0.12*z;
            if(w<0.24) w=0.24;
            if(w>0.82) w=0.82;
        } else {
            // Conservative three-zone gate.
            w = pcost>=7.0 ? 0.68 : (pcost<=4.5 ? 0.38 : 0.50);
        }
        double c=(1.0-w)*LIT+w*pcost;'''

assert old in s
s=s.replace(old,new,1)

Path("KEPHIR_2_EXP53_ULTRA_PSG.cpp").write_text(s)
print("EXP53_SOURCE_BYTES",len(s.encode()))
