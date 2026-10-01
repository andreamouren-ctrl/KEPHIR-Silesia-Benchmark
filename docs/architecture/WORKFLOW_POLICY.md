# Workflow Policy — AURORA Compressor / KHEPRI

**Canonical branch:** `project/aurora-compressor`

## Purpose

GitHub Actions è parte del sistema di riproducibilità. Un workflow deve riprodurre una qualification, un benchmark canonico o una ricerca ancora mantenuta; non deve essere usato come archivio storico.

## Retention policy

- Un workflow sperimentale concluso viene rimosso dal working tree quando il risultato è consolidato nella documentazione o assorbito da una linea successiva.
- La cronologia Git conserva comunque il workflow originale e permette di recuperarlo.
- Non si mantengono decine di workflow EXP/FAST/SPEED inattivi soltanto per memoria storica.
- I workflow promossi o ancora necessari alla riproducibilità corrente restano versionati.

## Percorsi canonici

- router/promoted research → `research/routers/`
- packaging attivo → `research/packaging/`
- real-world research benchmarks → `research/benchmarks/`
- Silesia harness → `benchmarks/silesia/`
- competitor benchmarks → `benchmarks/competitors/`
- release qualification → `release/`
- source fragments canonici → `engine/source_parts/`

Nessun workflow deve reintrodurre script di ricerca nella root.

## Trigger policy

### Active R&D

Può usare trigger automatici, ma con path filter stretti sull'esperimento interessato.

### Release qualification

La qualification deve attivarsi solo quando cambiano componenti che possono alterare encoder, decoder, packing, Factory Knowledge, qualification harness o backend/build chain.

Modifiche solo a `docs/**`, README o file editoriali non devono richiedere una qualification completa.

## Result discipline

Ogni benchmark attivo deve:
- fallire su roundtrip/SHA mismatch;
- identificare il checkpoint;
- registrare corpus e dimensione input;
- conservare output misurato come artifact quando utile;
- confrontare con il reference quando propone una sostituzione;
- separare misure reali da ipotesi.

## Release discipline

Il commit qualificato di una release è immutabile come riferimento tecnico.

KEPHIR 1.0:
- qualified commit: `efd00a3cfc63d8306bef65aa90eb0154dc7b9004`
- qualification run: `36151845469`
- result: **SUCCESS**
- roundtrip: **FINAL_SHA_ALL_PASS**

Una modifica successiva al codice crea un nuovo candidato e richiede una nuova qualification.

## Experiment discipline

Una modifica concettuale → una CI → un risultato misurato → PROMOTE/REJECT → consolidamento documentale → rimozione dal working tree se superseded.
