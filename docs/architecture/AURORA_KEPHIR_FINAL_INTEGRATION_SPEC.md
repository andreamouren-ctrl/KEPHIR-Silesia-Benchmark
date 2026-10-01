# AURORA / KEPHIR — Specifica tecnica completa per integrazione finale

**Documento:** Integration & Technology Handoff Specification  
**Progetto:** AURORA Compressor / KEPHIR  
**Scopo:** fornire a chi integrerà il motore KEPHIR dentro AURORA tutte le informazioni necessarie senza dover ricostruire la storia R&D del progetto.  
**Data snapshot:** 2026-10-01  
**Stato:** **HANDOFF MASTER — da aggiornare e congelare alla Release Candidate finale**

> **Regola fondamentale:** AURORA non deve dipendere da file `research/`, numeri EXP, script Python sperimentali, layout temporanei o dettagli interni del backend. L'applicazione deve integrare KEPHIR esclusivamente attraverso una **C ABI versionata e stabile**, preferibilmente distribuita come DLL + import library + header pubblico.

---

# 1. Obiettivo del documento

Questo file deve essere consegnato al programmatore, all'IA o al sistema che effettuerà l'integrazione finale del compressore dentro l'applicazione AURORA.

Definisce:

- architettura generale AURORA ↔ KEPHIR;
- responsabilità dell'applicazione e del motore;
- tecnologie usate nel motore;
- tecnologie encoder-only e decoder-required;
- formato archivio attuale e direzione del container `.aur`;
- API pubblica già esistente;
- API che devono esistere prima della sostituzione definitiva del vecchio motore;
- gestione profili, progresso, cancellazione ed errori;
- compatibilità e sicurezza di estrazione;
- regole ABI;
- struttura del pacchetto SDK;
- integrazione CMake/Windows;
- integrazione con `ProgressManager`, `JobManager` e GUI;
- test obbligatori e checklist finale di migrazione.

---

# 2. Legenda dello stato

| Stato | Significato |
|---|---|
| **IMPLEMENTED** | presente nel core o nella linea nativa corrente |
| **VALIDATED** | implementata e validata tramite test/CI/roundtrip |
| **PROMOTED** | ricerca accettata come direzione di prodotto |
| **R&D** | presente nella linea sperimentale, non ancora contratto stabile |
| **REQUIRED** | necessaria prima dell'integrazione finale |
| **PLANNED** | prevista ma non ancora parte del core qualificato |
| **LEGACY** | esiste per compatibilità con la linea precedente |
| **DO NOT EXPOSE** | dettaglio interno che non deve arrivare alla GUI/API pubblica |

---

# 3. Architettura di integrazione

```text
┌───────────────────────────────────────────────┐
│                 AURORA.exe                    │
│                                               │
│  GUI                                          │
│   │                                           │
│   ├── JobManager                              │
│   ├── ProgressManager                         │
│   ├── Settings                                │
│   └── CompressionService                      │
│              │                                │
│              ▼                                │
│       KephirBackend Adapter                   │
└──────────────┬────────────────────────────────┘
               │ C ABI stabile
               ▼
┌───────────────────────────────────────────────┐
│              kephir2.dll                      │
│                                               │
│  Public C API                                 │
│       ↓                                       │
│  Content Analyzer                             │
│       ↓                                       │
│  Global Strategy Router                       │
│       ↓                                       │
│  Compression Planner                          │
│       ↓                                       │
│  Directory Packing                            │
│       ↓                                       │
│  Scheduler / Execution                        │
│       ↓                                       │
│  KEPHIR Native Backend                        │
│       ↓                                       │
│  Archive / Integrity Layer                    │
└───────────────────────────────────────────────┘
```

La GUI **non deve** scegliere transform interni, conoscere EXP, implementare il router AUTO, replicare regole di grain/context, leggere Factory Knowledge o interpretare direttamente i blocchi compressi.

La GUI deve conoscere solo concetti di prodotto:

```text
AUTO
FAST
BALANCED
MAX
workers opzionali
verifica integrità
overwrite
progresso
cancellazione
informazioni archivio
lista file
estrazione
verifica/test archivio
```

---

# 4. Responsabilità

## 4.1 AURORA possiede

- selezione file/cartelle;
- destinazione output;
- conferma overwrite;
- GUI;
- gestione job;
- cronologia;
- notifiche;
- progress bar;
- pulsante annulla;
- preferenze utente;
- scelta profilo;
- visualizzazione statistiche;
- associazione file `.aur`;
- eventuale UI password/sicurezza.

## 4.2 KEPHIR possiede

- scansione input;
- analisi contenuto;
- classificazione content-first;
- scelta AUTO;
- layout directory;
- grain/context;
- transform;
- scheduling;
- compressione/decompressione;
- framing archivio;
- manifest;
- verifica integrità;
- path-safety;
- conteggi byte;
- backend;
- compatibilità stream;
- progress tecnico;
- cancellazione cooperativa.

---

# 5. Tecnologie KEPHIR

## 5.1 Compressione lossless general-purpose

**Stato:** IMPLEMENTED / VALIDATED

Requisito assoluto:

```text
SHA256(originale) == SHA256(estratto)
```

Nessuna modalità general-purpose può introdurre perdita.

## 5.2 Native Content Analyzer

**Stato:** IMPLEMENTED / VALIDATED

Analizza il contenuto indipendentemente dall'estensione del file.

Metriche principali:

