# KS-V02 — Multi-Motion Generalization

Date: 2026-09-23  
GitHub Actions run: 35818687799  
Result: **PASS / TEMPORAL-ONLY HYPOTHESIS REJECTED AS GENERAL SOLUTION**

All paths are lossless and bit-exact.

| Clip | Frames | Direct EXP-33H | Temporal GOP10 + EXP-33H | FFV1 L3 GOP10 | Temporal vs FFV1 |
|---|---:|---:|---:|---:|---:|
| Akiyo | 300 | 3,151,043 | **2,211,433** | 3,468,622 | **-36.245%** |
| Foreman | 300 | 7,160,599 | 6,079,072 | **5,295,415** | **+14.799%** |
| Bus | 75 | 1,910,181 | 2,009,484 | **1,593,314** | **+26.120%** |

## Interpretation

The KS-V01 Akiyo result is real but content-dependent.

A simple previous-frame residual is highly effective for low-motion content, but loses badly when objects or the camera move. EXP-33H itself remains a strong backend; the missing component is a media transform that converts motion into a residual geometry KHEPRI can exploit.

## Decision

Do not promote simple temporal prediction as the video core.

Next research target:
- bounded, chunk-local motion hypotheses;
- deterministic recovery boundaries;
- KHEPRI-specific selection cost;
- residual arrangement aligned to the backend's measured 16/256 topology.

Generic block matching, motion vectors and rate-distortion mode decisions are BACKGROUND unless a distinct KHEPRI-specific mechanism is demonstrated and survives prior-art review.
