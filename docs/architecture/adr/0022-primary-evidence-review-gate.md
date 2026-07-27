# ADR-0022: A Cited Range Becomes Normative Only Once a Human Has Watched It

- Status: Accepted — ratified 2026-07-27 by signing the ten cited ranges
- Date: 2026-07-27

## Context

ADR-0004 makes primary Stoic media and PDFs the normative evidence and says model-derived
artifacts "cannot be the sole normative source", with a validator that "requires a primary
media/PDF record for every executable rule, checks asset digests and locators, and rejects
model-only evidence".

The validator does all of that. It does not do the one thing the ADR's Consequences section
also requires — "Publication requires provenance and human review". An evidence record carries
`asset_path`, `asset_sha256`, `transcript_path`, `transcript_sha256`, `locator` and `claim`.
The digest proves the file has not changed. **Nothing proves anyone opened it.**

That gap is exactly where ADR-0004's stated hazard lives. The `claim` string is what actually
enters the rulebook, and a claim can be written from a transcript — a model-derived artifact
that "can omit, paraphrase, or hallucinate details" — with no field distinguishing it from one
a human confirmed against the video. `slide-text-not-in-transcripts` sharpens this: rule
definitions in this material are shown on screen and never spoken, so a transcript-sourced
claim can be confidently wrong about the rule it states.

The gap has a name already. It is unresolved decision 12, `primary-evidence-review`: *"Which
cited media ranges have a human reviewer checked before any candidate becomes validated?"* As
`docs/notes/2026-07-27-spec-coverage-probe.md` §3 concluded, this is not one of twelve peer
decisions — it is the gate the other eleven pass through.

There is an existing human gate, and it is at the wrong granularity and the wrong time. The
`approval` envelope is one Ed25519 signature over the whole candidate digest, checked at
`publish`. It attests "a human approved this version", not "a human watched 00:03:45–00:04:08".
Decision 12 asks *which ranges*, which is per-record by construction, and it must bite before a
candidate becomes `validated`, not at publication.

One more thing forces the design. In this repository agents author the commits. **Anything an
agent can write is not an attestation.** An unsigned `reviewed_by:` field would be a field an
agent can fill in, which is precisely the failure ADR-0004 exists to prevent.

## Decision

**A rule reaches `status: validated` only when every evidence record it cites carries a signed
human review attesting that the cited range supports the record's claim.**

A range counts as reviewed when a human has:

1. opened the **primary asset** at the locator — the video, **with picture**, not the
   transcript and not a VLM record;
2. confirmed the record's `claim` is stated there;
3. written down what they actually saw or heard; and
4. signed an attestation with the pinned Ed25519 key.

The attestation is a `review` block on the evidence record:

```yaml
review:
  reviewer_email: someone@example.com
  reviewed_at: '2026-07-28T00:00:00Z'
  verdict: claim_supported          # or claim_not_supported
  observed: 'Slide reads "PDH / PDL / PDC" at 00:03:52; he says to wait for price there.'
  asset_sha256: <must equal the record's>
  transcript_sha256: <must equal the record's, when it has one>
  public_key_fingerprint: <sha256 of the pinned raw Ed25519 public key>
  signature_base64: <Ed25519 over the review message>
```

The signed message is domain-separated under `stoic-derived/evidence-review/v1` and binds
`evidence_id`, `asset_sha256`, `transcript_sha256`, `locator`, `claim`, `verdict`, `observed`,
`reviewer_email`, `reviewed_at` and `public_key_fingerprint`.

**Amended 2026-07-27: `observed` is signed.** It was not, in the version of this ADR the first ten
reviews were made under. That left the field this ADR describes as the reviewer's own account of
what they saw — the thing a future reader uses to judge a review *without* re-watching — as the one
part of a review an agent could rewrite with the signature still verifying. Every other field was
attested; the human's words were not. The gap surfaced in practice on `ev-pdh-pdl-pdc`, whose
`observed` described the wrong claim and would have been silently correctable. Adding it invalidated
the ten signatures made before the amendment, and they were re-signed.

