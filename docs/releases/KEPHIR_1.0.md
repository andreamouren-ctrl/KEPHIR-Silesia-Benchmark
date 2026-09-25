# KEPHIR 1.0 — Qualified Release Baseline

**Promotion date:** 2026-09-25  
**Qualified engine commit:** `efd00a3cfc63d8306bef65aa90eb0154dc7b9004`  
**Qualification workflow:** `KEPHIR 1.0 Final Candidate Qualification`  
**Run:** `36151845469`  
**Conclusion:** **SUCCESS**  
**Roundtrip:** **FINAL_SHA_ALL_PASS**

## Release meaning

KEPHIR 1.0 è il primo checkpoint integrato del progetto in cui compressione, estrazione, packing directory, parallelizzazione, Adaptive Experience e verifica lossless funzionano insieme in un'unica superficie di prodotto.

Il file `release/kephir_final.py` del commit qualificato riporta `1.0.0-rc1`. Il marker viene mantenuto per non modificare il codice già qualificato; la baseline tecnica promossa è denominata **KEPHIR 1.0**.

## Componenti integrati

- EXP-75 come checkpoint algoritmo;
- EXP-76 come architettura di packing;
- adaptive grain;
- lazy/predictive Word-XOR;
- cost-aware parcel scheduling;
- ProcessPool encoder-side;
- content-first directory grouping;
- manifest compatto;
- Factory Knowledge v1;
- Local Experience opzionale;
- roundtrip verification;
- safe extraction path checks.

## Factory Knowledge v1

Fonte: EXP-75 multi-corpus training.

Stati positivi distillati:
- totale: **79**;
- adaptive grain: **77**;
- Word-XOR: **2**.

La Factory è encoder-only.

## Qualification environment

GitHub-hosted runner:
- logical CPU reported: **4**;
- Zstd CLI 1.5.7;
- Brotli 1.1.0;
- XZ Utils 5.4.5;
- 7-Zip 23.01.

I tempi su runner hosted sono soggetti a rumore; le dimensioni archivio sono il dato più stabile.

## Dataset 1 — repository real-world

- files: **242**
- logical bytes: **759,128**
- compact framed bytes competitor: **768,462**

| Compressor | Bytes | Ratio | Comp s | Dec s | SHA |
|---|---:|---:|---:|---:|:---:|
| Brotli-11 | 89,722 | 11.819% | 0.814 | 0.004 | PASS |
| XZ-9 | 91,944 | 12.112% | 0.103 | 0.007 | PASS |
| 7z-LZMA2 | 92,066 | 12.128% | 0.228 | 0.010 | PASS |
| Zstd-19 | 94,973 | 12.511% | 0.173 | 0.004 | PASS |
| Bzip2-9 | 108,731 | 14.323% | 0.060 | 0.019 | PASS |
| Gzip-9 | 115,059 | 15.157% | 0.024 | 0.004 | PASS |
| **KEPHIR 1.0 cold** | **117,523** | **15.481%** | **1.703** | **0.078** | **PASS** |
| **KEPHIR 1.0 Factory** | **117,523** | **15.481%** | **0.705** | **0.080** | **PASS** |
| LZ4-HC | 135,018 | 17.786% | 0.139 | 0.002 | PASS |

La Factory mantiene identica la dimensione e riduce il tempo di compressione da 1.703 s a 0.705 s.

## Dataset 2 — Silesia canonical

- files: **12**
- logical bytes: **211,938,580**
- compact framed bytes competitor: **211,938,700**

| Compressor | Bytes | Ratio | Comp s | Dec s | SHA |
|---|---:|---:|---:|---:|:---:|
| 7z-LZMA2 | 48,719,288 | 22.987% | 47.561 | 2.562 | PASS |
| XZ-9 | 48,767,040 | 23.010% | 79.733 | 2.866 | PASS |
| Brotli-11 | 49,774,776 | 23.485% | 415.287 | 0.622 | PASS |
| Zstd-19 | 52,854,090 | 24.938% | 46.595 | 0.254 | PASS |
| Bzip2-9 | 54,590,366 | 25.758% | 15.647 | 6.626 | PASS |
| **KEPHIR 1.0 cold** | **62,953,321** | **29.704%** | **96.050** | **13.645** | **PASS** |
| **KEPHIR 1.0 Factory** | **62,958,288** | **29.706%** | **75.057** | **13.629** | **PASS** |
| Gzip-9 | 67,650,744 | 31.920% | 19.424 | 1.242 | PASS |
| LZ4-HC | 78,001,175 | 36.804% | 7.340 | 0.225 | PASS |

## Interpretation

KEPHIR 1.0:
- è lossless e qualificato end-to-end;
- supera Gzip-9 e LZ4-HC sul rapporto Silesia;
- resta dietro Bzip2, Zstd, Brotli e LZMA2 sul rapporto puro;
- ha ancora un costo encoder/decoder elevato rispetto ai codec maturi;
- dimostra che la Factory Knowledge può ridurre lavoro encoder senza essere necessaria al decoder.

## Benchmark caveats

- Il repository cambia nel tempo: confronti con snapshot EXP-76 precedenti non sono 1:1.
- I competitor sul test directory ricevono una serializzazione compact-flat; KEPHIR usa il proprio packing raggruppato. È un confronto di sistemi di archivio realistico, non un test di backend su input byte-identico.
- Silesia Factory non è held-out rispetto alla Factory training; il profilo cold resta il riferimento neutro per il rapporto.
- I tempi GitHub hosted vanno interpretati con cautela.

## Frozen baseline

Non modificare retroattivamente il commit qualificato.

Le evoluzioni successive appartengono alla linea:
- KEPHIR 1.1 R&D;
- nuovi checkpoint EXP;
- eventuale CPU/GPU pipeline solo dopo validazione reale su hardware supportato.
