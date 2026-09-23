# AURORA Native 4K Parallel Scaling

Date: 2026-09-23
GitHub Actions run: 35871109006
Status: PASS

Synthetic 3840x2160 single-frame encode benchmark.

## Results

- 1 worker: 0.650928 s, 1.536 fps
- 2 workers: 0.343478 s, 2.911 fps
- 4 workers: 0.230661 s, 4.335 fps
- 8 workers: 0.236216 s, 4.233 fps

Packed bytes were identical for every worker count:
- 256,727 bytes

## Conclusion

Tile-level parallelism is deterministic and gives useful scaling.

Best point on the GitHub runner:
- 4 workers
- ~2.82x speedup versus 1 worker

8 workers do not improve further on this runner, indicating CPU/resource saturation or contention.

Do not assume 4 workers is the universal hardware optimum; worker count should eventually be hardware-adaptive.
