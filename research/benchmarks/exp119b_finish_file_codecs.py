#!/usr/bin/env python3
import hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
RAW=211_938_580
MiB=1024*1024

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(MiB),b''): h.update(b)
 return h.hexdigest()

def wall(cmd, stdout=None):
 t=time.perf_counter(); p=subprocess.run(cmd,stdout=stdout if stdout is not None else subprocess.PIPE,stderr=subprocess.PIPE,check=True,text=False); return time.perf_counter()-t,p

def metric(name,n,e,d,extra=None):
 r={'name':name,'archive_bytes':n,'ratio':n/RAW,'compress_seconds':e,'compress_MBps':RAW/1e6/e,'decompress_seconds':d,'decompress_MBps':RAW/1e6/d}
 if extra:r.update(extra)
 return r

def files():
 fs=sorted(p for p in Path('corpora/silesia').iterdir() if p.is_file()); assert sum(p.stat().st_size for p in fs)==RAW; return fs

def sample(data,budget=2*MiB):
 if len(data)<=budget:return data
 chunk=budget//4; maxoff=len(data)-chunk; offs=[maxoff*i//3 for i in range(4)]; return b''.join(data[o:o+chunk] for o in offs)[:budget]

def kv(out):
 d={}
 for line in out.decode().splitlines():
  if '=' in line:
   k,v=line.split('=',1); d[k]=v
 return d

def kephir(cli,fs,w):
 cand={'adaptive':['adaptive'],'grain4':['4096','4096','1'],'grain8':['8192','8192','1']}
 n=0; probe=0.; final=0.; dec=0.; choices={k:0 for k in cand}
 for i,s in enumerate(fs):
  sm=w/f's{i}.bin'; sm.write_bytes(sample(s.read_bytes())); t0=time.perf_counter(); sizes={}
  for k,x in cand.items():
   a=w/f'p{i}_{k}.kpf'; dt,p=wall([str(cli),'c',str(sm),str(a),'4',*x]); sizes[k]=a.stat().st_size; a.unlink()
  probe+=time.perf_counter()-t0; sm.unlink(); c=min(cand,key=lambda k:(sizes[k],list(cand).index(k))); choices[c]+=1
  a=w/f'k{i}.kpf'; dt,p=wall([str(cli),'c',str(s),str(a),'4',*cand[c]]); final+=dt; n+=a.stat().st_size
  o=w/f'ko{i}'; shutil.rmtree(o,ignore_errors=True); dt,p=wall([str(cli),'d',str(a),str(o),'4']); dec+=dt
  assert (o/s.name).is_file() and sha(o/s.name)==sha(s); a.unlink(); shutil.rmtree(o,ignore_errors=True)
 total=probe+final; assert n==60_963_390
 return metric('KEPHIR2 EXP-118B AUTO',n,total,dec,{'probe_seconds':probe,'final_encode_seconds':final,'final_encode_MBps_excluding_probe':RAW/1e6/final,'choices':choices})

def archive_codec(name,fs,w,build,extract,suffix):
 n=0;e=0.;d=0.
 for i,s in enumerate(fs):
  a=w/f'{name}{i}{suffix}'; o=w/f'{name}{i}out'; shutil.rmtree(o,ignore_errors=True); o.mkdir()
  dt,_=wall(build(s,a)); e+=dt; n+=a.stat().st_size
  dt,_=wall(extract(a,o)); d+=dt
  out=o/s.name; assert out.is_file() and sha(out)==sha(s)
  a.unlink(); shutil.rmtree(o)
 return metric(name,n,e,d)

def main():
 cli=Path(sys.argv[1]).resolve(); fs=files(); w=Path('exp119b_work'); shutil.rmtree(w,ignore_errors=True); w.mkdir()
 rows=[]
 rows.append(kephir(cli,fs,w)); print('EXP119B_DONE',rows[-1],flush=True)
 specs=[
 ('7z-lzma2-mx5',lambda s,a:['7z','a','-bd','-y','-t7z','-m0=lzma2','-mx=5',str(a),str(s)],lambda a,o:['7z','e','-bd','-y',f'-o{o}',str(a)],'.7z'),
 ('7z-lzma2-mx9',lambda s,a:['7z','a','-bd','-y','-t7z','-m0=lzma2','-mx=9',str(a),str(s)],lambda a,o:['7z','e','-bd','-y',f'-o{o}',str(a)],'.7z'),
 ('zip-deflate-9',lambda s,a:['7z','a','-bd','-y','-tzip','-mm=Deflate','-mx=9',str(a),str(s)],lambda a,o:['7z','e','-bd','-y',f'-o{o}',str(a)],'.zip'),
 ('rar5-m5',lambda s,a:['rar','a','-ma5','-m5','-idq',str(a),str(s)],lambda a,o:['unrar','e','-inul','-o+',str(a),str(o)+os.sep],'.rar')]
 for sp in specs:
  r=archive_codec(*sp[:1],fs,w,*sp[1:]); rows.append(r); print('EXP119B_DONE',r,flush=True)
 Path('exp119b_results.json').write_text(json.dumps({'experiment':'EXP-119B','raw_bytes':RAW,'results':rows},indent=2)); shutil.rmtree(w); print('EXP119B_COMPLETE',flush=True)
if __name__=='__main__': main()
