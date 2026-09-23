# KS-03 — Real-media lossless audio checkpoint

Date: 2026-09-23  
GitHub Actions run: 35819987558  
Result: **PASS / KMRL CONFIRMED ON REAL AUDIO**

## Source

Public Xiph.org Sintel trailer audio, decoded/resampled once to the common benchmark input:

- stereo PCM s16le
- 48 kHz
- 52.0 s
- 9,984,000 bytes
- SHA-256: `146d54c38755e6513ea823b6a08a705a5c852e5d725c7c7bf3603d52c19d3744`
- streaming block target: 20 ms / 960 frames

Every lossless candidate reconstructed the same PCM bit-exactly.

## Results

| Codec | Bytes | % PCM | Bits/sample | Encode real-time | Decode real-time |
|---|---:|---:|---:|---:|---:|
| Direct KEPHIR EXP-33H | 9,551,811 | 95.671% | 15.307 | 157.8x | 1254.2x |
| KS-01 varint + KEPHIR | 6,999,614 | 70.108% | 11.217 | 21.1x | 16.7x |
| **KMRL-0 + KEPHIR** | **5,775,307** | **57.846%** | **9.255** | **6.77x** | **17.28x** |
| FLAC -5, block 960 | 4,730,170 | 47.378% | 7.580 | 455.5x | 866.6x |

## Derived deltas

KMRL-0 + KEPHIR is:
- about **39.54% smaller** than direct EXP-33H on the same PCM;
- about **17.49% smaller** than KS-01 + KEPHIR;
- about **22.09% larger** than FLAC in final byte count.

## Interpretation

The KMRL improvement survived the move from the deterministic synthetic signal to a real music/cinematic audio source. The residual-geometry / KEPHIR-backend coupling remains a valid research direction.

The current Python KMRL frontend is not speed-competitive with FLAC and must not be treated as production code. Its purpose is to test representation hypotheses.

The next research goal is not generic LPC tuning. It is to make predictor selection aware of the topology that the KEPHIR backend can exploit, then measure whether that lowers the **final KEPHIR archive size** on this same real-media source.

## IP note

No patentability conclusion is made from this result. Known predictors, residual coding, stereo decorrelation and entropy coding remain background techniques. Candidate-IP focus remains the coupling among residual-field geometry, topology-aware serialization/predictor decisions and KEPHIR's native match-distance model.
