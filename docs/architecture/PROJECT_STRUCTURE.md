# AURORA Compressor — struttura canonica

**Canonical branch:** `project/aurora-compressor`

## Confine del progetto

Questa linea contiene solo compressione general-purpose di file e archivi.

Audio, video, container AUM, protocollo AUS1 e streaming appartengono a `project/aurora-media`.

## Struttura

~~~text
/
├── README.md
├── engine/
│   └── source_parts/
├── release/
│   ├── kephir_final.py
│   ├── final_qualification.py
│   └── factory/
│       └── khepri_factory_v1.json
├── research/
│   ├── routers/
│   ├── packaging/
│   └── benchmarks/
├── benchmarks/
│   ├── silesia/
│   └── competitors/
├── docs/
│   ├── architecture/
│   ├── releases/
│   └── research/
└── .github/workflows/
~~~

## Ruoli delle aree

- `engine/source_parts/` — ricostruzione del backend C++ storico.
- `release/` — superficie integrata qualificabile; non è area di esperimenti.
- `release/factory/` — Factory Knowledge read-only distribuita con il prodotto.
- `research/routers/` — solo router/promoted research ancora utile alla linea corrente.
- `research/packaging/` — Smart Directory Packing promosso e futuri esperimenti di packaging attivi.
- `research/benchmarks/` — benchmark real-world/R&D ancora in uso.
- `benchmarks/` — harness benchmark canonici e competitor.
- `docs/releases/` — baseline e qualification record.

## Politica di retention

Gli esperimenti superseded non vengono mantenuti nel working tree solo per memoria storica. La storia completa resta recuperabile da Git; conclusioni, numeri e checkpoint promossi devono invece essere consolidati in `docs/research/AURORA_COMPRESSOR_TECHNICAL_MASTER.md` e `docs/architecture/CHECKPOINT_REGISTRY.md`.

## Regole

1. Nessun nuovo script di ricerca va nella root.
2. Un esperimento concluso e non più necessario alla riproducibilità corrente viene rimosso dal working tree dopo aver consolidato i risultati.
3. I risultati promossi devono essere documentati.
4. `release/` contiene solo componenti integrati destinati a qualification/release.
5. Factory e Local Experience restano separate.
6. Il decoder non dipende da Factory/Local Experience.
7. I file runtime, cache, output benchmark e knowledge locali non vanno versionati.
8. Il lavoro media non entra in questa branch.
9. Il commit qualificato di una release non viene riscritto: ogni modifica successiva richiede nuova qualification.
10. I workflow attivi devono corrispondere a una qualification, benchmark canonico o ricerca ancora mantenuta.