- file count;
- logical bytes;
- average file size;
- median file size;
- small-file fraction;
- sampled entropy;
- printable fraction;
- zero fraction;
- content family count;
- dominant file-family fraction;
- dominant byte-family fraction;
- repeatable-content fraction;
- segnali strutturali relativi alla segmentazione.

Classi content-first della linea nativa:

```text
empty
tiny-text
tiny-binary
encoded-text
text-code
text-config
text-prose
text-generic
binary-zero
binary-low
binary-mid
binary-high
```

**DO NOT EXPOSE:** la GUI non deve dipendere da queste classi.

## 5.3 Global Strategy Router

**Stato:** IMPLEMENTED / PROMOTED

Profili pubblici:

```text
AUTO
FAST
BALANCED
MAX
```

Layout interni:

```text
FLAT
SMART
HYBRID
```

`HYBRID` non va assunto disponibile dalla GUI finché non viene dichiarato capability stabile.

## 5.4 AUTO routing

**Stato:** IMPLEMENTED / R&D evolutivo

AUTO può usare:

- metriche del Content Analyzer;
- probe limitati;
- confronto SMART/FLAT;
- rappresentatività del campione;
- diversità contenuto;
- volatilità strutturale;
- bounded sampling;
- criteri zero-regret/zero-harm dove validati.

L'implementazione interna può cambiare senza cambiare l'API.

## 5.5 Compression Planner

**Stato:** IMPLEMENTED

```text
Input
  ↓
ContentAnalyzer
  ↓
ArchiveFeatures
  ↓
GlobalRouter
  ↓
StrategyPlan
  ↓
Execution
```

---

# 6. Directory Packing

## 6.1 FLAT

**Stato:** IMPLEMENTED

Ordine lineare dei file.

## 6.2 SMART

**Stato:** IMPLEMENTED / VALIDATED

Raggruppamento content-first per aumentare similarità locale e ridurre confini sfavorevoli.

## 6.3 PackedGroupSource / PackedGroupSink

**Stato:** IMPLEMENTED

Astrazioni per leggere/scrivere gruppi logici senza imporre alla GUI il layout fisico interno.

---

# 7. Adaptive Grain e Context

**Stato:** PROMOTED / R&D evolutivo

Dimensioni studiate includono:

```text
512 KiB
4 MiB
8 MiB
```

La ricerca comprende:

- adaptive grain;
- parent grain;
- inner context esteso;
- selezione mediante probe;
- segnali di distribuzione/volatilità.

**Regola API:** parent grain, inner chunk e controlli di ricerca non devono essere esposti nella ABI di prodotto salvo futura decisione esplicita.

---

# 8. Structural Transforms

Transform reversibili presenti nella lineage KEPHIR 2:

```text
Base
Delta2 + Transpose2
Delta4 + Transpose4
Delta16 + Transpose16
Delta1024 + Transpose1024
WordXor16 + Transpose2
TextToken
```

Il decoder deve sempre ricavare dal bitstream tutto ciò che serve per invertire il transform.

La GUI non seleziona questi transform.

---

# 9. Word-XOR

**Stato:** PROMOTED

Lineage sviluppata:

- Word-XOR;
- predictive Word-XOR;
- lazy Word-XOR;
- fingerprint-aware selection.

È una decisione encoder/backend interna.

---

# 10. TextToken

**Stato:** R&D / strategia interna

Trasformazione specializzata per contenuti testuali/tokenizzabili.

Non deve essere necessariamente esposta come opzione utente.

---

# 11. Backend nativo

## 11.1 CompressionBackend

**Stato:** IMPLEMENTED abstraction

```text
ByteSource
    ↓
CompressionBackend::encode()
    ↓
CompressedBlob

CompressedBlob
    ↓
CompressionBackend::decode()
    ↓
ByteSink
```

## 11.2 ByteSource

```cpp
virtual uint64_t size() const noexcept = 0;
virtual size_t read(
    uint64_t offset,
    std::span<uint8_t> destination) const = 0;
```

## 11.3 ByteSink

```cpp
virtual void write(
    uint64_t offset,
    std::span<const uint8_t> source) = 0;
```

Queste astrazioni servono per large file, directory packing, streaming progressivo e riduzione della materializzazione in RAM.

---

# 12. Native K75 Backend

**Stato:** IMPLEMENTED / R&D production candidate

Caratteristiche:

- stream lossless;
- grain/context adattivi;
- transform reversibili;
- parallel encode/decode in evoluzione;
- decoder indipendente dal router;
- blob auto-descrivente per i parametri necessari.

**DO NOT EXPOSE:** `K75` non deve diventare un nome richiesto dalla GUI.

---

# 13. Prediction ed Entropy Coding

La lineage KEPHIR comprende:

- predictive parsing;
- LZ/dictionary matching;
- residual coding;
- probability modelling adattivo;
- arithmetic coding 32-bit;
- quantizzazione di probabilità;
- trasformazioni strutturali pre-coding.

Sono dettagli del backend.

L'outer container `.aur` deve evitarne la duplicazione quando il payload KEPHIR è già auto-descrivente.

---

# 14. Scheduling e Parallelismo

Tecnologie:

- cost-aware scheduling;
- work parcels;
- worker selection;
- parallel encoder;
- parallel decoder;
- bounded worker count;
- metriche worker utilizzati.

La GUI può offrire:

```text
Workers = AUTO
Workers = N
```

`0` nell'API significa **AUTO**.

---

# 15. Factory Knowledge / Local Experience

## Factory Knowledge

**Stato:** IMPLEMENTED nella linea qualificata KEPHIR 1.x; concetto mantenuto.

