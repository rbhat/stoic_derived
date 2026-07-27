---
name: primary-evidence-review-gate
description: "The ADR-0004 human-review gate (unresolved decision 12): a rule reaches validated only when every cited evidence record carries a signed human review of the range — an agent structurally cannot write one"
metadata:
  type: project
---

**Binding decision: `docs/architecture/adr/0022-primary-evidence-review-gate.md`. Procedure and the
backlog: `docs/notes/2026-07-27-decision-12-primary-evidence-review.md`.** Built 2026-07-27.

`strategy/rulebook.py` now refuses `status: validated` on any rule citing an evidence record without
a `review` block carrying `verdict: claim_supported`. `readiness()` names each unreviewed cited
record as a blocker, and `stoic-rulebook review-queue strategy/rulebook.yaml` prints what to open.

**The gap this closed:** evidence records had provenance but no attestation. A digest proves the file
has not changed; nothing proved anyone opened it. The `claim` string is what enters the rulebook, and
a claim written from a transcript was indistinguishable from one confirmed against the video —
which matters here because [[slide-text-not-in-transcripts]] means rule text is on screen and never
spoken.

**Why it is signed, and why that is not ceremony:** in this repo agents author the commits, so an
unsigned `reviewed_by:` is a field an agent can fill in. The Ed25519 signature over the claim,
locator and both digests is the only part an agent structurally cannot produce. It also means
editing a claim after review invalidates the signature rather than inheriting the attestation.

**Do not confuse it with `approval`.** That is one signature over the whole candidate digest at
`publish`. This is per-record and bites at `validated`. They compose; neither replaces the other.

**Status: the mechanism exists, the reviews do not.** Decision 12 stays in `unresolved_decisions`,
and ADR-0022 stays *Proposed*, until the user has watched the **10 cited ranges — 9m16s total** and
signed. Do not mark it resolved on the user's behalf, and do not propose an unsigned shortcut.

**Mining never becomes evidence.** The VLM/SLM path proposes a *review candidate* (locator + draft
claim) that a human confirms — ADR-0004's "mining remains useful without entering the live path".
This is also the answer to the question `docs/notes/2026-07-27-spec-coverage-probe.md` §3 left open:
measuring a parameter across instructor-labelled instances is discovery, and becomes a rule only via
a reviewed primary record. See [[signal-fidelity-over-edge-revalidation]] and
[[audit-derived-numbers]] — a reviewed claim is still subject to ADR-0021.
