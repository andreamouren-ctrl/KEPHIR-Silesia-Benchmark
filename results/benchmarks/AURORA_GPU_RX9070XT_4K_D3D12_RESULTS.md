# AURORA D3D12 4K — RX 9070 XT checkpoint

Date: 2026-09-24

## Environment

- Adapter: AMD Radeon RX 9070 XT
- Driver: 32.0.31041.1004 (2026-08-17)
- API: Direct3D 12 hardware adapter
- Workload: 3840x2160 YUV420p8, MC8R4 motion, residual and reconstruction
- Frames measured: 3 after one warm-up frame

## Final result

| Metric | CPU reference | D3D12 |
|---|---:|---:|
| Motion | 150.821 ms | 2.686 ms |
| Residual | 157.284 ms | 5.655 ms |
| Reconstruction | 19.541 ms | 5.805 ms |
| Total | 327.646 ms | 14.146 ms |
| Throughput | 36.214 MiB/s | 838.752 MiB/s |
| FPS | 3.052 | 70.690 |

- D3D12 speedup: 23.161x.
- 60 FPS real-time factor: 1.178x.
- Lossless verification: `mismatches=0`.

## Changes validated

1. Residual and reconstruction shaders use packed byte output rather than a
   32-bit value for every output byte.
2. Motion, residual and reconstruction reuse their D3D12 upload, default,
   readback and descriptor resources across frames of the same resolution.

The benchmark remains end-to-end for each compute stage: transfer overhead is
included in the reported D3D12 times.
