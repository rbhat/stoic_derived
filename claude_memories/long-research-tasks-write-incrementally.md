---
name: long-research-tasks-write-incrementally
description: Background subagents on long read-the-whole-corpus tasks died three times before writing anything — write the deliverable incrementally, or do it in the main session
metadata:
  type: feedback
---

**A long research task that writes its deliverable only at the end will lose everything when the
agent dies.** On 2026-08-09 the passage census was dispatched to background Sonnet subagents
**three times** and produced **nothing** all three times:

- Two agents on the first attempt, killed on a session limit.
- Two more on the relaunch, killed again. Both had finished reading and verifying — the last thing
  one reported was *"All citations verified. Now let me write the census document"* — and neither
  had written a byte.

The failure mode is specific and repeatable: these tasks spend a long time reading (66k words plus
ten images), hold the entire result in context, and emit one large file at the very end. That final
write is the only durable output, and it is the part that never happened.

**What worked:** doing it in the main session with the file written as the work completed. The
first census landed in one pass and verified at 64 citations; the second followed.

**Why this matters more than it looks:** `CLAUDE.md`'s orchestration rule says to delegate execution
to Sonnet subagents, and that rule is right for bounded, well-specified execution. It is *not* a good
fit for open-ended corpus reads whose value is entirely in a single terminal artifact. Three lost
dispatches cost more than the task itself.

**How to apply:**

- **Judge by the write pattern, not the task size.** Delegate when the agent produces incremental,
  checkpointed output or many small edits. Keep it in the main session when the deliverable is one
  large document written at the end.
- If delegating anyway, **instruct the agent to create the file with its header first and append each
  section as it completes**, so a kill costs one section rather than everything.
- **Never report a dispatched agent's findings before its completion notification arrives** — twice
  here the agent's last visible words implied it was about to write, and it never did.
- Prefer a **resumable** shape generally — this is the same instinct as the user's standing directive
  that long-running scripts pick up where they left off.

Related: [[opus-expanded-role]] for who orchestrates; [[coverage-claims-need-enumeration]] for why
these corpus reads are long in the first place.
