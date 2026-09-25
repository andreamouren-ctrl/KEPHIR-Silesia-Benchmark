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
