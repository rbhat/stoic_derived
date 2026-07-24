import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { dashboardApi } from "./api";
import { App } from "./App";
import {
  adminSession,
  auditRecords,
  operationsStatus,
  primaryAdmin,
  readyLedger,
  rotations,
  testAuthConfig,
  viewerSession,
} from "./test/fixtures";

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    dashboardApi: {
      authConfig: vi.fn(),
      session: vi.fn(),
      logout: vi.fn(),
      ledger: vi.fn(),
      operations: vi.fn(),
      users: vi.fn(),
      inviteUser: vi.fn(),
      updateUser: vi.fn(),
      removeUser: vi.fn(),
      testConnection: vi.fn(),
      refreshDrive: vi.fn(),
      publishDrive: vi.fn(),
      rotations: vi.fn(),
      createRotation: vi.fn(),
      verifyRotation: vi.fn(),
      cancelRotation: vi.fn(),
      audit: vi.fn(),
    },
  };
});

function commonMocks() {
  vi.mocked(dashboardApi.authConfig).mockResolvedValue(testAuthConfig);
  vi.mocked(dashboardApi.ledger).mockResolvedValue(readyLedger);
  vi.mocked(dashboardApi.operations).mockResolvedValue(operationsStatus);
}

describe("App authorization surfaces", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    commonMocks();
  });

  it("keeps viewer access read-only", async () => {
    vi.mocked(dashboardApi.session).mockResolvedValue(viewerSession);
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "System truth, without execution" }),
    ).toBeVisible();
    expect(screen.getByText("viewer@example.com")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Last successful Drive activity" })).toBeVisible();
    expect(screen.getByText("6 observations")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Management and audit" })).toBeNull();
    expect(dashboardApi.users).not.toHaveBeenCalled();
    expect(dashboardApi.audit).not.toHaveBeenCalled();
  });

  it("shows protected primary-admin evidence and constrained controls to admins", async () => {
    vi.mocked(dashboardApi.session).mockResolvedValue(adminSession);
    vi.mocked(dashboardApi.users).mockResolvedValue([primaryAdmin]);
    vi.mocked(dashboardApi.rotations).mockResolvedValue(rotations);
    vi.mocked(dashboardApi.audit).mockResolvedValue(auditRecords);
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Management and audit" }),
    ).toBeVisible();
    expect(screen.getByText("Immutable primary administrator")).toBeVisible();
    expect(screen.getByText("Protected in SQLite")).toBeVisible();
    expect(
      screen.queryByRole("combobox", { name: `Role for ${primaryAdmin.email}` }),
    ).toBeNull();
    expect(screen.getByRole("button", { name: "Test market data" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Publish committed outbox" })).toBeEnabled();
  });

  it("announces a contract-safe application error", async () => {
    vi.mocked(dashboardApi.authConfig).mockRejectedValue(
      new Error("The public API contract is unavailable."),
    );
    render(<App />);
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "Dashboard unavailable" }),
      ).toBeVisible(),
    );
    expect(screen.getByText("The public API contract is unavailable.")).toBeVisible();
  });
});
