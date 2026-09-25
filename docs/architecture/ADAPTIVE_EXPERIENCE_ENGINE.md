# KEPHIR Adaptive Experience Engine

**Status:** canonical architecture decision  
**Date:** 2026-09-25

## 1. Goal

KEPHIR must improve its encoder-side decision quality from accumulated experience without changing the lossless decoding contract.

The system learns which compression actions are worth testing for different chunk families and uses that knowledge to reduce wasted search while preserving or improving compressed size.

## 2. Three-layer knowledge model

### 2.1 Factory Knowledge Base

A pre-trained, versioned knowledge base is shipped with AURORA/KEPHIR.

It is trained from the project's canonical benchmark and research corpus, including:
- Silesia
- Canterbury
- Calgary
- Canterbury Large
- Artificial
- enwik8
- future approved benchmark/training corpora

A new installation therefore does **not** start from zero. It starts with the experience accumulated during KEPHIR R&D.

The factory knowledge is treated as read-only at runtime.

### 2.2 Persistent Local Experience

Each installation maintains a separate writable local experience store.

It records statistical experience only, for example:
- feature bucket / chunk fingerprint family
- candidate action
- number of observations and trials
- wins
- measured byte gain or loss
- measured encode cost
- confidence
- recency / last-seen generation
- optional decayed historical score

The local store persists across program launches and upgrades.

It must not require retaining the user's original file contents.

### 2.3 Session / Short-Term Experience

During one compression job, KEPHIR keeps a short-term model that adapts immediately to the current workload.

This lets a long archive become easier to route while it is still being compressed.

At successful job completion, eligible aggregate knowledge can be merged into the persistent local store.

## 3. Update and installation behavior

The shipped factory model and the user's local model are separate.

On software update:
1. install the new factory knowledge version;
2. preserve the user's local experience;
3. load both;
4. reconcile scores using compatibility/version metadata;
5. continue learning.

A software update must not silently destroy the user's accumulated local experience.

If an engine change makes old statistics incompatible, they are migrated, down-weighted, or archived rather than blindly reused.

## 4. Encoder-only intelligence

Learning influences encoder decisions only.

The decoder never needs the learner or its history. The archive stores every mode/backend/transform decision required for deterministic reversal.

Therefore:
- lossless behavior remains independent of learned state;
- decoding an archive does not require the originating machine's experience database;
- two machines may choose different encodings while still producing fully valid KEPHIR archives.

## 5. Decision objective

The learner does not optimize ratio alone.

For each candidate action it estimates an expected utility based on:
- probability of a win;
- expected bytes saved;
- expected compute cost;
- current compression profile;
- remaining time/search budget;
- confidence and exploration requirements.

A useful canonical form is:

```
expected_value ~= expected_bytes_saved / expected_extra_time
```

with profile-specific weighting.

ULTRA may spend more compute for ratio.
BALANCED trades ratio against cost.
ULTRA FAST strongly penalizes exploratory work.

## 6. Exploration vs exploitation

KEPHIR must never permanently stop learning.

Known-good families are exploited aggressively, while low-confidence or historically poor candidates receive sparse refresh probes so that changed data distributions or improved backends can be rediscovered.

Exploration rate must fall as confidence grows.

## 7. Privacy and portability

Persistent experience should contain aggregate statistics, not source-file contents.

The knowledge store should be exportable/importable independently of archives so that:
- users can migrate experience between their own machines;
- QA can reproduce learned states;
- benchmark-trained factory models can be generated in CI;
- corrupted or incompatible local knowledge can be reset without affecting archives.

## 8. Versioning

The knowledge format requires:
- schema version;
- engine compatibility version;
- factory model version;
- feature-set version;
- action-set version;
- checksum/integrity metadata.

Suggested conceptual artifacts:

```
khepri_factory.kxp     # shipped, read-only
khepri_local.kxp       # user-specific persistent overlay
khepri_session.tmp     # in-memory/temporary session experience
```

Names/extensions remain implementation details until the format is frozen.

## 9. EXP-70 evidence

EXP-70 validated the first online-learning prototype across six canonical corpora and three consecutive epochs.

