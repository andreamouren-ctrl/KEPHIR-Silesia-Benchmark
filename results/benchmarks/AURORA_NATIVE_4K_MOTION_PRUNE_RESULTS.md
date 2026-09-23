# AURORA Native 4K Motion Candidate Pruning

Date: 2026-09-23
GitHub Actions run: 35871460678
Status: PASS / SYNTHETIC DIAGNOSTIC

Synthetic 3840x2160, 4 workers.

## Results

25 candidates:
- 0.135092 s
- 7.402 fps
- 256,727 packed bytes

13 candidates:
- 0.104371 s
- 9.581 fps
- 194,899 packed bytes

9 candidates:
- 0.107434 s
- 9.308 fps
- 181,269 packed bytes

The synthetic source strongly favored candidate restriction in both speed and compressed size.

However KSV-12 on natural diagnostic clips showed that this does not generalize globally.

Therefore this result is retained as evidence for content-adaptive pruning, not as a production default.