Conoscenza read-only distribuita con il prodotto.

## Local Experience

**Stato:** opzionale / encoder-only

Persistenza locale di esperienza.

Regola assoluta:

> Un archivio deve essere decodificabile senza Factory Knowledge e senza Local Experience.

---

# 16. Integrità

Requisiti:

- exact roundtrip;
- checksum/CRC a livello appropriato;
- validazione lunghezze;
- corruption rejection;
- verifica opzionale post-compressione;
- SHA nei test di qualification;
- nessuna eccezione C++ oltre la C ABI.

---

# 17. Sicurezza di estrazione

**REQUIRED**

Bloccare:

- `../`;
- path traversal;
- path assoluti malevoli;
- uscita dalla destination root;
- collisioni non autorizzate;
- overwrite non consentito.

---

# 18. Formato KPF1 attuale

**Stato:** IMPLEMENTED / LEGACY-COMPATIBLE INTERNAL FORMAT

Concetti:

```text
KPF1 File Envelope
KPF1 Directory Envelope
Manifest
Groups
Compressed blobs
Varint
Safe archive target
```

Manifest record:

```text
path
group_id
size
```

Directory envelope:

```text
group_names
manifest
groups[]
```

---

# 19. `.aur` e KPF non devono essere confusi

Raccomandazione:

```text
.aur = container di prodotto AURORA
KPF/KEPHIR stream = payload/codec format interno
```

Il container AURORA deve poter evolvere più lentamente del codec.

```text
AUR Container 2
 ├── KEPHIR 2.0
 ├── KEPHIR 2.1
 ├── KEPHIR 2.8
 └── KEPHIR 3.x
```

---

# 20. AUR Container v2 — Specifica proposta

**Stato:** REQUIRED / DRAFT DA CONGELARE PRIMA DELLA RELEASE

Obiettivi:

- versionato;
- little-endian;
- auto-descrivente;
- estensibile;
- 64-bit clean;
- adatto a file grandi e directory;
- capace di sezioni opzionali;
- sicuro da ispezionare prima dell'estrazione;
- capace di dichiarare feature obbligatorie.

## 20.1 Magic

Proposta:

```text
41 55 52 32 0D 0A 1A 0A
```

ovvero:

```text
"AUR2\r\n\x1A\n"
```

## 20.2 Fixed Header — 64 byte

| Offset | Size | Campo | Tipo |
|---:|---:|---|---|
| 0 | 8 | magic | bytes |
| 8 | 2 | container_major | uint16 LE |
| 10 | 2 | container_minor | uint16 LE |
| 12 | 4 | header_size | uint32 LE |
| 16 | 8 | feature_flags | uint64 LE |
| 24 | 8 | archive_id | uint64 LE |
| 32 | 8 | logical_size | uint64 LE |
| 40 | 8 | toc_offset | uint64 LE |
| 48 | 8 | footer_offset | uint64 LE |
| 56 | 4 | header_crc32 | uint32 LE |
| 60 | 4 | reserved | uint32 LE |

Regole:

- `header_size >= 64`;
- major incompatibile → rifiuto;
- minor più recente accettabile solo senza feature obbligatorie sconosciute;
- `reserved = 0` in scrittura;
- serializzazione esplicita campo per campo, mai `fwrite(sizeof(struct))`.

---

# 21. AUR2 — Sezioni TLV

Header sezione:

| Campo | Tipo |
|---|---|
| type | uint32 LE |
| flags | uint32 LE |
| payload_length | uint64 LE |

Tipi iniziali proposti:

```text
0x0001 FILE_TABLE
0x0002 CODEC_DESCRIPTOR
0x0003 BLOCK_TABLE
0x0004 DATA
0x0005 INTEGRITY
0x0006 ENCRYPTION
0x0007 RECOVERY
0x0008 SEEK_INDEX
0x0009 EXTENDED_METADATA
0x000A USER_METADATA
```

Sezione sconosciuta:

- `IGNORABLE` → reader può saltarla;
- `REQUIRED` → `UNSUPPORTED_ARCHIVE`.

---

# 22. Feature Flags AUR2

Proposta:

```text
AUR_FEATURE_DIRECTORY
AUR_FEATURE_MULTISTREAM
AUR_FEATURE_INTEGRITY
AUR_FEATURE_SEEK_INDEX
AUR_FEATURE_ENCRYPTION
AUR_FEATURE_RECOVERY
AUR_FEATURE_EXTENDED_METADATA
AUR_FEATURE_KEPHIR2
AUR_FEATURE_LEGACY_PAYLOAD
```

I bit number devono essere congelati prima della release.

Una volta pubblicato, un bit non cambia significato.

---

# 23. Codec Descriptor

Deve contenere almeno:

```text
codec_id
codec_major
codec_minor
minimum_decoder_major
minimum_decoder_minor
codec_flags
codec_private_data_length
codec_private_data
```

Esempio:

```text
codec_id = KEPHIR
codec_major = 2
codec_minor = 0
```

Il container non deve replicare dettagli KEPHIR già presenti nel payload.

---

# 24. File Table

Ogni entry dovrebbe descrivere:

```text
entry_id
parent_id / path
entry_type
logical_size
stream_id
stream_offset
attributes
mtime
optional checksum
optional permissions
```

Tipi iniziali:

```text
FILE
DIRECTORY
```

Symlink solo dopo design e test di sicurezza espliciti.

---

# 25. Block / Stream Table

Campi raccomandati:

```text
stream_id
file/group owner
payload_offset
compressed_size
raw_size
codec_id
codec_flags
integrity_ref
```

