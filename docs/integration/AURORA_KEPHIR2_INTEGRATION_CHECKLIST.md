# AURORA Compressor — KEPHIR2 / AUR2 Integration Checklist

Use this checklist when replacing the current KEPHIR1/AUR1 write path inside AURORA Compressor.

## 1. Keep legacy compatibility during migration

Recommended application architecture:

```text
CompressionService
  +-- Kephir2Backend      -> new writes: AUR2 / KEPHIR2
  +-- LegacyBackend       -> existing AUR1 / KEPHIR1 support
```

Do not delete the legacy reader before real user archives have been validated.

## 2. Integrate only the stable C ABI

SDK RC1 layout:

```text
include/kephir2/kephir2_c.h
bin/kephir2_api.dll
lib/kephir2_api.lib
cmake/Kephir2Config.cmake
docs/
VERSION
SHA256SUMS
```

Do not include research Python scripts or call C++ internal classes directly from the GUI.

Preferred CMake integration:

```cmake
find_package(Kephir2 CONFIG REQUIRED)
target_link_libraries(AURORA PRIVATE Kephir2::kephir2)
```

Point `Kephir2_DIR` at the SDK `cmake/` directory, or add the SDK root to the application's CMake prefix path. The installed application does not require Python; Python is only a source-build/generation dependency inside the KEPHIR repository.

## 3. Startup compatibility check

At application startup or first engine use:

1. call `kephir2_api_version()`;
2. require API version `1`;
3. optionally display `kephir2_engine_version()`;
4. create an engine with `kephir2_create()`;
5. call `kephir2_get_capabilities()`;
6. verify required capability bits before enabling UI actions.

Minimum recommended capabilities for the full AURORA experience:

- `KEPHIR2_CAP_COMPRESS_FILE`
- `KEPHIR2_CAP_COMPRESS_DIRECTORY`
- `KEPHIR2_CAP_EXTRACT`
- `KEPHIR2_CAP_INSPECT`
- `KEPHIR2_CAP_LIST_ENTRIES`
- `KEPHIR2_CAP_EXTRACT_SELECTED`
- `KEPHIR2_CAP_TEST_ARCHIVE`
- `KEPHIR2_CAP_AUR2_READ`
- `KEPHIR2_CAP_AUR2_WRITE`
- `KEPHIR2_CAP_PROGRESS_CALLBACK`
- `KEPHIR2_CAP_CANCELLATION`

## 4. Default options

Always initialize options with:

```c
kephir2_options_v1 options;
kephir2_options_init_v1(&options);
```

Recommended application defaults:

```text
profile = AUTO
workers = 0 (automatic)
verify_integrity = true
overwrite_output = false
allow_local_experience = true unless Privacy Mode disables it
```

Do not duplicate KEPHIR internal tuning parameters in AURORA settings.

## 5. Compression flow

```text
User selects file/directory
  -> AURORA validates destination
  -> create ProgressTask
  -> kephir2_compress(...)
  -> map status code
  -> refresh UI/history
```

New archives written by this engine are AUR2.

## 6. Extraction flow

Before extraction, prefer:

```text
kephir2_inspect
kephir2_list_entries
```

Then call:

```text
kephir2_extract
```

or:

```text
kephir2_extract_selected
```

for selected entries.

The engine performs transactional staging for AUR2 indexed extraction. A failure/cancellation must be reported to the user rather than treated as a partially successful extraction.

## 7. Archive test command

Expose an application action such as "Test archive" using:

```c
kephir2_test_archive(...)
```

This is the deep integrity path and is intentionally more expensive than simple inspect/list.

## 8. ProgressManager mapping

Map phases:

| KEPHIR | AURORA UI |
|---|---|
| IDLE | In attesa |
| SCANNING | Scansione |
| ANALYZING | Analisi |
| PLANNING | Pianificazione |
| PACKING | Preparazione archivio |
| COMPRESSING | Compressione |
| WRITING | Scrittura |
| VERIFYING | Verifica |
| EXTRACTING | Estrazione |
| DONE | Completato |

