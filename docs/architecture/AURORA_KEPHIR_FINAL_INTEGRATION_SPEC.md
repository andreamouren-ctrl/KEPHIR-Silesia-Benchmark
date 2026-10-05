# AURORA / KEPHIR — Specifica tecnica finale di integrazione RC1

**Documento:** Integration & Technology Handoff Specification  
**Progetto:** AURORA Compressor / KEPHIR  
**Data snapshot:** 2026-10-05  
**Stato:** **KEPHIR 2.0.0 RC1 / AUR Container 2.0 — FEATURE FREEZE**  
**C ABI:** `KEPHIR2_API_VERSION = 1`

> Regola fondamentale: AURORA non deve dipendere da `research/`, numeri EXP, script Python, generatori, corpus, K75, grain, context, router o altri dettagli interni. L'applicazione integra KEPHIR esclusivamente tramite la C ABI pubblica e il pacchetto SDK RC1.

---

# 1. Obiettivo

Questo documento è il contratto tecnico di handoff per sostituire/affiancare il motore legacy KEPHIR1/AUR1 dentro AURORA Compressor con KEPHIR2/AUR2 senza riscrivere la GUI.

Architettura target:

```text
AURORA.exe
  -> GUI
  -> JobManager / ProgressManager
  -> CompressionService
  -> KephirBackend
  -> KEPHIR C ABI v1
  -> KEPHIR 2.0.0 RC1
  -> AUR Container 2.0
```

Durante la migrazione:

```text
CompressionService
  +-- Kephir2Backend   -> nuovo default writer AUR2 / KEPHIR2
  +-- LegacyBackend    -> compatibilità AUR1 / KEPHIR1 finché validata
```

Non rimuovere il reader legacy prima della qualification applicativa su archivi reali precedenti.

---

# 2. Stato congelato

Versioni RC1:

```text
KEPHIR Engine:       2.0.0-rc1
KEPHIR C ABI:        1
AUR Container:       2.0
Native K75 stream:   1
Legacy engine read:  KPF1
```

Branch motore di integrazione:

```text
release/kephir-2.0-aur2-integration-rc1
```

AUR2 qualificato deriva da:

```text
development/kephir-2-core
AUR2 integration commit: a46b84363a207db8d4a4e85a6ef9ea2f7e7a4a23
```

Il ramo RC1 contiene inoltre il core adaptive-context production-safe promosso dalla lineage precedente, senza importare EXP-120A o altre modifiche di ricerca incompatibili con il freeze.

---

# 3. Policy FEATURE FREEZE

Sono congelati:

- AUR2 major format;
- magic e fixed header;
- section ID pubblicati;
- feature bit pubblicati;
- C ABI v1;
- valori numerici di status/profile/phase;
- layout delle struct pubbliche v1;
- API base di integrazione;
- semantica delle API esistenti;
- stream format K75 usato dal decoder RC.

Sono consentiti prima della release finale 2.0.0:

- bug fix;
- security/data-loss fix;
- compatibilità;
- correzioni necessarie all'integrazione AURORA;
- API additive e backward-compatible solo se realmente indispensabili;
- packaging/SDK/installer support;
- documentazione;
- qualification/release engineering.

Sono vietati in KEPHIR2/AUR2:

- nuove strategie ratio;
- nuovi transform;
- mixed grain;
- nuovi matcher;
- nuovi entropy coder;
- redesign del container;
- breaking ABI;
- EXP-120/121 o altre grandi linee R&D.

Queste attività appartengono a KEPHIR3/AUR3, che inizierà solo dopo integrazione, test applicazione, installer e prima release AURORA.

---

# 4. Responsabilità dei layer

## AURORA possiede

- GUI e localizzazione;
- selezione input/output;
- conferma overwrite;
- JobManager;
- ProgressManager;
- history/notifiche;
- impostazioni utente;
- scelta profilo pubblico;
- thread/UI marshaling;
- compatibilità applicativa legacy AUR1/KEPHIR1;
- distribuzione della DLL tramite installer.

## KEPHIR2/AUR2 possiede

