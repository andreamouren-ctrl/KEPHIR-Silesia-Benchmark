# KEPHIR 2 Native Core

This directory is the production-oriented native core for KEPHIR 2.

It is intentionally separate from `research/`. Research checkpoints remain the scientific record; code promoted here must have stable interfaces, tests and product-level invariants.

## Current milestone

The first native contract is the **Global Strategy Router**.

It defines:
- product profiles: AUTO, FAST, BALANCED, MAX;
- archive layouts: FLAT, SMART, HYBRID;
- bounded archive features;
- bounded layout probe results;
- a self-contained `StrategyPlan`.

The router is **probe-first**. Metadata-only heuristics are fallback behavior and must not become the primary production decision mechanism.

## Invariants

- exact lossless decode is mandatory;
- integrity verification remains enabled for all commercial profiles;
- learned Factory/Local/Session state may influence encoding decisions but is never required by the decoder;
- the archive must be self-describing;
- every promoted optimization must have a focused benchmark and regression test.

## Planned native modules

```text
include/kephir2/
  strategy.hpp

src/
  strategy.cpp

future:
  analyzer/
  archive/
  transforms/
  learning/
  scheduler/
  parser/
  entropy/
```

## Build

```bash
cmake -S src/kephir2 -B build/kephir2 -DCMAKE_BUILD_TYPE=Release
cmake --build build/kephir2 --parallel
ctest --test-dir build/kephir2 --output-on-failure
```