Aggregate raw data per epoch: **329,460,340 B**.

Measured behavior:
- epoch 1: 401 probes, 4 wins, 16,358 B gain, 92.01 s
- epoch 2: 88 probes, 4 wins, 16,358 B gain, 76.79 s
- epoch 3: 68 probes, 4 wins, 16,358 B gain, 76.18 s
- SHA roundtrip: PASS in all epochs

The learner reduced probes by about 83% from epoch 1 to epoch 3 while retaining all measured winning decisions and the same byte gain.

This validates the architectural premise that accumulated experience can reduce search cost without sacrificing the successful choices already discovered.

## 10. Next expansion

The next learner generation should generalize from one learned action (Word-XOR probing) to a portfolio including:
- structural transforms;
- delta families;
- Word-XOR;
- PSG variants;
- grain 128/256/512 KiB;
- BASE verification;
- text transforms;
- future CPU/GPU analysis actions.

The long-term objective is a cost-aware Adaptive Experience Engine that continuously converts benchmark and user-local experience into better routing decisions.


## 11. Canonical functional specification

The Adaptive Experience Engine is composed of the following canonical functions.

### 11.1 Feature / Fingerprint Extraction

For each chunk, compute a compact content fingerprint from inexpensive signals such as:
- chunk size;
- sampled byte entropy;
- local/subchunk entropy spread;
- residual entropy at selected lags;
- zero-byte density;
- printable/ASCII density;
- letter/space density;
- repetition/run density;
- simple periodicity indicators;
- optional LZ/match-density summaries;
- structural heterogeneity.

The feature extractor must be cheaper than the candidate encodes it is intended to avoid.

The file name or extension may be used as a weak optional hint in future work, but routing must never depend on it for correctness.

### 11.2 Chunk Family / Context Bucketing

Fingerprints are mapped to a compact context/family representation.

EXP-70 used coarse buckets based on:
- size band;
- entropy band;
- zero-density band;
- printability band.

Future versions may use a denser vector model or contextual bandit, but the model must remain bounded, fast and versioned.

### 11.3 Action Portfolio

The learner may score actions including:
- BASE KEPHIR;
- delta + transpose families;
- Word-XOR;
- PSG3 / PSG5 / PSG6 or later backend experts;
- 512 / 256 / 128 KiB grain choice;
- BASE verification;
- indexed text transform;
- future structural transforms;
- future CPU/GPU pre-analysis actions.

An action is never accepted because the learner predicts it will win. When a candidate is actually encoded, the measured compressed size remains authoritative.

### 11.4 Utility / Reward Scoring

Each context-action pair stores enough evidence to estimate:
- probability of winning;
- expected byte gain;
- expected extra encode time;
- win rate;
- confidence;
- recency.

Canonical objective:

```
utility = profile_weighted(expected_byte_gain, expected_extra_time, confidence)
```

A simple first-order efficiency metric is:

```
bytes_saved_per_second = expected_byte_gain / expected_extra_time
```

The exact formula may evolve without changing the archive format.

### 11.5 Exploration Controller

The engine must support controlled exploration:
- mandatory probes for new/unknown contexts;
- decreasing exploration as confidence grows;
- sparse refresh probes for historically poor actions;
- re-exploration after engine/action version changes;
- configurable exploration ceilings by compression profile.

This prevents permanent lock-in to an early wrong decision.

### 11.6 Exploitation Controller

When evidence is strong, KEPHIR should:
- skip repeatedly losing candidate encodes;
- prioritize historically profitable candidates;
- order candidate evaluation by expected utility;
- stop early when remaining candidates have insufficient expected return.

### 11.7 Time / Search Budget Manager

The encoder maintains a search budget.

Conceptually:

```
total_target_time = baseline_encode_time + adaptive_search_budget
```

For ULTRA, unused time headroom may be reinvested into high-value candidate checks.
BALANCED uses a smaller search budget.
FAST/ULTRA FAST aggressively restricts or disables expensive exploration.

Budget consumption is measured, not guessed.

### 11.8 Online Learning Update