- scansione input;
- analisi contenuto;
- pianificazione;
- routing AUTO;
- packing directory;
- grain/context interni;
- transform interni;
- compressione/decompressione;
- framing AUR2;
- metadata container;
- integrity;
- path safety;
- selective extraction;
- transactional extraction;
- progress tecnico;
- cancellation cooperativa;
- KPF1 legacy read.

La GUI non deve replicare alcuna logica di compressione.

---

# 5. C ABI pubblica congelata

Header canonico:

```text
include/kephir2/kephir2_c.h
```

API:

```c
uint32_t kephir2_api_version(void);
const char* kephir2_engine_version(void);

kephir2_engine* kephir2_create(void);
void kephir2_destroy(kephir2_engine* engine);

void kephir2_options_init_v1(kephir2_options_v1* options);

kephir2_status kephir2_get_capabilities(
    kephir2_engine* engine,
    kephir2_capabilities_v1* capabilities);

kephir2_status kephir2_compress(...);
kephir2_status kephir2_extract(...);
kephir2_status kephir2_inspect(...);
kephir2_status kephir2_list_entries(...);
kephir2_status kephir2_test_archive(...);
kephir2_status kephir2_extract_selected(...);

const char* kephir2_status_name(kephir2_status status);
```

Runtime RC1:

```text
kephir2_api_version()    -> 1
kephir2_engine_version() -> "2.0.0-rc1"
```

Opaque handle:

```c
typedef struct kephir2_engine kephir2_engine;
```

AURORA non deve includere header C++ interni del motore.

---

# 6. Profili pubblici

```text
AUTO
FAST
BALANCED
MAX
```

`AUTO` è il default raccomandato.

Il profilo AUTO abilita nel backend RC1 la policy adaptive-context production-safe. Grain/context restano completamente interni e non fanno parte della ABI pubblica.

Default raccomandati:

```text
profile                = AUTO
workers                = 0
verify_integrity       = true
overwrite_output       = false
allow_local_experience = true, salvo Privacy Mode
```

Inizializzare sempre con:

```c
kephir2_options_v1 options;
kephir2_options_init_v1(&options);
```

---

# 7. Status code pubblici

Valori congelati:

```text
0  OK
1  CANCELLED
2  INVALID_ARGUMENT
3  INPUT_NOT_FOUND
4  OUTPUT_EXISTS
5  IO_ERROR
6  UNSUPPORTED_ARCHIVE
7  CORRUPT_ARCHIVE
8  INTEGRITY_ERROR
9  BACKEND_UNAVAILABLE
10 INTERNAL_ERROR
```

La GUI deve basare la logica sul valore `kephir2_status`, non sul testo diagnostico di `result.message`.

La localizzazione degli errori appartiene ad AURORA.

---

# 8. Progress e cancellation

Fasi pubbliche congelate:

```text
IDLE
SCANNING
ANALYZING
PLANNING
PACKING
COMPRESSING
WRITING
VERIFYING
EXTRACTING
DONE
```

Il callback riceve:

```text
phase
fraction
processed_bytes
total_bytes
current_path_utf8
```

Il progress multi-stream AUR2 è qualificato come globale e monotono:

- `fraction` non decresce;
- `processed_bytes` non decresce;
- `total_bytes` resta stabile;
- esiste un solo `DONE` finale.

Qualification storica: run `37237913015` PASS Linux/Windows.

Cancellation:

```c
typedef int (*kephir2_cancel_callback)(void* user_data);
```

`0` continua, non-zero richiede cancellazione.

AURORA non deve terminare forzatamente il worker. La cancellazione deve propagarsi in modo cooperativo al motore.

---

# 9. Capability query

AURORA deve interrogare `kephir2_get_capabilities()` invece di dedurre feature dalla versione della DLL.

Capability RC1 dichiarate:

```text
COMPRESS_FILE
COMPRESS_DIRECTORY
EXTRACT
INSPECT
LIST_ENTRIES
EXTRACT_SELECTED
TEST_ARCHIVE
AUR2_READ
AUR2_WRITE
KPF1_LEGACY_READ
SEEK_INDEX
FILESYSTEM_METADATA
FOOTER_INTEGRITY
STREAM_CRC32
PROGRESS_CALLBACK
CANCELLATION
```