Use `fraction`, `processed_bytes`, `total_bytes` and `current_path_utf8` from the callback.

Callbacks may originate outside the GUI thread. Marshal updates through the application UI/event system.

## 9. Cancellation

The cancel callback returns non-zero when AURORA's `ProgressTask` has received a cancellation request.

Do not terminate the compression thread forcibly.

Map `KEPHIR2_CANCELLED` to a cancelled operation, not a generic failure.

## 10. Error mapping

Application logic must use `kephir2_status`, never parse the English diagnostic string.

Recommended UI mapping:

- `KEPHIR2_OK` -> success
- `KEPHIR2_CANCELLED` -> cancelled
- `KEPHIR2_INVALID_ARGUMENT` -> invalid operation/options
- `KEPHIR2_INPUT_NOT_FOUND` -> input missing
- `KEPHIR2_OUTPUT_EXISTS` -> overwrite decision required
- `KEPHIR2_IO_ERROR` -> file system I/O failure
- `KEPHIR2_UNSUPPORTED_ARCHIVE` -> unsupported archive/version
- `KEPHIR2_CORRUPT_ARCHIVE` -> malformed/corrupt archive
- `KEPHIR2_INTEGRITY_ERROR` -> integrity verification failed
- `KEPHIR2_BACKEND_UNAVAILABLE` -> engine/backend unavailable
- `KEPHIR2_INTERNAL_ERROR` -> unexpected engine error

Localization belongs to AURORA, not the DLL.

## 11. UTF-8 paths

All public C API path strings are UTF-8.

Do not convert them to the Windows ANSI code page.

## 12. Engine lifetime/threading

Recommended model:

- one engine handle per active compression/extraction job, or a serialized engine service;
- do not start concurrent mutating operations on the same engine handle;
- destroy the handle with `kephir2_destroy()` after the job/service lifetime ends.

## 13. Installer

The final AURORA installer must deploy the DLL next to the application executable (or another deterministic loader path):

```text
AURORA.exe
kephir2_api.dll
```

Do not install benchmark corpora, research scripts or GitHub workflow files.

Include the correct MSVC runtime through the installer if the chosen build configuration requires it.

## 14. Application migration policy

During RC1 integration:

- new compression can be routed to KEPHIR2/AUR2;
- legacy archives continue to use the existing compatibility path;
- keep a developer setting to switch old/new engine until integration QA is complete;
- do not expose experimental KEPHIR tuning in the normal UI.

## 15. Mandatory application integration tests

Before making KEPHIR2 the default writer, test through the actual AURORA executable:

- compress one regular file;
- compress a directory;
- empty file;
- empty directory;
- mixed directory;
- Unicode filenames;
- long Windows paths;
- overwrite deny/allow;
- cancellation during compression;
- cancellation during extraction;
- corrupted archive;
- archive inspection;
- file listing;
- selective extraction;
- archive test;
- progress monotonicity;
- installer clean machine test;
- uninstall/reinstall test;
- legacy AUR1/KEPHIR1 archive opening;
- new AUR2 archive reopening after application restart.

## 16. API-gap rule

If AURORA integration discovers a missing operation:

1. do not bypass the DLL by calling internal C++ classes;
2. document the exact use case;
3. add an ABI-compatible C API function/struct version on the RC branch;
4. add a test;
5. rebuild the SDK artifact;
6. update the freeze manifest.

Breaking changes are deferred to KEPHIR3/AUR3 unless required to prevent data loss/security failure.

## 17. Final release gate

After the application and installer are complete:

```text
AURORA application integration PASS
+ clean-machine installer PASS
+ KEPHIR2 RC qualification PASS
+ legacy compatibility PASS
= freeze KEPHIR 2.0 / AUR2.0 final
```

Only after that point should KEPHIR3/AUR3 development begin on a new branch/generation.