Informazioni come Delta4, WordXor, parent grain, inner context e modello aritmetico devono preferibilmente restare nel payload KEPHIR.

---

# 26. Integrity Section

Può contenere:

- CRC32 header/section;
- checksum per stream;
- hash file opzionale;
- hash globale opzionale.

La qualification può continuare a usare SHA-256 anche se il runtime usa checksum più leggeri.

---

# 27. Encryption Section

**Stato:** PLANNED, NON ASSUMERE IMPLEMENTATA

Il container deve poter aggiungere in futuro:

- authenticated encryption;
- KDF parametrica;
- salt;
- nonce/IV;
- key slot;
- encrypted metadata opzionale;
- autenticazione prima dell'estrazione.

La C API sicurezza dovrà essere una estensione separata.

---

# 28. Recovery Section

**Stato:** PLANNED

Possibili dati:

- recovery points;
- segment CRC;
- parity/redundancy future;
- restart points.

---

# 29. Seek Index

**Stato:** PLANNED / utile per large archive

Permette:

- listing veloce;
- estrazione selettiva;
- accesso diretto;
- apertura senza scansione completa del payload.

---

# 30. Compatibilità AUR1 / AUR2

```text
if AUR1:
    LegacyContainerReader
elif AUR2:
    Aur2Reader
else:
    UnsupportedArchive
```

Non eliminare il decoder legacy finché gli archivi storici devono restare apribili.

---

# 31. Versioni da separare

Servono almeno:

```text
Application Version
AUR Container Version
KEPHIR API Version
KEPHIR Engine Version
KEPHIR Stream/Codec Version
```

Esempio:

```text
AURORA App:      1.4.0
AUR Container:  2.0
KEPHIR API:      1
KEPHIR Engine:   2.3.0
KEPHIR Stream:   2
```

---

# 32. C ABI pubblica esistente

La linea nativa corrente contiene:

```c
#define KEPHIR2_API_VERSION 1u
```

Opaque handle:

```c
typedef struct kephir2_engine kephir2_engine;
```

Funzioni correnti:

```c
uint32_t kephir2_api_version(void);
const char* kephir2_engine_version(void);

kephir2_engine* kephir2_create(void);
void kephir2_destroy(kephir2_engine* engine);

kephir2_status kephir2_compress(
    kephir2_engine* engine,
    const char* input_utf8,
    const char* output_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);

kephir2_status kephir2_extract(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);

const char* kephir2_status_name(kephir2_status status);
```

---

# 33. Status Code esistenti

```c
typedef enum kephir2_status {
    KEPHIR2_OK = 0,
    KEPHIR2_CANCELLED = 1,
    KEPHIR2_INVALID_ARGUMENT = 2,
    KEPHIR2_INPUT_NOT_FOUND = 3,
    KEPHIR2_OUTPUT_EXISTS = 4,
    KEPHIR2_IO_ERROR = 5,
    KEPHIR2_UNSUPPORTED_ARCHIVE = 6,
    KEPHIR2_CORRUPT_ARCHIVE = 7,
    KEPHIR2_INTEGRITY_ERROR = 8,
    KEPHIR2_BACKEND_UNAVAILABLE = 9,
    KEPHIR2_INTERNAL_ERROR = 10
} kephir2_status;
```

Una volta pubblicati non vanno rinumerati.

Possibili estensioni future:

```text
KEPHIR2_PASSWORD_REQUIRED
KEPHIR2_AUTHENTICATION_FAILED
KEPHIR2_UNSUPPORTED_FEATURE
KEPHIR2_VERSION_TOO_NEW
KEPHIR2_PERMISSION_DENIED
KEPHIR2_DISK_FULL
```

---

# 34. Profili pubblici

```c
typedef enum kephir2_profile {
    KEPHIR2_PROFILE_AUTO = 0,
    KEPHIR2_PROFILE_FAST = 1,
    KEPHIR2_PROFILE_BALANCED = 2,
    KEPHIR2_PROFILE_MAX = 3
} kephir2_profile;
```

La GUI non hard-coda parametri interni per i profili.

---

# 35. Progress Phases pubbliche

```c
typedef enum kephir2_phase {
    KEPHIR2_PHASE_IDLE = 0,
    KEPHIR2_PHASE_SCANNING = 1,
    KEPHIR2_PHASE_ANALYZING = 2,
    KEPHIR2_PHASE_PLANNING = 3,
    KEPHIR2_PHASE_PACKING = 4,
    KEPHIR2_PHASE_COMPRESSING = 5,
    KEPHIR2_PHASE_WRITING = 6,
    KEPHIR2_PHASE_VERIFYING = 7,
    KEPHIR2_PHASE_EXTRACTING = 8,
    KEPHIR2_PHASE_DONE = 9
} kephir2_phase;
```

Queste fasi sono il contratto GUI. L'implementazione interna può cambiare.

---

# 36. Progress Callback

```c
typedef struct kephir2_progress_v1 {
    uint32_t struct_size;
    kephir2_phase phase;
    double fraction;
    uint64_t processed_bytes;
    uint64_t total_bytes;
    const char* current_path_utf8;
} kephir2_progress_v1;
```

```c
typedef void (*kephir2_progress_callback)(
    const kephir2_progress_v1* progress,
    void* user_data);
```

Regole:

- `fraction` in `[0,1]`;
- può non essere lineare fra fasi;
- `current_path_utf8` è valido durante la callback salvo contratto diverso;
- callback breve e non bloccante;
- la GUI deve fare marshal sul UI thread;
- il motore può chiamare da worker thread.