Non sono dichiarate:

```text
ENCRYPTION
RECOVERY/PARITY
```

`aur_read_major_min = 2`, `aur_read_major_max = 2`, `aur_write_major = 2`.

---

# 10. AUR Container v2 — stato finale RC1

AUR2 non è più una proposta. È implementato e qualificato.

Caratteristiche:

- fixed header versionato da 64 byte;
- magic AUR2;
- little-endian;
- TLV sections;
- FILE_TABLE;
- CODEC_DESCRIPTOR;
- STREAM/BLOCK information;
- DATA;
- INTEGRITY;
- SEEK_INDEX / TOC;
- Footer Integrity `FTR1`;
- `toc_offset` attivo;
- `footer_offset` attivo;
- CRC32 per stream;
- integrità globale/footer;
- file;
- directory;
- directory vuote;
- file vuoti;
- metadata filesystem base;
- mtime;
- permessi portabili;
- path safety/path traversal rejection;
- struttura 64-bit per file >4 GiB;
- SMART directory packing;
- FLAT directory packing;
- inspect;
- list entries;
- deep archive test;
- selective extraction;
- KPF1 legacy reading;
- file-backed reader;
- ranged reads;
- bounded-memory extraction;
- file-backed finalizer;
- transactional extraction;
- rollback su corruption/cancellation/I/O failure;
- progress multi-stream monotono.

Non dichiarare supportati in AUR2 RC1:

- encryption;
- recovery/parity;
- ACL Windows completi;
- Alternate Data Streams;
- symlink preservation canonica;
- fully streaming K75 encode/decode.

Sono candidati futuri AUR3 salvo fix strettamente necessario alla release corrente.

---

# 11. Fixed Header AUR2

Layout congelato a 64 byte:

| Offset | Size | Campo |
|---:|---:|---|
| 0 | 8 | magic |
| 8 | 2 | container_major |
| 10 | 2 | container_minor |
| 12 | 4 | header_size |
| 16 | 8 | feature_flags |
| 24 | 8 | archive_id |
| 32 | 8 | logical_size |
| 40 | 8 | toc_offset |
| 48 | 8 | footer_offset |
| 56 | 4 | header_crc32 |
| 60 | 4 | reserved |

La specifica binaria completa resta in:

```text
docs/architecture/AUR2_CONTAINER_FORMAT.md
```

Lo stato implementativo resta in:

```text
docs/architecture/AUR2_IMPLEMENTATION_STATUS.md
```

AURORA non deve interpretare direttamente questi campi: usa `kephir2_inspect()` e le altre API pubbliche.

---

# 12. Integrità e corruption handling

Runtime:

- validazione header/section bounds;
- CRC32 stream;
- Footer Integrity FTR1;
- checksum/integrità container;
- corruption rejection;
- `kephir2_test_archive()` per verifica profonda.

Durante i test di qualification si usa anche SHA per validare round-trip esatto.

Un fallimento di integrità deve diventare `KEPHIR2_INTEGRITY_ERROR` o `KEPHIR2_CORRUPT_ARCHIVE` secondo il tipo di errore, mai un successo parziale.

---

# 13. File-backed I/O e memoria

Reader AUR2:

```text
header + TOC/Seek Index
  -> metadata
  -> stream necessario
  -> CRC
  -> decode
  -> release memoria stream
  -> stream successivo
```

Selective extraction legge soltanto gli stream richiesti.

Writer:

```text
Base AUR2
  -> file-backed finalizer
  -> metadata + Seek Index + FTR1
  -> publish
```

Il DATA viene copiato a blocchi; non è necessario materializzare l'intero `.aur` in RAM.

Qualification finalizer: run `36917547860` PASS Linux/Windows.  
Writer pubblico: run `36918208737` PASS Linux/Windows.

---

# 14. Transactional extraction

`kephir2_extract()` e `kephir2_extract_selected()` usano staging temporaneo.

```text
archive
  -> staging directory
  -> decode
  -> CRC/integrity
  -> metadata
  -> success
  -> publish
```

In caso di:

- cancellation;
- corruption;
- I/O failure;

la destinazione originale resta intatta.

Qualification: run `37237322025` PASS Linux/Windows.

