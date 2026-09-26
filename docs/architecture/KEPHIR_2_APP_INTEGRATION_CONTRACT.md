# KEPHIR 2 — Application Integration Contract

**Status:** integration boundary freeze candidate
**Target:** AURORA application / future host applications
**Scope:** general-purpose lossless compression engine

## Objective

The host application must not depend on KEPHIR research files, EXP numbers, subprocess conventions, temporary-file layout, or backend implementation details.

The application integrates with one stable engine boundary:

Application / GUI → stable KEPHIR 2 API → Analyzer / AUTO Router → Directory Packing → KPF Archive Layer → Scheduler → Compression Backend → Integrity Verification.

## Ownership boundary

The application owns user interface, input/output selection, overwrite confirmation, progress presentation, cancellation controls, application settings, and job history.

KEPHIR owns input analysis, AUTO strategy, grouping, profiles, worker selection, archive framing, integrity verification, extraction safety, compression/decompression backend, and technical progress metrics.

The GUI must never reproduce KEPHIR routing logic.

## Binary boundary

The preferred production boundary is a **versioned C ABI** exported by a native library. This avoids C++ ABI coupling, makes DLL replacement safer on Windows, and allows future bindings without changing the engine internals.

A thin optional C++ wrapper may exist above the C ABI.

## API v1 requirements

The public ABI must expose engine/API version, engine create/destroy, compression, extraction, archive inspection, progress callback, cancellation callback, stable result/error codes, input/output byte metrics, profile selection, worker override, integrity verification, and overwrite policy.

Profiles exposed to the application are AUTO, FAST, BALANCED, and MAX. Internal EXP identifiers are never exposed.

## Stable progress phases

SCANNING → ANALYZING → PLANNING → PACKING → COMPRESSING → WRITING → VERIFYING → EXTRACTING → DONE.

The implementation inside a phase may change without breaking the host application.

## Cancellation

Cancellation is cooperative and checked at safe boundaries. It must never leave a valid-looking partial archive. Temporary output is removed or clearly incomplete. Extraction must remain inside the destination root. Cancellation returns a dedicated status code.

## Error boundary

No C++ exception may cross the public ABI. Public operations return stable status codes plus optional diagnostic text.

Initial status families: OK, CANCELLED, INVALID_ARGUMENT, INPUT_NOT_FOUND, OUTPUT_EXISTS, IO_ERROR, UNSUPPORTED_ARCHIVE, CORRUPT_ARCHIVE, INTEGRITY_ERROR, BACKEND_UNAVAILABLE, INTERNAL_ERROR.

## Migration from the old engine

The application should use one adapter/facade with two temporary backends: Legacy Engine and KEPHIR 2.

Migration sequence:
1. Freeze the host-side adapter contract.
2. Integrate the KEPHIR 2 DLL beside the legacy engine.
3. Add a developer-only engine selector.
4. Run A/B archive creation and extraction tests.
5. Make KEPHIR 2 the default after qualification.
6. Keep the legacy fallback for one compatibility release if required.
7. Remove the legacy engine only after field validation.

## Current readiness

Already native and validated: Content Analyzer, AUTO pre-router, Compression Planner, KPF1 varint/manifest, KPF1 file/directory outer framing, and path-safety checks.

In progress: native directory packing plan.

Still to migrate before replacement: group streaming/execution, compression backend as a native library, decompression backend as a native library, end-to-end KPF archive operations, progress/cancellation plumbing, and application-level integration tests.

## Compatibility rule

Until an explicit KPF2 migration is approved, KEPHIR 2 native components must preserve KPF1 compatibility where the current format is retained.

## Release gate for replacing the old engine

The legacy engine is not removed until native file and directory roundtrip, extraction, KPF compatibility, corruption rejection, path traversal rejection, cancellation, progress callbacks, multi-thread stress, large-file tests, many-small-file tests, application A/B integration, benchmark matrix, and release-candidate soak tests are all green.

This document is the application/engine boundary. Internal KEPHIR R&D must not leak across it.
