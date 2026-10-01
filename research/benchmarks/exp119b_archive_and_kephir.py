#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MiB=1024*1024
RAW=211_938_580
EXPECTED_KEPHIR=60_963_390


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(MiB),b''):
            h.update(b)
    return h.hexdigest()


def files():
    out=sorted(p for p in Path('corpora/silesia').iterdir() if p.is_file())
    assert sum(p.stat().st_size for p in out)==RAW
    return out


def sample_stratified(data,budget=2*MiB):
    if len(data)<=budget:
        return data
    chunk=budget//4
    maxoff=len(data)-chunk
    offsets=[(maxoff*i)//3 for i in range(4)]
    return b''.join(data[o:o+chunk] for o in offsets)[:budget]


def run(cmd,cwd=None):
    t=time.perf_counter()
    p=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,check=True)
    return time.perf_counter()-t,p


def kv(text):
    d={}
    for line in text.splitlines():
        if '=' in line:
            k,v=line.split('=',1); d[k]=v
    return d


def kcompress(cli,src,arc,extra):
    dt,p=run([str(cli),'c',str(src),str(arc),'4',*extra])
    return dt,int(kv(p.stdout)['OUTPUT_BYTES'])


def bench_kephir(cli,srcs,work):
    opts={
        'adaptive':['adaptive'],
        'grain4':['4096','4096','1'],
        'grain8':['8192','8192','1'],
    }
    total=0; probe=0.0; final=0.0; dec=0.0
    choices={k:0 for k in opts}
    for i,src in enumerate(srcs):
        t0=time.perf_counter()
        sample=work/f'ksample_{i}.bin'
        sample.write_bytes(sample_stratified(src.read_bytes()))
        sizes={}
        for name,extra in opts.items():
            a=work/f'kp_{i}_{name}.kpf'
            _,size=kcompress(cli,sample,a,extra)
            sizes[name]=size
            a.unlink()
        sample.unlink()
        probe+=time.perf_counter()-t0
        choice=min(opts,key=lambda x:(sizes[x],list(opts).index(x)))
        choices[choice]+=1
        a=work/f'kfull_{i}.kpf'
        dt,size=kcompress(cli,src,a,opts[choice]); final+=dt; total+=size
        out=work/f'kout_{i}'
        shutil.rmtree(out,ignore_errors=True)
        dt,_=run([str(cli),'d',str(a),str(out),'4']); dec+=dt
        restored=out/src.name
        assert restored.is_file() and sha256(restored)==sha256(src)
        a.unlink(); shutil.rmtree(out,ignore_errors=True)
    assert total==EXPECTED_KEPHIR,(total,EXPECTED_KEPHIR)
    enc=probe+final
    return {
        'name':'KEPHIR2 EXP-118B AUTO','archive_bytes':total,'ratio':total/RAW,
        'compress_seconds':enc,'compress_MBps':RAW/1e6/enc,
        'probe_seconds':probe,'final_encode_seconds':final,
        'final_encode_MBps_excluding_probe':RAW/1e6/final,
        'decompress_seconds':dec,'decompress_MBps':RAW/1e6/dec,
        'choices':choices,
    }


def bench_archive(name,srcs,work,kind,level):
    total=0; enc=0.0; dec=0.0
    for i,src in enumerate(srcs):
        suffix={'7z':'.7z','zip':'.zip','rar':'.rar'}[kind]
        arc=(work/f'{name}_{i}{suffix}').resolve()
        out=(work/f'{name}_{i}_out').resolve()
        shutil.rmtree(out,ignore_errors=True); out.mkdir(parents=True)
        if kind=='7z':
            cmd=['7z','a','-bd','-y','-t7z','-m0=lzma2',f'-mx={level}',str(arc),src.name]
        elif kind=='zip':
            cmd=['7z','a','-bd','-y','-tzip','-mm=Deflate',f'-mx={level}',str(arc),src.name]
        elif kind=='rar':
            cmd=['rar','a','-ma5',f'-m{level}','-idq',str(arc),src.name]
        dt,_=run(cmd,cwd=src.parent.resolve()); enc+=dt; total+=arc.stat().st_size
        if kind in ('7z','zip'):
            dcmd=['7z','x','-bd','-y',f'-o{out}',str(arc)]
        else:
            dcmd=['unrar','e','-inul','-o+',str(arc),str(out)+os.sep]
        dt,_=run(dcmd); dec+=dt
        restored=out/src.name
        assert restored.is_file() and sha256(restored)==sha256(src),(name,src,restored)
        arc.unlink(); shutil.rmtree(out,ignore_errors=True)
    return {
        'name':name,'archive_bytes':total,'ratio':total/RAW,
        'compress_seconds':enc,'compress_MBps':RAW/1e6/enc,
        'decompress_seconds':dec,'decompress_MBps':RAW/1e6/dec,
    }


def main():
    if len(sys.argv)!=2: raise SystemExit('usage: exp119b_archive_and_kephir.py CLI')
    cli=Path(sys.argv[1]).resolve(); srcs=files()
    work=Path('exp119b_work'); shutil.rmtree(work,ignore_errors=True); work.mkdir()
    results=[]
    for fn in [
        lambda:bench_kephir(cli,srcs,work),
        lambda:bench_archive('7z-lzma2-mx5',srcs,work,'7z',5),
        lambda:bench_archive('7z-lzma2-mx9',srcs,work,'7z',9),
        lambda:bench_archive('zip-deflate-9',srcs,work,'zip',9),
        lambda:bench_archive('rar5-m5',srcs,work,'rar',5),
    ]:
        r=fn(); results.append(r)
        print('EXP119B_RESULT',r['name'],'BYTES',r['archive_bytes'],'RATIO',r['ratio'],'COMP_MBPS',r['compress_MBps'],'DEC_MBPS',r['decompress_MBps'],flush=True)
        if r['name'].startswith('KEPHIR'):
            print('EXP119B_KEPHIR_DETAIL','PROBE_SEC',r['probe_seconds'],'FINAL_SEC',r['final_encode_seconds'],'FINAL_MBPS',r['final_encode_MBps_excluding_probe'],'CHOICES',json.dumps(r['choices'],sort_keys=True),flush=True)
    Path('exp119b_results.json').write_text(json.dumps({'experiment':'EXP-119B','raw_bytes':RAW,'results':results},indent=2,sort_keys=True))
    shutil.rmtree(work,ignore_errors=True)
    print('EXP119B_COMPLETE',flush=True)

if __name__=='__main__': main()
