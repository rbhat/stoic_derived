import { describe, expect, it } from "vitest";

import { formatHold, formatPacific, formatPnlTicks } from "./format";

describe("edge formatting", () => {
  it("shows Pacific daylight and standard time while retaining precise values", () => {
    expect(formatPacific("2026-07-24T20:58:00Z")).toContain("PDT");
    expect(formatPacific("2026-12-24T21:58:00Z")).toContain("PST");
  });

  it("formats observational units without money", () => {
    expect(formatPnlTicks(20)).toBe("+20 ticks");
    expect(formatPnlTicks(-40)).toBe("-40 ticks");
    expect(formatHold(3_661)).toBe("1h 1m");
  });
});
