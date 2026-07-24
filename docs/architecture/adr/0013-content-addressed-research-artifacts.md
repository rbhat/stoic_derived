# ADR-0013: Publish Content-addressed Research Artifacts

- Status: Accepted
- Date: 2026-07-24

## Context

Research results are unsafe to compare when releases, data, assumptions,
partitions, code schemas, or denominators drift. Wall-clock run IDs also make
identical experiments appear different.

## Decision

SP3 derives a deterministic plan ID from canonical input batch identities,
release identity, simulation policy, chronological replay plan, and pinned
algorithm/schema versions. Ordered output hashes plus that plan ID determine
the run ID. Every JSON/JSONL artifact is hashed and counted in a manifest that
declares `execution: false` and `orders_placed: 0`. The manifest is excluded
from its own digest to avoid recursive identity. Explicit record and byte
bounds fail closed before publication.

The final target must be absent. SP3 writes and synchronizes a sibling
temporary directory, writes the manifest last, and uses the host's atomic
no-replace rename primitive to publish the directory. Every existing target,
including one appearing during publication, is refused. An unsupported host
fails closed instead of using an overwrite-capable fallback.

## Consequences

- Identical experiments are byte-identical across Mac, Windows/WSL, and GCP.
- Any data, rule, cost, or fold change produces a different comparable plan.
- Reports retain suppressions, unresolved observations, and limitations.

## Compliance

Input-order rejection, timezone, tamper, overwrite, bounds, hash, and manifest
reconciliation tests verify the artifact contract.
