# KEPHIR Adaptive Experience Engine

## Scopo

L'Adaptive Experience Engine consente all'encoder KEPHIR di usare conoscenza statistica accumulata per ridurre probe inutili e scegliere più rapidamente strategie promettenti.

È un sistema **encoder-only**: il decoder non consulta alcun database di esperienza.

## Tre livelli

### 1. Factory Knowledge

Read-only e distribuita con KEPHIR.

Percorso 1.0:

`release/factory/khepri_factory_v1.json`

La Factory v1 contiene **79 stati positivi** distillati dall'EXP-75:
- 77 stati adaptive-grain;
- 2 stati Word-XOR.

Un aggiornamento software può sostituire la Factory senza cancellare l'esperienza locale.

### 2. Persistent Local Experience

Overlay scrivibile sul computer dell'utente.

Default implementativo:
`~/.kephir/khepri_local_v1.json`

Override:
- `KEPHIR_HOME`
- opzione CLI `--local-knowledge`

Il salvataggio è atomico tramite file temporaneo + replace.

### 3. Session Experience

Conoscenza temporanea maturata durante il job corrente.

Serve a evitare di ripetere probe già giudicati poco utili e può alimentare l'overlay locale dopo un'operazione completata correttamente.

## Principio di privacy

L'esperienza deve contenere solo statistiche aggregate/fingerprint tecnici.

Non devono essere memorizzati:
- byte originali;
- contenuti;
- nomi di file;
- path personali;
- testo utente;
- metadati identificativi.

## Feature

La linea di ricerca usa o prevede:
- size class;
- entropy;
- residual entropy;
- zero density;
- printability;
- repetition;
- periodicity;
- match density;
- heterogeneity;
- lag residual features;
- entropy spread.

## Azioni

Le azioni possono includere:
- BASE;
- adaptive grain 128/256/512 KiB;
- delta/transpose;
- Word-XOR;
- PSG sperimentali;
- futuri backend CPU/GPU.

L'azione effettivamente usata è sempre descritta nell'archivio dal formato necessario alla decodifica. La decisione del learner non è necessaria al decoder.

## Factory prior in KEPHIR 1.0

La baseline usa un gate conservativo per i prior grain.

Condizioni indicative del checkpoint integrato:
- trials sufficienti;
- win rate elevato;
- gain medio positivo;
- fallback alla normale esplorazione quando la confidenza non è sufficiente.

## Risultati qualificati

### Repository reale

Cold:
- 117,523 B;
- 1.703 s.

Factory:
- 117,523 B;
- 0.705 s.

La Factory ha mantenuto esattamente lo stesso archivio riducendo fortemente il costo di probe.

### Silesia

Cold:
- 62,953,321 B;
- 96.050 s.

Factory:
- 62,958,288 B;
- 75.057 s.

La Factory ha ridotto il tempo di compressione con una differenza di 4,967 B sul dataset completo.

## Invarianti

1. Factory e Local sono separati.
2. Il decoder non dipende da nessuno dei due.
3. Il formato archivio deve essere autosufficiente.
4. L'apprendimento non può rendere la decodifica non deterministica.
5. Corruzione/mancanza del database locale non deve impedire la decodifica.
6. La Factory non deve essere modificata dall'utente durante un job.
7. L'esperienza locale deve essere versionata e migrabile.
8. Il reset della Local Experience non deve rendere illeggibili archivi esistenti.

## Evoluzione prevista

La linea 1.1 può estendere:
- confidence calibration;
- decay/staleness;
- exploration/exploitation;
- budget per profilo FAST/BALANCED/ULTRA;
- clustering di stream;
- predictive grain gate più economico;
- backend CPU/GPU quando realmente validato.