---

# 15. API di ispezione e selective extraction

Sono tutte implementate in RC1:

```text
kephir2_inspect
kephir2_list_entries
kephir2_test_archive
kephir2_extract_selected
```

Non sono più API “future” o “required”.

Flusso UI raccomandato:

```text
open archive
 -> inspect
 -> list entries
 -> show metadata/tree
 -> extract all OR extract selected
```

`kephir2_test_archive()` è il percorso di verifica profonda e può essere più costoso di inspect/list.

---

# 16. UTF-8 e path safety

Tutti i path della C API sono UTF-8.

Su Windows non usare code page ANSI.

Il motore applica path safety per impedire:

- `../` traversal;
- path assoluti malevoli;
- uscita dalla destination root;
- target non sicuri.

AURORA deve comunque gestire UX e messaggi di errore.

---

# 17. KEPHIR2 core congelato

La linea RC1 include la policy adaptive-context production-safe:

- bounded content sampling;
- context 512 KiB / 4 MiB / 8 MiB;
- structural-volatility safety gate;
- long-context AUTO layout bootstrap;
- parametri necessari al decode auto-descritti nel NativeK75 stream.

La GUI non conosce questi dettagli.

Restano research-only e NON sono promossi in RC1:

- EXP-118B Python bounded grain-probe router;
- EXP-120A mixed parent-grain oracle;
- grain2 sperimentale;
- mixed-grain per-superchunk;
- EXP-121 e successive linee evolutive.

Questa conoscenza viene conservata per KEPHIR3.

---

# 18. Performance reference

## Silesia codec line

Baseline di ricerca migliore mantenuta come riferimento:

```text
Silesia raw:                  211,938,580 bytes
EXP-118B baseline:             60,963,390 bytes
Ratio:                         28.764649645%
External pinned corpus:         4,792,947 bytes
External ratio:                ~27.83076%
```

Numeri codec comparabili precedenti:

```text
full compression with probing: ~4.16 MB/s
final encode excluding probe:  ~6.77 MB/s
decode:                        ~82.3 MB/s
```

Non si continua a ottimizzare ratio/speed in KEPHIR2 salvo bug.

## AUR2 public/container scale path

Fixture ~64 MiB:

```text
encode:   ~32.67 MiB/s
decode:   ~277.18 MiB/s
peak RAM encode: ~106.15 MiB
peak RAM decode: ~43.66 MiB
SHA round-trip: PASS
```

Questi dati misurano il percorso pubblico/container e non sono equivalenti alle prestazioni Silesia del codec.

Scale run: `37238274255` PASS.

---

# 19. Qualification già completata

Checkpoint verificati:

```text
AUR2 final Linux/Windows gate       37238651446 PASS
AUR2 scale qualification            37238274255 PASS
Transactional extraction            37237322025 PASS Linux/Windows
Multi-stream progress               37237913015 PASS Linux/Windows
File-backed finalizer               36917547860 PASS Linux/Windows
Public writer                       36918208737 PASS Linux/Windows
RC1 base freeze qualification       37266002327 PASS Linux/Windows
RC1 SDK package/consumer gate       37271671809 PASS Linux/Windows
```

Il gate SDK `37271671809` include su Windows:

- build Release;
- test suite;
- staging SDK;
- `find_package(Kephir2 CONFIG REQUIRED)` da progetto consumer separato;
- linking `Kephir2::kephir2`;
- runtime DLL loading;
- API version check;
- runtime version `2.0.0-rc1` check;
- create/destroy engine;
- artifact upload.

Non dichiarare PASS per un run ancora in esecuzione.

---

# 20. SDK di integrazione RC1

Layout Windows x64:

```text
kephir2-sdk-2.0.0-rc1-windows-x64/
  include/
    kephir2/
      kephir2_c.h
  bin/
    kephir2_api.dll
  lib/
    kephir2_api.lib
  cmake/
    Kephir2Config.cmake
  docs/
    KEPHIR2_AUR2_RC1_FREEZE_MANIFEST.md
    AURORA_KEPHIR2_INTEGRATION_CHECKLIST.md
    AUR2_CONTAINER_FORMAT.md
    AUR2_IMPLEMENTATION_STATUS.md
  VERSION
  SHA256SUMS
```

