# KSV-12 — Motion Candidate Shortlist

Date: 2026-09-23
GitHub Actions run: 35871776726
Status: PASS / NO GLOBAL PROMOTION

## Goal

Reduce MC8R4 search cost by testing only the first 13 or 9 ordered motion candidates instead of all 25.

All variants remain lossless and SHA-verified.

## Results

### Akiyo
25 candidates:
- 2,209,935 bytes
- 6.604 s

13 candidates:
- 2,209,916 bytes
- -19 bytes
- 4.440 s

9 candidates:
- 2,209,906 bytes
- -29 bytes
- 3.620 s

### Foreman
25 candidates:
- 5,779,093 bytes
- 6.850 s

13 candidates:
- 5,837,597 bytes
- +58,504 bytes (+1.012%)
- 4.599 s

9 candidates:
- 5,867,846 bytes
- +88,753 bytes (+1.536%)
- 3.755 s

### Bus
25 candidates:
- 1,841,766 bytes
- 1.721 s

13 candidates:
- 1,844,607 bytes
- +2,841 bytes (+0.154%)
- 1.243 s

9 candidates:
- 1,845,962 bytes
- +4,196 bytes (+0.228%)
- 0.966 s

## Aggregate

25 candidates:
- 9,830,794 bytes
- 15.175 s

13 candidates:
- 9,892,120 bytes
- +61,326 bytes (+0.624%)
- 10.282 s (~32% faster)

9 candidates:
- 9,923,714 bytes
- +92,920 bytes (+0.945%)
- 8.341 s (~45% faster)

## Decision

Do not replace 25-candidate MC8R4 globally.

The shortlist is potentially useful only for low-motion content:
- Akiyo: safe and slightly smaller;
- Foreman/Bus: measurable compression regression.

Next research direction:
use a cheap pre-motion activity classifier to enable 9-candidate search only on low-motion windows.

This preserves the speed opportunity without paying the compression penalty on moving scenes.
