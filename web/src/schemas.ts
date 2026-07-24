import { z } from "zod";

const schemaVersion = z.literal("dashboard-api/v1");
const utcTimestamp = z
  .iso.datetime({ offset: true })
  .refine((value) => value.endsWith("Z"), "Timestamp must use canonical UTC Z notation");
const role = z.enum(["admin", "viewer"]);
const componentState = z.enum([
  "running",
  "ready",
  "blocked",
  "degraded",
  "unknown",
  "stale",
]);

export const authConfigSchema = z
  .object({
    schema_version: schemaVersion,
    client_id: z.string().min(1),
    login_uri: z.url(),
    ux_mode: z.literal("redirect"),
  })
  .strict();

export const userSchema = z
  .object({
    schema_version: schemaVersion,
    user_id: z.string().min(1),
    email: z.email(),
    role,
    enabled: z.boolean(),
    primary: z.boolean(),
    identity_bound: z.boolean(),
  })
  .strict();

export const sessionSchema = z
  .object({
    schema_version: schemaVersion,
    user: userSchema,
    csrf_token: z.string().min(32),
    expires_at_utc: utcTimestamp,
  })
  .strict();

const exactRSchema = z
  .object({
    numerator: z.number().int(),
    denominator: z.number().int().positive(),
    display: z.string().min(1),
  })
  .strict();

const conflictSchema = z
  .object({
    code: z.string().min(1),
    detail: z.string().min(1),
  })
  .strict();

export const observationSchema = z
  .object({
    signal_id: z.string().length(64),
    instrument: z.enum(["NQ", "ES"]),
    signal_type: z.enum(["Scalp", "Day", "Swing", "Position"]),
    state: z.enum(["pending", "active", "closed", "unresolved"]),
    direction: z.enum(["long", "short"]),
    setup_type: z.string().min(1),
    confidence: z.number().int().min(0).max(100),
    signal_ts_utc: utcTimestamp,
    planned_entry_price_ticks: z.number().int().positive().safe(),
    planned_stop_price_ticks: z.number().int().positive().safe(),
    planned_target_price_ticks: z.number().int().positive().safe(),
    entry_observed_ts_utc: utcTimestamp.nullable(),
    entry_observed_price_ticks: z.number().int().positive().safe().nullable(),
    close_observed_ts_utc: utcTimestamp.nullable(),
    close_observed_price_ticks: z.number().int().positive().safe().nullable(),
    terminal_reason: z.string().min(1).nullable(),
    observed_pnl_ticks: z.number().int().safe().nullable(),
    observed_pnl_r: exactRSchema.nullable(),
    hold_seconds: z.number().int().nonnegative().safe().nullable(),
    conflicts: z.array(conflictSchema),
    execution: z.literal(false),
    orders_placed: z.literal(0),
  })
  .strict();

const ledgerReadySchema = z
  .object({
    status: z.literal("ready"),
    open_observations: z.array(observationSchema),
    closed_observations: z.array(observationSchema),
    unresolved_observations: z.array(observationSchema),
    source: z.literal("verified_drive_plus_undelivered_outbox"),
    execution: z.literal(false),
    orders_placed: z.literal(0),
  })
  .strict();

const ledgerBlockedSchema = z
  .object({
    status: z.literal("blocked"),
    blockers: z.array(z.string().min(1)).min(1),
    observation_count: z.literal(0),
    execution: z.literal(false),
    orders_placed: z.literal(0),
  })
  .strict();

const ledgerErrorSchema = z
  .object({
    status: z.literal("error"),
    detail: z.string().min(1),
    observation_count: z.literal(0),
    execution: z.literal(false),
    orders_placed: z.literal(0),
  })
  .strict();

export const ledgerSnapshotSchema = z
  .object({
    schema_version: schemaVersion,
    generated_at_utc: utcTimestamp,
    ledger: z.discriminatedUnion("status", [
      ledgerReadySchema,
      ledgerBlockedSchema,
      ledgerErrorSchema,
    ]),
  })
  .strict();

const componentStatusSchema = z
  .object({
    component: z.string().min(1),
    state: componentState,
    detail: z.string().min(1),
    observed_at_utc: utcTimestamp.nullable(),
  })
  .strict();

export const operationsStatusSchema = z
  .object({
    schema_version: schemaVersion,
    generated_at_utc: utcTimestamp,
    process_started_at_utc: utcTimestamp,
    components: z.array(componentStatusSchema),
    outbox: z
      .object({
        state: componentState,
        pending_count: z.number().int().nonnegative(),
        acknowledged_count: z.number().int().nonnegative(),
        maximum_pending_attempts: z.number().int().nonnegative(),
        detail: z.string().min(1),
      })
      .strict(),
    drive_activity: z
      .object({
        refresh: z
          .object({
            observed_at_utc: utcTimestamp.nullable(),
            affected_count: z.number().int().nonnegative(),
          })
          .strict(),
        publish: z
          .object({
            observed_at_utc: utcTimestamp.nullable(),
            affected_count: z.number().int().nonnegative(),
          })
          .strict(),
      })
      .strict(),
    execution: z.literal(false),
    orders_placed: z.literal(0),
  })
  .strict();

export const userListSchema = z
  .object({
    schema_version: schemaVersion,
    users: z.array(userSchema),
  })
  .strict();

export const operationSchema = z
  .object({
    schema_version: schemaVersion,
    operation_id: z.string().min(1),
    operation: z.string().min(1),
    state: z.enum(["complete", "blocked", "failed"]),
    detail: z.string().min(1),
    affected_count: z.number().int().nonnegative(),
    observed_at_utc: utcTimestamp,
    execution: z.literal(false),
    orders_placed: z.literal(0),
  })
  .strict();

export const rotationSchema = z
  .object({
    schema_version: schemaVersion,
    rotation_id: z.string().min(1),
    target: z.literal("databento"),
    state: z.enum(["requested", "verified", "failed", "cancelled"]),
    requested_at_utc: utcTimestamp,
    updated_at_utc: utcTimestamp,
    requested_by_email: z.email(),
    detail: z.string().min(1),
  })
  .strict();

export const rotationListSchema = z
  .object({
    schema_version: schemaVersion,
    rotations: z.array(rotationSchema),
  })
  .strict();

const auditRecordSchema = z
  .object({
    audit_id: z.number().int().positive(),
    occurred_at_utc: utcTimestamp,
    actor_email: z.string().min(1),
    action: z.string().min(1),
    resource_type: z.string().min(1),
    resource_id: z.string().min(1),
    request_id: z.string().min(1),
    before: z.record(z.string(), z.unknown()).nullable(),
    after: z.record(z.string(), z.unknown()).nullable(),
    record_hash: z.string().length(64),
  })
  .strict();

export const auditListSchema = z
  .object({
    schema_version: schemaVersion,
    records: z.array(auditRecordSchema),
  })
  .strict();

export const messageSchema = z
  .object({
    schema_version: schemaVersion,
    message: z.string().min(1),
  })
  .strict();

export type AuthConfig = z.infer<typeof authConfigSchema>;
export type User = z.infer<typeof userSchema>;
export type Session = z.infer<typeof sessionSchema>;
export type Observation = z.infer<typeof observationSchema>;
export type LedgerSnapshot = z.infer<typeof ledgerSnapshotSchema>;
export type OperationsStatus = z.infer<typeof operationsStatusSchema>;
export type Operation = z.infer<typeof operationSchema>;
export type Rotation = z.infer<typeof rotationSchema>;
export type AuditRecord = z.infer<typeof auditRecordSchema>;