CMake:

```cmake
find_package(Kephir2 CONFIG REQUIRED)
target_link_libraries(AURORA PRIVATE Kephir2::kephir2)
```

Il package config è relocatable rispetto alla root SDK.

L'app installata non dipende da Python.

Python è attualmente richiesto soltanto durante il source build del repository per generare una parte nativa del backend. Nessun runtime Python, script R&D o corpus deve essere distribuito con AURORA.

---

# 21. CompressionService / KephirBackend

AURORA deve introdurre/adattare un wrapper applicativo, non chiamare la DLL direttamente dalla GUI.

Schema raccomandato:

```cpp
class ICompressionEngine {
public:
    virtual ~ICompressionEngine() = default;
    virtual CompressResult compress(...) = 0;
    virtual ExtractResult extract(...) = 0;
    virtual ArchiveInfo inspect(...) = 0;
    virtual TestResult test(...) = 0;
};
```

Migrazione:

```text
LegacyCompressionEngine
Kephir2CompressionEngine
```

`Kephir2CompressionEngine` deve contenere solo mapping verso la C ABI.

---

# 22. Mapping ProgressManager

Mapping raccomandato:

| KEPHIR | AURORA |
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

Le callback possono arrivare fuori dal thread GUI: usare l'event system/dispatcher dell'applicazione.

---

# 23. Engine lifetime e concorrenza

Modello raccomandato per RC1:

- un `kephir2_engine*` per job attivo, oppure servizio serializzato;
- non avviare due operazioni mutanti contemporanee sulla stessa handle;
- istanze separate possono essere gestite indipendentemente;
- distruggere sempre con `kephir2_destroy()`;
- non fare reentrancy sullo stesso engine dentro callback progress/cancel.

---

# 24. Error mapping AURORA

Mapping UI raccomandato:

```text
OK                  -> successo
CANCELLED           -> annullato
INVALID_ARGUMENT    -> parametri non validi
INPUT_NOT_FOUND     -> origine non trovata
OUTPUT_EXISTS       -> richiesta overwrite
IO_ERROR            -> errore filesystem/I/O
UNSUPPORTED_ARCHIVE -> formato/versione non supportata
CORRUPT_ARCHIVE     -> archivio danneggiato
INTEGRITY_ERROR     -> verifica integrità fallita
BACKEND_UNAVAILABLE -> backend non disponibile
INTERNAL_ERROR      -> errore interno inatteso
```

Non fare branching sul contenuto inglese di `message[512]`.

---

# 25. Legacy compatibility

KEPHIR2 RC1 dichiara e testa almeno:

```text
KPF1_LEGACY_READ
```

Questo non equivale automaticamente alla compatibilità completa con ogni archivio AUR1 prodotto dalla precedente applicazione AURORA.

Durante la migrazione applicativa:

1. mantenere il reader KEPHIR1/AUR1 esistente;
2. identificare fixture reali AUR1 dell'app;
3. aprire/estrarre tali fixture attraverso AURORA;
4. confrontare contenuto e metadata necessari;
5. solo dopo decidere se il vecchio reader può essere eliminato.

Nuove scritture devono andare a KEPHIR2/AUR2 una volta superato il gate applicativo.

---

# 26. Installer

Distribuzione minima runtime Windows:

```text
AURORA.exe
kephir2_api.dll
```

Il `.lib`, header, CMake config e documentazione servono allo sviluppo, non al runtime utente.

L'installer deve inoltre includere il runtime MSVC corretto se richiesto dal tipo di build scelto.

Non installare:

```text
research/
benchmarks/
tests/
Python
EXP scripts
generatori
corpus
GitHub workflow files
```

---

# 27. Test obbligatori nell'app AURORA

Prima di rendere KEPHIR2 il default writer, eseguire tramite l'EXE reale:

- startup API/version/capability negotiation;
- compressione file;
- compressione directory;
- file vuoto;
- directory vuota;
- directory mixed;
- nomi Unicode;
- long Windows paths;
- overwrite deny/allow;
- progress GUI monotono;
- cancellation durante compressione;
- cancellation durante estrazione;
- corruption handling;
- inspect;
- list entries;
- selective extraction;
- test archive;
- riapertura AUR2 dopo restart applicazione;
- compatibilità fixture AUR1/KEPHIR1;
- clean-machine installer test;
- uninstall/reinstall test.

