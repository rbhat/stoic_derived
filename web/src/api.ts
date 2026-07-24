import type { ZodType } from "zod";

import {
  auditListSchema,
  authConfigSchema,
  ledgerSnapshotSchema,
  messageSchema,
  operationSchema,
  operationsStatusSchema,
  rotationListSchema,
  rotationSchema,
  sessionSchema,
  userListSchema,
  userSchema,
  type AuditRecord,
  type AuthConfig,
  type LedgerSnapshot,
  type Operation,
  type OperationsStatus,
  type Rotation,
  type Session,
  type User,
} from "./schemas";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class ContractError extends Error {
  constructor(path: string) {
    super(`The API response for ${path} did not match dashboard-api/v1.`);
    this.name = "ContractError";
  }
}

async function request<T>(
  path: string,
  schema: ZodType<T>,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers,
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "The dashboard request failed.";
    throw new ApiError(detail, response.status);
  }
  const decoded = schema.safeParse(payload);
  if (!decoded.success) {
    throw new ContractError(path);
  }
  return decoded.data;
}

function mutationHeaders(csrfToken: string): HeadersInit {
  return { "X-CSRF-Token": csrfToken };
}

export const dashboardApi = {
  authConfig: (): Promise<AuthConfig> =>
    request("/api/v1/auth/config", authConfigSchema),
  session: (): Promise<Session> => request("/api/v1/session", sessionSchema),
  logout: (csrfToken: string): Promise<{ message: string }> =>
    request("/api/v1/session/logout", messageSchema, {
      method: "POST",
      headers: mutationHeaders(csrfToken),
    }),
  ledger: (): Promise<LedgerSnapshot> =>
    request("/api/v1/ledger", ledgerSnapshotSchema),
  operations: (): Promise<OperationsStatus> =>
    request("/api/v1/operations/status", operationsStatusSchema),
  users: async (): Promise<readonly User[]> =>
    (await request("/api/v1/admin/users", userListSchema)).users,
  inviteUser: (csrfToken: string, email: string, role: "admin" | "viewer"): Promise<User> =>
    request("/api/v1/admin/users", userSchema, {
      method: "POST",
      headers: mutationHeaders(csrfToken),
      body: JSON.stringify({ email, role }),
    }),
  updateUser: (
    csrfToken: string,
    userId: string,
    change: { role?: "admin" | "viewer"; enabled?: boolean },
  ): Promise<User> =>
    request(`/api/v1/admin/users/${encodeURIComponent(userId)}`, userSchema, {
      method: "PATCH",
      headers: mutationHeaders(csrfToken),
      body: JSON.stringify(change),
    }),
  removeUser: (csrfToken: string, userId: string): Promise<{ message: string }> =>
    request(`/api/v1/admin/users/${encodeURIComponent(userId)}`, messageSchema, {
      method: "DELETE",
      headers: mutationHeaders(csrfToken),
    }),
  testConnection: (
    csrfToken: string,
    target: "market_data" | "drive",
  ): Promise<Operation> =>
    request("/api/v1/admin/operations/connection-tests", operationSchema, {
      method: "POST",
      headers: mutationHeaders(csrfToken),
      body: JSON.stringify({ target }),
    }),
  refreshDrive: (csrfToken: string): Promise<Operation> =>
    request("/api/v1/admin/operations/drive-refresh", operationSchema, {
      method: "POST",
      headers: mutationHeaders(csrfToken),
    }),
  publishDrive: (csrfToken: string): Promise<Operation> =>
    request("/api/v1/admin/operations/drive-publish", operationSchema, {
      method: "POST",
      headers: mutationHeaders(csrfToken),
    }),
  rotations: async (): Promise<readonly Rotation[]> =>
    (await request("/api/v1/admin/key-rotations", rotationListSchema)).rotations,
  createRotation: (csrfToken: string): Promise<Rotation> =>
    request("/api/v1/admin/key-rotations", rotationSchema, {
      method: "POST",
      headers: mutationHeaders(csrfToken),
      body: JSON.stringify({ target: "databento" }),
    }),
  verifyRotation: (csrfToken: string, rotationId: string): Promise<Rotation> =>
    request(
      `/api/v1/admin/key-rotations/${encodeURIComponent(rotationId)}/verify`,
      rotationSchema,
      { method: "POST", headers: mutationHeaders(csrfToken) },
    ),
  cancelRotation: (csrfToken: string, rotationId: string): Promise<Rotation> =>
    request(
      `/api/v1/admin/key-rotations/${encodeURIComponent(rotationId)}/cancel`,
      rotationSchema,
      { method: "POST", headers: mutationHeaders(csrfToken) },
    ),
  audit: async (): Promise<readonly AuditRecord[]> =>
    (await request("/api/v1/admin/audit?limit=50", auditListSchema)).records,
};
