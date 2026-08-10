# Memory Index

**Before this index, read `docs/STATE.md` (what is running) and `docs/CONSTRAINTS.md` (what binds
the next step, indexed by when it bites). This file is the third stop, not the first.**


This directory is the single source of truth for this project's agent memory, version-controlled so
it travels between machines. Write new memories here — not to `~/.claude/projects/<slug>/memory/`,
which has been retired for this project. See `CLAUDE.md` for the contract.
- [Scope: the 1-2-3 sequence](scope-123-sequence.md) — 2026-07-31 restart; which edu/ material is main, supporting, and validation-only
- [Two systems in the corpus](two-systems-in-the-corpus.md) — the 1-2-3 and the daily-close layer it was distilled from — complementary, but the 1-2-3 wins on conflict
- [Artifact locality](artifact-locality.md) — user directive: all run artifacts under <repo>/.artifacts/, never ~ or other drives
- [Always ruff --fix](ruff-always-fix.md) — user directive: never bare `ruff check`; use `uvx ruff check --fix`
- [Opus expanded role](opus-expanded-role.md) — user directive: Opus subagents orchestrate+verify+audit whole phases, not just final audits
- [Audit hard rules not in the material](audit-hard-rules-not-in-material.md) — user directive: never invent a predicate to close a gap the material left open; it pre-decides what the SLM should discover
- [SLM decides L2's fuzzy terms](slm-decides-l2-fuzzy-terms.md) — user directive: route the unquantified L2 terms to the SLM to propose; ungroundable ones come back to the human, never a default. **All four the human then decided himself (D-29, D-30, D-34) once the censuses were in** — routing is not a bar on his deciding
- [Define fuzzy terms as residuals](define-fuzzy-terms-as-residuals.md) — user design rule: say what the term is NOT and let the rest be it; D-34 needed no number where four positive detectors all would have
- [Marked charts do not fingerprint to our bars](marked-charts-do-not-fingerprint-to-our-bars.md) — **superseded**: the fingerprint works to 0.08 pts; the 2026-08-09 failure was the bar range, not the method
- [Negative result over an incomplete range](negative-result-over-an-incomplete-range.md) — a search that finds nothing proves something about the span searched, not about the world
- [Measure after the engine runs](measure-after-the-engine-runs.md) — user directive: decide the open rule and build; do not gate the engine on labelling an answer key first
- [Long research tasks write incrementally](long-research-tasks-write-incrementally.md) — background subagents died 3x on the census with nothing written; judge delegation by the write pattern, not the task size
- [Read around the citation](read-around-the-citation.md) — a rulebook quote can be cut short of the sentence that undoes it; verify_citations cannot catch that
- [Sweep a misreading to every instance](sweep-a-misreading-to-every-instance.md) — one misread §10 number was four, and the fourth had already become a "fact" in our own evidence
- [Plausible cause is not a measured cause](plausible-cause-is-not-a-measured-cause.md) — the CME break "explained" a 16.95 pt residual for two days; the tool had been printing the real cause all along
- [Coverage claims need enumeration](coverage-claims-need-enumeration.md) — matching row counts are not coverage; diff the IDs, and list the source directory before claiming the material is silent
- [Databento OHLCV buckets by ts_recv](databento-ohlcv-buckets-by-ts-recv.md) — aggregating trades by ts_event silently mismatches vendor bars at minute boundaries
- [tz-aware day arithmetic](tz-aware-day-arithmetic.md) — Timedelta(days=1) on a tz-aware timestamp misdates the DST fall-back day; gate the deriving function, not just its consumers
- [2025-11-28 bar outage](historical-bars-2025-11-28-outage.md) — ~645 min of NQ+ES 1m bars missing; how to tell a data gap from a limit halt