After a probe:
1. measure candidate size;
2. measure extra encode cost;
3. compare with the retained baseline choice;
4. record win/loss and byte delta;
5. update confidence and utility statistics;
6. use the new evidence for subsequent chunks immediately.

Learning therefore occurs while the current archive is still being compressed.

### 11.9 Persistent Save

At successful completion, eligible aggregate session statistics are merged into the local persistent store.

Persistence must be:
- atomic or crash-safe;
- checksum protected;
- schema-versioned;
- bounded in size;
- recoverable if corrupted.

Source bytes are not stored.

### 11.10 Startup Load

At program startup:
1. load compatible Factory Knowledge;
2. load compatible Local Experience;
3. verify integrity;
4. reconcile versions;
5. initialize Session Experience;
6. fall back safely to factory/default routing if local knowledge is absent or invalid.

### 11.11 Factory + Local Merge

Factory knowledge remains read-only.

Local knowledge overlays factory knowledge using evidence/confidence weighting. A local installation can specialize its decisions while retaining the broad benchmark experience distributed by the project.

A program update may replace the factory model without overwriting local history.

### 11.12 Confidence

Confidence increases with:
- more compatible observations;
- repeated wins/losses;
- stable measured costs;
- recent evidence.

Low-confidence contexts receive more exploration. High-confidence contexts favor exploitation.

### 11.13 Experience Decay

Historical observations may be down-weighted based on:
- age/generation;
- backend version change;
- feature schema change;
- action implementation change;
- changed measured behavior.

Decay avoids treating old evidence as permanently authoritative.

### 11.14 Compatibility and Migration

Every knowledge store must carry:
- schema version;
- engine compatibility version;
- feature-set version;
- action-set version;
- factory model version;
- checksum/integrity metadata.

If knowledge is partially compatible, KEPHIR should migrate or down-weight compatible sections rather than discarding everything.

### 11.15 Privacy

The default persistent learner stores aggregate statistical knowledge only.

It must not require:
- file contents;
- document text;
- paths;
- personal metadata.

The learning system is designed to work locally/offline.

### 11.16 Export / Import

Knowledge should be exportable for:
- migration between a user's machines;
- QA reproduction;
- benchmark training;
- regression testing;
- creation of future Factory Knowledge releases.

Import must validate compatibility and integrity before activation.

### 11.17 Reset / Recovery

Resetting learned knowledge must not affect compressed archives.

The user or recovery system can:
- reset Local Experience;
- restore Factory-only behavior;
- archive an incompatible local model;
- rebuild local experience over time.

### 11.18 Deterministic archive contract

Learned state may change encoder decisions, but every chosen transform/backend/mode is explicitly represented in the encoded stream/container.

Therefore decode correctness is independent of:
- factory model;
- local model;
- session model;
- training corpus;
- originating machine.

## 12. Knowledge lifecycle

Canonical lifecycle:

```
R&D benchmark results
        ↓
Factory training/export
        ↓
Factory Knowledge shipped with AURORA
        ↓
new installation loads prior project experience
        ↓
session observes local files
        ↓
online learner updates session statistics
        ↓
successful job merges aggregate knowledge locally
        ↓
future jobs start smarter
        ↓
software update supplies newer Factory Knowledge
        ↓
compatible Local Experience is preserved and merged
```

## 13. Product behavior

A newly installed KEPHIR should therefore behave as an experienced compressor from its first archive.

A long-running installation should become increasingly specialized to the statistical structures it encounters while never requiring its learned state to decode an archive.

This behavior is a product-level requirement, not only an EXP-70 research feature.

## 14. Current implementation state

As of EXP-70:
- online feature bucketing: prototype validated;
- exploration/exploitation reduction: prototype validated;
- same winning Word-XOR decisions retained across three epochs: validated;
- six-corpus SHA roundtrip: validated;
- Factory Knowledge packaging: architecture approved, implementation pending;
- persistent Local Experience file: architecture approved, implementation pending;
- contextual multi-action portfolio: planned next research step;
- knowledge migration/versioning: specified, implementation pending;
- real CPU+GPU learner integration: pending real GPU validation.