---

# 37. Cancellation Callback

```c
typedef int (*kephir2_cancel_callback)(void* user_data);
```

Semantica:

```text
0 = continua
!= 0 = richiedi cancellazione
```

La cancellazione deve essere cooperativa e non lasciare un archivio apparentemente valido ma parziale.

---

# 38. Options v1 esistenti

```c
typedef struct kephir2_options_v1 {
    uint32_t struct_size;
    kephir2_profile profile;
    uint32_t workers;
    int verify_integrity;
    int overwrite_output;
    int allow_local_experience;
    kephir2_progress_callback progress_callback;
    kephir2_cancel_callback cancel_callback;
    void* user_data;
} kephir2_options_v1;
```

Default raccomandati:

```text
profile                = AUTO
workers                = 0 (AUTO)
verify_integrity       = 1
overwrite_output       = 0
allow_local_experience = 1 se consentito dalle impostazioni
callbacks              = NULL
user_data              = NULL
```

---

# 39. Result v1 esistente

```c
typedef struct kephir2_result_v1 {
    uint32_t struct_size;
    kephir2_status status;
    uint64_t input_bytes;
    uint64_t output_bytes;
    double elapsed_seconds;
    char message[512];
} kephir2_result_v1;
```

Regole:

- byte count sempre corretti;
- `message` sempre NUL-terminated;
- `message` è diagnostico e non va parsato;
- la logica usa `status`.

---

# 40. Versioning delle Struct

Ogni struct pubblica usa:

```c
uint32_t struct_size;
```

Il chiamante:

```c
kephir2_options_v1 opt = {0};
opt.struct_size = sizeof(opt);
```

Non modificare layout dei campi già pubblicati.

---

# 41. API REQUIRED prima dell'integrazione finale

## 41.1 Default Options

```c
KEPHIR2_API void kephir2_options_init_v1(
    kephir2_options_v1* options);
```

Motivo: evitare che ogni host ricrei i default.

## 41.2 Capability Query

```c
typedef struct kephir2_capabilities_v1 {
    uint32_t struct_size;
    uint32_t api_version;
    uint32_t engine_major;
    uint32_t engine_minor;
    uint32_t engine_patch;
    uint64_t feature_flags;
    uint32_t max_workers;
    uint32_t reserved0;
} kephir2_capabilities_v1;

KEPHIR2_API kephir2_status kephir2_get_capabilities(
    kephir2_engine* engine,
    kephir2_capabilities_v1* caps);
```

Capability possibili:

```text
COMPRESS_FILE
COMPRESS_DIRECTORY
EXTRACT
INSPECT
LIST_ENTRIES
EXTRACT_SELECTED
TEST_ARCHIVE
AUR1_READ
AUR2_READ
AUR2_WRITE
KEPHIR_STREAM_V1_READ
KEPHIR_STREAM_V2_READ
ENCRYPTION
RECOVERY
SEEK_INDEX
```

---

# 42. API Inspect — REQUIRED

```c
typedef struct kephir2_archive_info_v1 {
    uint32_t struct_size;
    uint32_t container_major;
    uint32_t container_minor;
    uint32_t codec_major;
    uint32_t codec_minor;
    uint64_t feature_flags;
    uint64_t entry_count;
    uint64_t logical_bytes;
    uint64_t archive_bytes;
    int is_encrypted;
    int integrity_available;
    int integrity_verified;
    int reserved0;
} kephir2_archive_info_v1;

KEPHIR2_API kephir2_status kephir2_inspect(
    kephir2_engine* engine,
    const char* archive_utf8,
    kephir2_archive_info_v1* info);
```

La GUI usa questa API per mostrare dimensione, numero file, versioni e compatibilità prima dell'estrazione.

---

# 43. API Listing — REQUIRED

```c
typedef enum kephir2_entry_type {
    KEPHIR2_ENTRY_FILE = 0,
    KEPHIR2_ENTRY_DIRECTORY = 1
} kephir2_entry_type;

typedef struct kephir2_entry_info_v1 {
    uint32_t struct_size;
    uint64_t entry_id;
    kephir2_entry_type type;
    uint64_t logical_size;
    const char* path_utf8;
} kephir2_entry_info_v1;

typedef int (*kephir2_entry_callback)(
    const kephir2_entry_info_v1* entry,
    void* user_data);

KEPHIR2_API kephir2_status kephir2_list_entries(
    kephir2_engine* engine,
    const char* archive_utf8,
    kephir2_entry_callback callback,
    void* user_data);
```

Callback evita allocazioni ABI cross-module.

---

# 44. API Test Archive — REQUIRED

```c
KEPHIR2_API kephir2_status kephir2_test_archive(
    kephir2_engine* engine,
    const char* archive_utf8,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);
```

Deve verificare header, manifest, bounds, checksum, backend frames e integrità senza estrazione su disco.

---

# 45. API Selective Extraction — REQUIRED per UX completa

```c
typedef struct kephir2_selection_v1 {
    uint32_t struct_size;
    const uint64_t* entry_ids;
    size_t entry_count;
} kephir2_selection_v1;

KEPHIR2_API kephir2_status kephir2_extract_selected(
    kephir2_engine* engine,
    const char* archive_utf8,
    const char* output_directory_utf8,
    const kephir2_selection_v1* selection,
    const kephir2_options_v1* options,
    kephir2_result_v1* result);
```

Se non entra nella prima release, AURORA può inizialmente offrire solo “Estrai tutto”, ma la limitazione deve essere documentata.

