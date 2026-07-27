# Decision 12, `primary-evidence-review`: the gate, and how to clear the backlog

**Date:** 2026-07-27 · **Status:** mechanism built and enforced; awaiting the user's reviews and
ratification · **Binding decision:** `docs/architecture/adr/0022-primary-evidence-review-gate.md`

## 0. What was actually missing

The validator already enforced everything ADR-0004's Compliance paragraph names except one thing.
Evidence records carry `asset_path`, `asset_sha256`, `transcript_path`, `transcript_sha256`,
`locator` and `claim`. **The digest proves the file has not changed; nothing proved anyone opened
it.** The `claim` is what enters the rulebook, and a claim written from a transcript was
indistinguishable from one a human confirmed against the video.

That matters more here than it would elsewhere, because `slide-text-not-in-transcripts` establishes
that rule definitions in this material are **shown on screen and never spoken**. A transcript-
sourced claim about a rule can be confidently wrong.

The existing `approval` envelope is not this gate: it is one signature over the whole candidate
digest at `publish` time. Decision 12 asks *which ranges*, which is per-record, and it has to bite
before `validated`, not at publication. The two compose — review gates `validated`, approval gates
`publish`.

## 1. The backlog is small, and that is the headline

```
$ stoic-rulebook review-queue strategy/rulebook.yaml
10 record(s), 9m16s of media to watch
```

| evidence id | range | cited by | seconds |
|---|---|---|---|
| `ev-hcom-lcom` | 00:27:49–00:28:00 | 3 | 11 |
| `ev-poi-not-middle-range` | 00:22:30–00:22:44 | 1 | 14 |
| `ev-pdh-pdl-pdc` | 00:03:45–00:04:08 | 4 | 23 |
| `ev-trapped-trader-context` | 00:04:15–00:04:41 | 1 | 26 |
| `ev-context-ordering` | 00:36:35–00:37:05 | 1 | 30 |
| `ev-chop-zone` | 00:44:32–00:45:11 | 3 | 39 |
| `ev-setup-taxonomy` | 00:06:27–00:07:11 | 6 | 44 |
| `ev-fib-target-context` | 00:51:19–00:52:15 | 3 | 56 |
| `ev-sma-session-context` | 00:44:34–00:45:44 | 3 | 70 |
| `ev-sbs-entry-model` | 00:46:55–00:50:58 | 4 | 243 |

`ev-alternate-sma-profile` (247 s) is cited by no rule — only by the `sma-profile-conflict` entry —
so it is out of scope until something cites it.

**Decision 12 was carrying the weight of an open-ended programme and it is a single sitting.** This
is the number worth knowing before deciding whether the gate is affordable.

## 2. The procedure

For each record in the queue:

1. **Watch the range with picture.** The queue prints the command:
   `ffplay -ss 00:03:45 -autoexit "edu/videos/…mp4"`. Not the transcript — a transcript is a
   model-derived artifact and ADR-0004 rejects it as the sole source, and the rule text is usually
   on screen rather than in the audio.
2. **Read the claim the queue prints** and decide whether the range supports it as written.
3. **Write down what you saw or heard**, in your words. This becomes `observed`. It is the part a
   future reader uses to decide whether to trust the review without re-watching.
4. **Sign it.** `stoic-rulebook review-message --evidence-id … --reviewer-email … --reviewed-at …
   --public-key-fingerprint …` emits the exact bytes; sign them with the pinned Ed25519 key and
   paste the block onto the record.

A `claim_not_supported` verdict is a finding, not a failure: it means the claim needs rewriting,
and rewriting invalidates the review so it comes back through the gate.

## 3. What the signature is for

In this repo **agents author the commits**, so an unsigned `reviewed_by:` field would be a field an
agent can fill in — which is the exact failure ADR-0004 exists to prevent. The signature is the only
part of this design an agent structurally cannot produce.

The message binds the claim, the locator and both digests, so:

- editing a claim after review invalidates the signature (reviewing a weak claim and then
  strengthening it is the accident this closes);
- moving the locator invalidates it;
- re-encoding the asset makes the review go stale rather than silently carry over.

Both are covered by tests that fail closed.

## 4. What this does not do

- **It does not gate research.** Mining, probes and backtests are untouched (ADR-0011, ADR-0021).
  It blocks exactly one transition: candidate → validated.
- **It does not make a reviewed claim true.** ADR-0021 still governs every number derived from it.
- **It does not resolve decision 12.** The mechanism exists; the reviews do not. `decision 12`
  stays in `unresolved_decisions` until the ten ranges are reviewed and the user ratifies ADR-0022
  (currently *Proposed*).

## 5. Where the VLM corpus fits

Nowhere, directly — and that is the correct answer, not a limitation. Model-derived output proposes
a **review candidate**: a draft record with a locator and a claim, which a human confirms. Every
visual record already carries `video`, `t_start`, `hms_start` and `source_frame`, so the 10,120-state
corpus is a locator generator for exactly this queue. ADR-0004: "Mining remains useful without
entering the live path."

This also settles the question `docs/notes/2026-07-27-spec-coverage-probe.md` §3 left open. Measuring
retest depth across ~148 instructor-labelled B&R instances stays **discovery**; it becomes a rule only
by way of a reviewed primary record, whatever the measurement says.
