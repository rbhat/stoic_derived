import { describe, expect, it } from "vitest";

import { ledgerSnapshotSchema, operationsStatusSchema } from "./schemas";
import { operationsStatus, readyLedger } from "./test/fixtures";

describe("dashboard runtime contracts", () => {
  it("accepts exact v1 ledger and operations contracts", () => {
    expect(ledgerSnapshotSchema.parse(readyLedger)).toEqual(readyLedger);
    expect(operationsStatusSchema.parse(operationsStatus)).toEqual(operationsStatus);
  });

  it("rejects fabricated dollar P/L and unknown response fields", () => {
    const candidate = structuredClone(readyLedger) as Record<string, unknown>;
    const ledger = candidate["ledger"] as Record<string, unknown>;
    const closed = ledger["closed_observations"] as Record<string, unknown>[];
    closed[0] = { ...closed[0], observed_pnl_dollars: 400 };
    expect(ledgerSnapshotSchema.safeParse(candidate).success).toBe(false);
  });

  it("rejects any claim that execution occurred", () => {
    const candidate = structuredClone(readyLedger) as Record<string, unknown>;
    const ledger = candidate["ledger"] as Record<string, unknown>;
    ledger["execution"] = true;
    expect(ledgerSnapshotSchema.safeParse(candidate).success).toBe(false);
  });

  it("requires canonical UTC timestamps instead of local offsets", () => {
    const candidate = structuredClone(readyLedger) as Record<string, unknown>;
    candidate["generated_at_utc"] = "2026-07-24T13:04:00-07:00";
    expect(ledgerSnapshotSchema.safeParse(candidate).success).toBe(false);
  });
});
