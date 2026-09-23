# KS-V03 — Motion-Compensation Controls

Date: 2026-09-23  
GitHub Actions run: 35818980273  
Result: **PASS / IMPROVES TEMPORAL, STILL BELOW FFV1**

All paths reconstructed bit-exactly.

| Clip | Temporal | MC16/R4 | MC8/R4 | FFV1 | Best KHEPRI vs FFV1 |
|---|---:|---:|---:|---:|---:|
| Foreman | 6,079,072 | 5,828,896 | **5,781,680** | 5,295,415 | **+9.183%** |
| Bus | 2,009,484 | 1,865,094 | **1,842,544** | 1,593,314 | **+15.642%** |

## Decision

Bounded integer-pixel motion compensation recovers part of the KS-V02 gap, but ordinary block matching is not enough and is not candidate IP.

MC8/R4 is the strongest technical control from this checkpoint, but it is slower than real time in the Python prototype on Foreman and remains materially larger than FFV1.

Next experiment: residual block linearization aligned to KHEPRI's 256-byte distance topology. Fixed reordering remains BACKGROUND/control until a distinct KHEPRI-specific inventive mechanism is identified.