**What the binding buys, and why each field is in it:**

- **`claim` is signed**, so reviewing a weak claim and then strengthening it invalidates the
  signature rather than inheriting the attestation. This is the attack that matters most: it is
  the one an honest person commits by accident while editing.
- **`observed` is signed**, so the reviewer's account cannot be edited into one they never wrote.
  Without this the gate attests *that* a human reviewed a range but not *what they said about it*,
  which is the half a later reader actually reads.
- **`locator` is signed**, so moving the range invalidates the review.
- **`asset_sha256` and `transcript_sha256` are signed and must also equal the record's**, so
  re-encoding the video or re-cutting the transcript makes the review go stale instead of
  silently carrying over.
- **The key is pinned**, so an agent cannot produce one.

Reviews are authoring data and live inside the candidate digest, so the `approval` envelope
signs over them: approving a rulebook approves *who reviewed which range*, and adding a review
after approval correctly reports a stale approval digest.

### Scope: which ranges

Exactly the evidence cited by rules, and only when a rule wants to leave `candidate`/`unknown`.
Not the corpus, not uncited records. The gate is on *promotion*, not on collection.

The whole backlog today is **10 cited records, 9m16s of video** (`ev-alternate-sma-profile` is
uncited and out of scope until something cites it). That is the entire ADR-0004 review debt for
this project as it stands — a single sitting, not a programme.

### Where mining fits

Model-derived work never becomes evidence. It proposes a **review candidate** — a draft record
with a locator and a claim — that a human confirms or rejects. This is ADR-0004's "Mining
remains useful without entering the live path", made operational. Every visual record already
cites `video`, `t_start`, `hms_start` and `source_frame`, so the VLM corpus is a locator
generator, which is the useful half.

## Consequences

- **Decision 12 is answered, 2026-07-27.** All ten cited ranges were watched and signed by the
  repository owner under one key (fingerprint `25054c7b…`); `primary-evidence-review` has been
  removed from `unresolved_decisions`. The gate is now live rather than pending: it no longer
  blocks, and it will block again the moment a claim, locator, `observed` or asset changes.
- **`validate` is now the review to-do list.** Unreviewed cited evidence is a readiness blocker
  named per record, and the dossier's Evidence Matrix carries a **Human review** column that
  reads `**not reviewed**` until it does not.
- **A `claim_not_supported` verdict is a finding, not a failure.** It means the record's claim
  is wrong and must be rewritten — and rewriting it invalidates the review, so it goes back
  through the gate. The material is not at fault; our transcription of it is.
- **Reviews are cheap to invalidate and that is the point.** Any edit to a claim, locator or
  asset drops the record back to unreviewed. Expect to re-review after editing a claim.
- **This does not gate research.** Consistent with ADR-0011 and ADR-0021, nothing here blocks
  mining, probes or backtests. It blocks exactly one transition: candidate → validated.
- **It does not weaken ADR-0021.** A reviewed claim is still a claim; every number derived from
  it remains presumed invalid until audited.

## Compliance

- `_validate_rules` hard-fails a `validated` rule citing any record without a
  `verdict: claim_supported` review — in the authoring YAML and, independently, in a published
  release, which carries its reviews in `source_snapshot_digests`.
- `_validate_review` enforces the digest binding structurally on every load.
- `publish` verifies every cited review's signature against the pinned key, alongside the
  approval envelope. Structural validation proves a review exists and is bound to the right
  bytes; only the pinned key proves a human made it.
- `readiness()` reports one blocker per unreviewed cited record.
- `stoic-rulebook review-queue <rulebook>` prints what to open, the exact range, an `ffplay`
  command, and the claim to check. `stoic-rulebook review-message` emits the bytes to sign.
- Tests: `tests/strategy/test_rulebook.py`, the block under
  "ADR-0004 primary-evidence review gate", including that editing a claim after review, editing
  `observed` after review, and signing with an unpinned key all fail closed. Each was observed
  failing against the unfixed code before being kept.
