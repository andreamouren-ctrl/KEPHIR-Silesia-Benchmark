# KSV-07 — Residual Symbol Mapping

Date: 2026-09-23
GitHub Actions run: 35849374472
Backend: KHEPRI EXP-37A
Result: PASS / CONDITIONAL PROMOTION THROUGH KSV-08

## Result summary

ZZ_INTER versus MOD8:
- Akiyo: -43,855 bytes (-1.985%)
- Foreman: -9,721 bytes (-0.168%)
- Bus: +33,059 bytes (+1.795%)

ZZ_ALL was weaker than ZZ_INTER on all useful cases.

## Decision

Do not use ZZ_INTER globally.

Retain it as an adaptive candidate inside KSV-08.

ZZ_ALL is rejected for the current pipeline.