---

# 46. Error Diagnostics

Possibile API:

```c
KEPHIR2_API const char* kephir2_last_error(
    kephir2_engine* engine);
```

Oppure mantenere solo `result.message`.

Non usare entrambi senza ownership/thread-safety chiara.

---

# 47. Feature Negotiation

Preferire `kephir2_inspect()` + status specifici invece di duplicare logica host-side.

L'host non deve dedurre compatibilità leggendo a mano il file.

---

# 48. API Password / Encryption

**NON inserire nella v1 fino a design sicurezza congelato.**

Quando necessaria, usare un'estensione versionata separata, non campi improvvisati dentro `kephir2_options_v1`.

---

# 49. Ownership della memoria

Regola:

> La memoria allocata da un modulo viene liberata dallo stesso modulo.

Preferire:

- buffer del chiamante;
- callback;
- opaque handle;
- fixed-size output structs.

Evitare `DLL malloc()` + `EXE free()`.

---

# 50. Encoding Stringhe

Tutte le API pubbliche usano UTF-8.

Su Windows la conversione UTF-8 → UTF-16 avviene nel layer nativo.

Supportare long path.

---

# 51. Thread Safety

Raccomandazione da congelare:

- una singola `kephir2_engine*` non esegue due operazioni mutanti contemporaneamente;
- istanze distinte possono lavorare in parallelo;
- version query thread-safe;
- callback possono arrivare dal thread operazione/worker;
- GUI mai aggiornata direttamente dalla callback.

---

# 52. Reentrancy Callback

Durante `progress_callback` non chiamare sulla stessa istanza:

```text
kephir2_compress
kephir2_extract
kephir2_destroy
```

Default sicuro: nessuna reentrancy sulla stessa handle.

---

# 53. Temporary Output / Atomicity

Compressione raccomandata:

```text
target.aur.partial
       ↓
compression
       ↓
integrity
       ↓
flush
       ↓
atomic rename
       ↓
target.aur
```

Errore/cancel → rimuovere `.partial`.

---

# 54. Overwrite Policy

`overwrite_output = 0`:

```text
output esiste → KEPHIR2_OUTPUT_EXISTS
```

`overwrite_output = 1`:

- replace sicuro;
- non distruggere il vecchio file prima che il nuovo sia valido quando possibile.

---

# 55. File e Directory

`kephir2_compress()` deve poter accettare sia file sia directory.

La GUI non deve mantenere due motori diversi.

---

# 56. Empty Directories

**REQUIRED**

Il container finale deve preservare directory vuote.

AUR2 FILE_TABLE deve rappresentarle esplicitamente.

---

# 57. Metadata

Minimo raccomandato:

```text
relative path
entry type
file size
mtime
directory existence
```

Possibili futuri:

```text
Windows attributes
permissions
creation time
ACL
alternate streams
symlink
```

Non dichiarare supporto se non testato.

---

# 58. Determinismo

Obiettivo raccomandato:

stesso input + stessa versione + stesso profilo + stesse options → output riproducibile, salvo campi esplicitamente non deterministici.

---

# 59. Pacchetto SDK finale

```text
kephir-sdk/
├── include/
│   └── kephir2/
│       └── kephir2_c.h
├── bin/
│   └── kephir2.dll
├── lib/
│   └── kephir2.lib
├── cmake/
│   └── Kephir2Config.cmake
├── licenses/
├── docs/
│   └── AURORA_KEPHIR_FINAL_INTEGRATION_SPEC.md
├── VERSION
└── SHA256SUMS
```

---

# 60. ABI Windows

Export macro corrente:

```c
#if defined(_WIN32) && defined(KEPHIR2_BUILD_DLL)
#  define KEPHIR2_API __declspec(dllexport)
#elif defined(_WIN32)
#  define KEPHIR2_API __declspec(dllimport)
#else
#  define KEPHIR2_API
#endif
```

Prima del freeze definire anche calling convention esplicita e non cambiarla.

---

# 61. CMake Integration

Ideale:

```cmake
find_package(Kephir2 CONFIG REQUIRED)
target_link_libraries(AURORA PRIVATE Kephir2::kephir2)
```

Fallback:

```cmake
target_include_directories(AURORA PRIVATE path/to/kephir-sdk/include)
target_link_libraries(AURORA PRIVATE path/to/kephir-sdk/lib/kephir2.lib)
```

---

# 62. Host Adapter C++

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

Migrazione temporanea:

```text
LegacyCompressionEngine
Kephir2CompressionEngine
```

Dopo field validation:

```text
Kephir2CompressionEngine
```

---

# 63. CompressionService

```text
GUI
 ↓
JobManager
 ↓
CompressionService
 ↓
Kephir2CompressionEngine
 ↓
kephir2.dll
```

La GUI non chiama direttamente `kephir2_*`.

---

# 64. Mapping ProgressManager

| KEPHIR | AURORA |
|---|---|
| SCANNING | Scansione |
| ANALYZING | Analisi |
| PLANNING | Pianificazione |
| PACKING | Preparazione archivio |
| COMPRESSING | Compressione |
| WRITING | Scrittura |
| VERIFYING | Verifica |
| EXTRACTING | Estrazione |
| DONE | Completato |

Mostrare se disponibili:

```text
phase
percentage
processed bytes
total bytes
current path
elapsed
throughput
```

---

# 65. Cancellation AURORA

```text
Cancel button
  ↓
atomic<bool> cancelRequested = true
  ↓
cancel_callback()
  ↓
KEPHIR2_CANCELLED
  ↓
JobManager = Cancelled
```