I test core già verdi non sostituiscono questi test end-to-end applicativi.

---

# 28. API-gap rule durante l'integrazione

Se l'integrazione AURORA scopre un'operazione mancante:

1. non bypassare la DLL chiamando classi C++ interne;
2. documentare il caso d'uso reale;
3. preferire una nuova funzione/struct versionata additive e ABI-compatible;
4. aggiungere test core e consumer;
5. ricostruire SDK;
6. aggiornare freeze manifest e questa specifica;
7. rifare qualification Linux/Windows.

Una breaking change viene rinviata a KEPHIR3/AUR3 salvo necessità di sicurezza o prevenzione perdita dati.

---

# 29. Cosa NON esporre alla GUI

Non creare impostazioni UI per:

```text
K75
EXP number
grain size
parent grain
inner context
probe budget
router mode
transform id
match finder
entropy coder
research toggles
factory/research internals
```

La GUI conosce solo:

```text
AUTO / FAST / BALANCED / MAX
workers
integrity verification
overwrite
progress
cancel
archive info
entry list
extract all / selected
test archive
```

---

# 30. Freeze manifest e checklist operativa

Sul ramo RC1, i documenti operativi sono:

```text
docs/integration/KEPHIR2_AUR2_RC1_FREEZE_MANIFEST.md
docs/integration/AURORA_KEPHIR2_INTEGRATION_CHECKLIST.md
```

Questi documenti, il public header e l'SDK generato sono la base dell'integrazione.

---

# 31. Sequenza di migrazione raccomandata

```text
1. acquisire SDK RC1 qualificato
2. aggiungere Kephir2Backend a CompressionService
3. caricare/linkare kephir2_api.dll
4. verificare API version/capabilities
5. mappare options/profiles
6. mappare progress/cancel
7. implementare compress
8. implementare inspect/list/test
9. implementare extract all/selected
10. mantenere LegacyBackend attivo
11. eseguire test end-to-end AURORA
12. verificare fixture AUR1 reali
13. correggere solo bug/API gap reali
14. rendere KEPHIR2/AUR2 default writer
15. creare installer
16. clean-machine qualification
17. release AURORA
18. promuovere KEPHIR 2.0 / AUR2 final
19. solo dopo aprire KEPHIR3/AUR3
```

---

# 32. Release gate finale

La release KEPHIR2/AUR2 non passa da RC1 a final finché non sono veri tutti i seguenti punti:

```text
KEPHIR2 RC qualification PASS
AUR2 qualification PASS
SDK consumer qualification PASS
AURORA integration PASS
legacy application compatibility PASS
clean-machine installer PASS
AURORA release candidate PASS
```

Il core RC1 è qualificato; l'integrazione applicativa e l'installer restano il prossimo gate.

---

# 33. Source of Truth

Per l'integrazione usare esclusivamente:

```text
release/kephir-2.0-aur2-integration-rc1
src/kephir2/include/kephir2/kephir2_c.h
src/kephir2/cmake/Kephir2Config.cmake
docs/architecture/AUR2_CONTAINER_FORMAT.md
docs/architecture/AUR2_IMPLEMENTATION_STATUS.md
docs/integration/KEPHIR2_AUR2_RC1_FREEZE_MANIFEST.md
docs/integration/AURORA_KEPHIR2_INTEGRATION_CHECKLIST.md
RC1 SDK artifact
```

Non integrare direttamente da `research/*`.

---

# 34. Stato al freeze

**KEPHIR2/AUR2:** feature freeze attivo.  
**AUR2:** implementato e qualificato.  
**C ABI v1:** congelata per integrazione.  
**Runtime RC:** `2.0.0-rc1`.  
**SDK Windows x64:** packaging e consumer CMake qualificati.  
**KEPHIR3/AUR3:** non iniziati.  
**Prossima attività di prodotto:** integrazione dentro AURORA Compressor, test end-to-end e installer.
