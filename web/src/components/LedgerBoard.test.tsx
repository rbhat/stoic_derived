import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { blockedLedger, readyLedger } from "../test/fixtures";
import { LedgerBoard } from "./LedgerBoard";

describe("LedgerBoard", () => {
  it("separates lifecycle sections and displays only exact observational units", () => {
    const { container } = render(<LedgerBoard snapshot={readyLedger} />);

    expect(screen.getByRole("heading", { name: "Open observations" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Closed observations" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Unresolved observations" })).toBeVisible();
    expect(screen.getByText("+80 ticks")).toBeVisible();
    expect(screen.getByText("+2R")).toBeVisible();
    expect(screen.getAllByText(/Session flatten/u).length).toBeGreaterThan(0);
    expect(screen.getByText(/terminal_conflict/u)).toBeVisible();
    expect(container).not.toHaveTextContent(/\$\s*\d/u);
    expect(container).toHaveTextContent("UTC 2026-07-24T20:58:00Z");
  });

  it("provides text equivalents for both lifecycle charts", () => {
    render(<LedgerBoard snapshot={readyLedger} />);
    const openEquivalent = screen.getByRole("list", {
      name: "Open observations by state and signal type text equivalent",
    });
    const closedEquivalent = screen.getByRole("list", {
      name: "Closed observations by terminal reason text equivalent",
    });
    expect(within(openEquivalent).getByText("Active · Scalp")).toBeVisible();
    expect(within(closedEquivalent).getByText("Target observed")).toBeVisible();
  });

  it("renders zero records when the release boundary is blocked", () => {
    render(<LedgerBoard snapshot={blockedLedger} />);
    expect(
      screen.getByRole("heading", { name: "Production remains blocked at zero" }),
    ).toBeVisible();
    expect(screen.getByText("SP0 release is not configured")).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