Non terminare brutalmente il thread.

---

# 66. Error Mapping GUI

```text
KEPHIR2_INVALID_ARGUMENT      → Parametri non validi
KEPHIR2_INPUT_NOT_FOUND       → Origine non trovata
KEPHIR2_OUTPUT_EXISTS         → Richiesta overwrite
KEPHIR2_IO_ERROR              → Errore I/O
KEPHIR2_UNSUPPORTED_ARCHIVE   → Formato/versione non supportata
KEPHIR2_CORRUPT_ARCHIVE       → Archivio danneggiato
KEPHIR2_INTEGRITY_ERROR       → Verifica integrità fallita
KEPHIR2_CANCELLED             → Operazione annullata
```

La localizzazione resta lato GUI.

---

# 67. Logging

La DLL non dovrebbe stampare direttamente su stdout/stderr in produzione.

Possibile callback futura di logging con livelli ERROR/WARNING/INFO/DEBUG/TRACE.

---

# 68. Metrics

Le metriche base sono già in `kephir2_result_v1`.

Possibile estensione futura:

```text
input_bytes
output_bytes
files_processed
elapsed_seconds
encode_seconds
verify_seconds
workers_used
```

Non esporre metriche R&D instabili nel contratto base.

---

# 69. Dynamic Loading opzionale

Per sostituire la DLL senza ricompilare AURORA:

```text
LoadLibraryW("kephir2.dll")
GetProcAddress(...)
```

Prima controllare `kephir2_api_version()`.

Per la prima release è accettabile linking tramite `.lib`.

---

# 70. API Compatibility Policy

Una minor/patch del motore può:

- correggere bug;
- migliorare ratio/speed;
- cambiare router;
- cambiare backend interno;
- aggiungere nuove API compatibili.

Non può:

- rinumerare enum pubblicati;
- cambiare semantica funzioni esistenti;
- cambiare ownership;
- cambiare calling convention;
- rimuovere simboli.

Breaking change → nuova API major.

---

# 71. Codec Compatibility Policy

```text
nuovo encoder → deve continuare a leggere stream vecchi supportati
vecchio decoder → non è obbligato a leggere stream nuovi
```

Il container dichiara la versione minima decoder.

---

# 72. Migration Plan

1. congelare `ICompressionEngine`;
2. integrare `kephir2.dll` accanto al legacy;
3. aggiungere engine selector developer-only;
4. testare compress/extract legacy vs KEPHIR2;
5. testare archivi storici;
6. testare directory grandi;
7. testare many-small-files;
8. testare file >4 GiB;
9. testare cancellation;
10. testare overwrite;
11. testare corruption;
12. testare path traversal;
13. testare progress GUI;
14. qualification;
15. impostare KEPHIR2 default;
16. mantenere legacy reader per almeno una release di compatibilità se necessario;
17. rimuovere legacy encoder solo dopo field validation.

---

# 73. Test obbligatori

## Core

- Windows x64 Release;
- C ABI load;
- version query;
- create/destroy ripetuto;
- file roundtrip;
- directory roundtrip;
- empty file;
- empty directory;
- Unicode path;
- long path;
- file >4 GiB;
- many small files;
- incompressible;
- zero-rich;
- large text;
- mixed directory.

## Concorrenza

- workers 1/2/4/8/16 se supportati;
- due engine distinti in parallelo;
- cancel sotto carico.

## Errori

- input mancante;
- output esistente;
- disco pieno simulato;
- destinazione read-only;
- archivio troncato;
- corruption payload/header/manifest;
- unsupported feature/version.

## Sicurezza

- `../evil`;
- absolute path;
- UTF-8 problematico;
- path collision;
- root escape.

## Compatibilità

- legacy;
- KPF1;
- AUR1;
- AUR2;
- inspect;
- list;
- extract selected;
- test archive.

---

# 74. Qualification Gate

Non sostituire il vecchio motore finché non sono verdi:

```text
Native file roundtrip
Native directory roundtrip
Extraction
Legacy compatibility
Container compatibility
Corruption rejection
Path traversal rejection
Cancellation
Progress callbacks
Worker stress
Large-file tests
Many-small-file tests
Application A/B integration
Benchmark matrix
Release Candidate soak
```

---

# 75. Benchmark Gate

Prima della release aggiornare questo documento con:

```text
Silesia ratio
Encode MB/s
Decode MB/s
Peak RAM
Worker scaling
External holdout
Competitor comparison
```

I confronti devono essere eseguiti nello stesso ambiente.

---

# 76. Performance Target di progetto

Target storici:

```text
Silesia ratio:        < 28%
Encode:               20–30 MB/s o più
Decode:               150–200 MB/s o più
Exact lossless:       obbligatorio
```

Sono target di sviluppo, non garanzie API.

---

# 77. Installazione

Pacchetto utente:

```text
AURORA.exe
kephir2.dll
```

Non installare:

```text
research/
Python
benchmark scripts
EXP files
test corpora
```

---

# 78. Aggiornamento motore

Se ABI v1 resta compatibile, AURORA può aggiornare principalmente `kephir2.dll`.

Prima dell'update verificare:

- API version;
- engine version;
- hash/signature pacchetto;
- compatibility tests.

---

# 79. Versioning SDK

Raccomandazione:

```text
KEPHIR Engine: MAJOR.MINOR.PATCH
KEPHIR API: integer major separato
```

API v1 resta `1` fino a breaking ABI.

---

# 80. C++ Wrapper opzionale

