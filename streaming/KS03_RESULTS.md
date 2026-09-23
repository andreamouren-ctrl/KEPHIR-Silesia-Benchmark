# KS-03 — Real Audio Checkpoint

Date: 2026-09-23
GitHub Actions run: 35813138749
Result: PASS

Source: Xiph.org Sintel trailer audio, converted to a common benchmark PCM:
- stereo s16le
- 48 kHz
- 52.0 seconds
- 9,984,000 bytes
- SHA-256: 146d54c38755e6513ea823b6a08a705a5c852e5d725c7c7bf3603d52c19d3744

All lossless outputs were verified bit-exact against that derived PCM.

| Codec/path | Bytes | % PCM | bits/sample | Encode realtime |
|---|---:|---:|---:|---:|
| Direct EXP-33H | 9,551,811 | 95.671% | 15.307 | 145.9x |
| KS-01 varint 20 ms + EXP-33H | 6,999,614 | 70.108% | 11.217 | 20.65x |
| KMRL-0 20 ms + EXP-33H | 5,775,307 | 57.846% | 9.255 | 6.27x |
| FLAC -5, block 960 (20 ms) | 4,730,170 | 47.378% | 7.580 | 513.2x |

## Decision

KMRL is technically validated on real audio and substantially improves the generic backend, but does not yet match FLAC. No superiority claim is permitted.

The current Python frontend is research code; its encode timing must not be treated as representative of a future C++ implementation.
