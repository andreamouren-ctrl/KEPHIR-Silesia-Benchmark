# AURORA Compressor — struttura canonica

**Branch:** `project/aurora-compressor`

## Confine del progetto

Questa branch contiene solo compressione general-purpose di file e archivi.

Il codice audio, video, container AUM, protocollo AUS1 e streaming appartiene a `project/aurora-media`.

## Cartelle

- `engine/source_parts/` — frammenti sorgente KEPHIR usati per ricostruire il baseline C++.
- `research/experiments/` — sweep e test EXP cronologici.
- `research/validation/` — validazioni dei checkpoint scelti.
- `research/oracles/` — esperimenti oracle non production-ready.
- `research/routers/` — router strutturali/adattivi.
- `research/diagnostics/` — profiling e diagnostica.
- `research/generators/general/` — generatori C++ della linea EXP.
- `research/generators/speed/` — generatori della linea FAST/SPEED.
- `research/speed/` — benchmark velocità e confronti A/B.
- `benchmarks/silesia/` — harness Silesia.
- `benchmarks/competitors/` — benchmark comparativi.
- `.github/workflows/` — workflow riproducibili aggiornati ai percorsi canonici.

## Regole

1. Nessun nuovo script di ricerca va nella root.
2. Gli ID storici EXP/FAST restano nei nomi file.
3. I risultati promossi devono essere documentati prima di diventare baseline.
4. Il lavoro media non entra in questa branch.


## Aggiornamento ULTRA / parallelismo

Aree aggiunte dalla linea EXP-51→EXP-70:

- `research/routers/` — router ULTRA EXP-54→70, inclusi grain routing, scheduler paralleli, candidate verification e learner adattivo.
- `research/diagnostics/` — profiling EXP-60 e diagnostica dei colli di bottiglia.
- `research/gpu/` — prototipi OpenCL CPU+GPU; nessuna misura GPU è considerata valida senza hardware reale.
- `benchmarks/competitors/` — benchmark EXP-56 e benchmark multi-corpus EXP-58.
- branch sperimentali `research/ultra-expXX` — conservano gli esperimenti senza promuoverli automaticamente nella branch canonica.

Il checkpoint ULTRA pratico corrente è **EXP-66**.


## Adaptive Experience Engine

La memoria adattiva è una funzione canonica dell'encoder KEPHIR.

Componenti logici:
- **Factory Knowledge Base** — esperienza pre-addestrata e distribuita con il programma;
- **Persistent Local Experience** — esperienza locale persistente tra sessioni e aggiornamenti;
- **Session Experience** — apprendimento rapido limitato al job corrente;
- **Feature/Fingerprint Extractor** — descrive i chunk senza usare il nome del file;
- **Action Portfolio** — BASE, delta/transpose, Word-XOR, PSG, grain, token text e future azioni;
- **Decision/Utility Engine** — stima byte attesi risparmiati rispetto al costo computazionale;
- **Exploration Controller** — mantiene probe rari anche sulle azioni sfavorite;
- **Confidence + Decay** — aumenta la fiducia con l'evidenza e riduce il peso dell'esperienza obsoleta;
- **Budget Manager** — limita la ricerca extra in funzione del profilo ULTRA/BALANCED/FAST;
- **Knowledge Merger** — combina Factory + Local + Session senza distruggere la memoria locale;
- **Version/Compatibility Layer** — gestisce schema, feature set, action set e compatibilità con il motore;
- **Integrity/Recovery** — checksum, fallback sicuro e reset della sola knowledge base senza influire sugli archivi.

Documento canonico: `docs/architecture/ADAPTIVE_EXPERIENCE_ENGINE.md`.

La knowledge base influenza solo l'encoder. Il decoder rimane indipendente dallo stato appreso.