```cpp
class KephirEngine final {
public:
    KephirEngine();
    ~KephirEngine();

    CompressionResult compress(...);
    ExtractionResult extract(...);
    ArchiveInfo inspect(...);
    TestResult test(...);

private:
    kephir2_engine* handle_{nullptr};
};
```

Il wrapper chiama solo la C ABI.

---

# 81. Esempio compressione C

```c
kephir2_engine* engine = kephir2_create();
if (!engine) return;

kephir2_options_v1 options = {0};
options.struct_size = sizeof(options);
options.profile = KEPHIR2_PROFILE_AUTO;
options.workers = 0;
options.verify_integrity = 1;
options.overwrite_output = 0;
options.allow_local_experience = 1;
options.progress_callback = on_progress;
options.cancel_callback = should_cancel;
options.user_data = my_job;

kephir2_result_v1 result = {0};
result.struct_size = sizeof(result);

kephir2_status st = kephir2_compress(
    engine,
    "C:/data/input",
    "C:/data/archive.aur",
    &options,
    &result);

kephir2_destroy(engine);
```

---

# 82. Esempio ProgressManager

```cpp
static void kephirProgress(
    const kephir2_progress_v1* p,
    void* userData)
{
    auto* task = static_cast<ProgressTask*>(userData);

    ProgressUpdate u;
    u.phase = mapPhase(p->phase);
    u.fraction = p->fraction;
    u.processedBytes = p->processed_bytes;
    u.totalBytes = p->total_bytes;

    if (p->current_path_utf8)
        u.currentItem = p->current_path_utf8;

    task->post(u);
}
```

---

# 83. Esempio cancellazione

```cpp
static int kephirCancel(void* userData)
{
    auto* task = static_cast<ProgressTask*>(userData);
    return task->isCancellationRequested() ? 1 : 0;
}
```

---

# 84. Cosa NON copiare nel programma

```text
research/*
.github/workflows/*
benchmarks/*
tests/*
EXP*.py
router sperimentali Python
generatori
oracle
holdout corpus
```

L'applicazione deve ricevere il prodotto compilato/SDK.

---

# 85. Cosa integrare davvero

Minimo:

```text
kephir2.dll
kephir2.lib
kephir2_c.h
```

Più:

```text
CompressionService
Kephir2Backend adapter
Progress mapping
Error mapping
Installer rule
Compatibility tests
```

---

# 86. Audit prima del Freeze

Prima di dichiarare questo documento `FINAL`:

- confrontare header pubblico con `kephir2_c.h`;
- controllare simboli DLL esportati;
- testare ABI con host compilato separatamente;
- verificare `sizeof` struct;
- verificare calling convention;
- verificare UTF-8;
- verificare `output_bytes`;
- verificare defaults;
- verificare thread safety;
- verificare callback lifetime;
- verificare cancellation atomicity;
- verificare archive inspect;
- verificare AUR2 spec reale;
- sostituire ogni sezione DRAFT con FINAL oppure rimuoverla.

---

# 87. Source of Truth tecnico

Riferimenti principali:

```text
src/kephir2/include/kephir2/kephir2_c.h
src/kephir2/include/kephir2/operation.hpp
src/kephir2/include/kephir2/strategy.hpp
src/kephir2/include/kephir2/backend.hpp
src/kephir2/include/kephir2/archive.hpp
src/kephir2/include/kephir2/packing.hpp
docs/architecture/KEPHIR_2_APP_INTEGRATION_CONTRACT.md
docs/KEPHIR_2_CURRENT_STATUS.md
```

Branch base documentale al momento dello snapshot:

```text
development/kephir-2-core
```

Le branch R&D successive possono contenere ottimizzazioni più recenti, ma non devono cambiare il contratto host senza aggiornare questo documento.

---

# 88. Regola finale di integrazione

> **AURORA possiede l'esperienza utente. KEPHIR possiede la compressione. Il confine tra i due è la C ABI versionata. Il container `.aur` è un formato di prodotto stabile e non deve dipendere dai dettagli temporanei della ricerca KEPHIR.**

---

# 89. Definition of Done

L'integrazione è completata soltanto quando:

- AURORA comprime file;
- AURORA comprime directory;
- AURORA estrae;
- AURORA ispeziona;
- AURORA elenca contenuto;
- AURORA verifica un archivio;
- progress funziona;
- cancel funziona;
- errori sono localizzati lato GUI;
- Unicode funziona;
- path-safety passa;
- archivi legacy richiesti si aprono;
- `.aur` nuovo viene riconosciuto correttamente;
- il motore può essere aggiornato senza accoppiare la GUI agli internals;
- qualification completa è PASS.

---

# 90. Nota per chi effettuerà l'integrazione

Non assumere che ogni funzione descritta come `PLANNED`, `R&D` o `REQUIRED` sia già presente nel binario.

Prima di scrivere il codice di integrazione:

1. leggere `kephir2_c.h`;
2. chiamare `kephir2_api_version()`;
3. leggere release note del motore;
4. confrontare API realmente esportate con questa specifica;
5. implementare solo capability dichiarate dal motore;
6. non ricostruire internals mancanti dentro la GUI;
7. se una capability REQUIRED manca, completarla nel motore prima di aggirarla lato applicazione.

---

## Fine documento

**Nome definitivo consigliato:** `AURORA_KEPHIR_FINAL_INTEGRATION_SPEC.md`

Questo documento deve accompagnare la Release Candidate finale di KEPHIR e venire aggiornato nello stesso commit/tag del freeze dell'API e del formato `.aur`.
