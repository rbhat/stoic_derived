import { afterEach, describe, expect, it, vi } from "vitest";

import { ContractError, dashboardApi } from "./api";
import { blockedLedger } from "./test/fixtures";

describe("dashboardApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fails closed when a successful payload violates the runtime contract", async () => {
    const invalid = structuredClone(blockedLedger) as Record<string, unknown>;
    invalid["private_fixture"] = true;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(invalid), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(dashboardApi.ledger()).rejects.toBeInstanceOf(ContractError);
  });

  it("sends same-origin cookies and the session CSRF token on mutations", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          schema_version: "dashboard-api/v1",
          user_id: "user-2",
          email: "viewer@example.com",
          role: "viewer",
          enabled: false,
          primary: false,
          identity_bound: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await dashboardApi.updateUser("csrf-value", "user-2", { enabled: false });

    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/admin/users/user-2");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-value");
    expect(init.method).toBe("PATCH");
  });
});
