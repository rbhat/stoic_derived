import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

import {
  adminSession,
  auditRecords,
  operationsStatus,
  primaryAdmin,
  readyLedger,
  rotations,
  testAuthConfig,
} from "../src/test/fixtures";

const operationResult = {
  schema_version: "dashboard-api/v1",
  operation_id: "operation-1",
  operation: "drive_publish",
  state: "complete",
  detail: "Committed outbox events were published and Drive authority was re-verified",
  affected_count: 0,
  observed_at_utc: "2026-07-24T20:05:00Z",
  execution: false,
  orders_placed: 0,
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/auth/config") {
      await json(route, testAuthConfig);
      return;
    }
    if (path === "/api/v1/session") {
      await json(route, adminSession);
      return;
    }
    if (path === "/api/v1/ledger") {
      await json(route, readyLedger);
      return;
    }
    if (path === "/api/v1/operations/status") {
      await json(route, operationsStatus);
      return;
    }
    if (path === "/api/v1/admin/users") {
      await json(route, { schema_version: "dashboard-api/v1", users: [primaryAdmin] });
      return;
    }
    if (path === "/api/v1/admin/key-rotations") {
      await json(route, { schema_version: "dashboard-api/v1", rotations });
      return;
    }
    if (path === "/api/v1/admin/audit") {
      await json(route, { schema_version: "dashboard-api/v1", records: auditRecords });
      return;
    }
    if (
      path === "/api/v1/admin/operations/drive-publish" &&
      route.request().method() === "POST"
    ) {
      await json(route, operationResult);
      return;
    }
    await json(route, { detail: `Unhandled test route ${path}` }, 500);
  });
}

test.beforeEach(async ({ page }) => {
  await installApi(page);
});

test("renders verified lifecycle and operational evidence accessibly", async ({
  page,
}, testInfo) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "System truth, without execution" }),
  ).toBeVisible();
  await expect(page.getByText("13:58", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Open observations" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Closed observations" })).toBeVisible();
  await expect(page.getByText("+80 ticks")).toBeVisible();
  await expect(page.getByText("+2R")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Last successful Drive activity" }),
  ).toBeVisible();
  await expect(page.getByText("6 observations")).toBeVisible();
  await expect(page.getByText("Protected in SQLite")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/\$\s*\d/u);

  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious",
    ),
  ).toEqual([]);
  if (process.env["CAPTURE_UI"] === "1") {
    await page.screenshot({
      path: `/tmp/stoic-dashboard-${testInfo.project.name}.png`,
      fullPage: true,
    });
  }
});

test("keeps publication behind an explicit confirmation step", async ({ page }) => {
  await page.goto("/");
  const publish = page.getByRole("button", { name: "Publish committed outbox" });
  await publish.click();
  await expect(
    page.getByRole("button", { name: "Confirm outbox publication" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Confirm outbox publication" }).click();
  await expect(page.getByText(/Committed outbox events were published/u).first()).toBeVisible();
});

test("exposes a keyboard skip link", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "System truth, without execution" }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to observational ledger" });
  await expect(skip).toBeFocused();
  await skip.press("Enter");
  await expect(page).toHaveURL(/#ledger$/u);
});
