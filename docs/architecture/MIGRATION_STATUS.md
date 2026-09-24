# AURORA Media — Migration Status

**Status: COMPLETE**

The branch `project/aurora-media` is now isolated from the general-purpose compressor research tree.

## Completed migrations
- former `streaming/` source tree removed;
- C++ backend consolidated under `src/cpp/aurora_media/`;
- Python reference under `src/python/reference/`;
- tests under `tests/`;
- audio/video/backend research under `research/`;
- reusable benchmarks under `benchmarks/`;
- measured outputs under `results/`;
- long-lived documentation under `docs/`;
- minimal KHEPRI construction dependency isolated under `engine/khepri/`.

## General-purpose cleanup
Inherited Silesia, EXP and FAST scripts and their general-purpose workflows were removed from this branch.

The complete general-purpose lineage is maintained on `project/aurora-compressor`.

## Workflow policy
Media workflows use canonical media paths and the isolated `engine/khepri/` backend kit. Historical KS/KSV jobs may create temporary runtime directories, but those are CI artifacts and not tracked source.

## Rule
No new general-purpose compressor experiment may be added to this branch. New media production code, reference code, tests, experiments and results must use their canonical directories.
