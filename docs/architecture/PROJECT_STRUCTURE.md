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
