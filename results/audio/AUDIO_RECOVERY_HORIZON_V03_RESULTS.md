# AURORA Audio Recovery Horizon v0.3

Date: 2026-09-23
GitHub Actions run: 35844650459

## Results

- 200 ms: 5,825,143 bytes
- 500 ms: 5,715,709 bytes
- 1000 ms: 5,599,490 bytes
- 2000 ms: 5,546,958 bytes

All variants were bit-exact.

## Decision

Promote 2000 ms as the current fixed lossless audio recovery baseline.

This is not the final KASH design. It is the best validated fixed recovery horizon tested in this checkpoint.

The pure AUM metadata at 2000 ms is only ~1,732 bytes. The major size difference at shorter horizons comes from repeated KHEPRI state resets, not container overhead.
