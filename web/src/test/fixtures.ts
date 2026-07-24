import type {
  AuditRecord,
  AuthConfig,
  LedgerSnapshot,
  Observation,
  OperationsStatus,
  Rotation,
  Session,
  User,
} from "../schemas";

export const testAuthConfig = {
  schema_version: "dashboard-api/v1",
  client_id: "test-web-client.apps.googleusercontent.com",
  login_uri: "https://dashboard.example.test/api/v1/auth/google",
  ux_mode: "redirect",
} satisfies AuthConfig;

export const primaryAdmin = {
  schema_version: "dashboard-api/v1",
  user_id: "user-primary",
  email: "rajeevmbhat@gmail.com",
  role: "admin",
  enabled: true,
  primary: true,
  identity_bound: true,
} satisfies User;

export const viewer = {
  schema_version: "dashboard-api/v1",
  user_id: "user-viewer",
  email: "viewer@example.com",
  role: "viewer",
  enabled: true,
  primary: false,
  identity_bound: true,
} satisfies User;

export const adminSession = {
  schema_version: "dashboard-api/v1",
  user: primaryAdmin,
  csrf_token: "csrf-token-with-at-least-thirty-two-characters",
  expires_at_utc: "2026-07-25T20:00:00Z",
} satisfies Session;

export const viewerSession = {
  ...adminSession,
  user: viewer,
} satisfies Session;

const baseObservation: Omit<Observation, "signal_id" | "state"> = {
  instrument: "NQ",
  signal_type: "Day",
  direction: "long",
  setup_type: "opening-drive",
  confidence: 78,
  signal_ts_utc: "2026-07-24T16:45:00Z",
  planned_entry_price_ticks: 79_200,
  planned_stop_price_ticks: 79_160,
  planned_target_price_ticks: 79_280,
  entry_observed_ts_utc: null,
  entry_observed_price_ticks: null,
  close_observed_ts_utc: null,
  close_observed_price_ticks: null,
  terminal_reason: null,
  observed_pnl_ticks: null,
  observed_pnl_r: null,
  hold_seconds: null,
  conflicts: [],
  execution: false,
  orders_placed: 0,
};

export const openObservations = [
  {
    ...baseObservation,
    signal_id: "1".repeat(64),
    state: "pending",
  },
  {
    ...baseObservation,
    signal_id: "2".repeat(64),
    instrument: "ES",
    signal_type: "Scalp",
    state: "active",
    direction: "short",
    setup_type: "failed-breakout",
    signal_ts_utc: "2026-07-24T17:03:00Z",
    planned_entry_price_ticks: 25_400,
    planned_stop_price_ticks: 25_420,
    planned_target_price_ticks: 25_360,
    entry_observed_ts_utc: "2026-07-24T17:05:00Z",
    entry_observed_price_ticks: 25_400,
    hold_seconds: 3_540,
  },
] satisfies readonly Observation[];

export const closedObservations = [
  {
    ...baseObservation,
    signal_id: "3".repeat(64),
    state: "closed",
    entry_observed_ts_utc: "2026-07-24T16:48:00Z",
    entry_observed_price_ticks: 79_200,
    close_observed_ts_utc: "2026-07-24T17:12:00Z",
    close_observed_price_ticks: 79_280,
    terminal_reason: "target_observed",
    observed_pnl_ticks: 80,
    observed_pnl_r: { numerator: 2, denominator: 1, display: "2" },
    hold_seconds: 1_440,
  },
  {
    ...baseObservation,
    signal_id: "4".repeat(64),
    state: "closed",
    direction: "short",
    entry_observed_ts_utc: "2026-07-24T18:00:00Z",
    entry_observed_price_ticks: 79_200,
    close_observed_ts_utc: "2026-07-24T18:10:00Z",
    close_observed_price_ticks: 79_240,
    terminal_reason: "stop_observed",
    observed_pnl_ticks: -40,
    observed_pnl_r: { numerator: -1, denominator: 1, display: "-1" },
    hold_seconds: 600,
  },
  {
    ...baseObservation,
    signal_id: "5".repeat(64),
    state: "closed",
    signal_type: "Swing",
    entry_observed_ts_utc: "2026-07-24T20:00:00Z",
    entry_observed_price_ticks: 79_200,
    close_observed_ts_utc: "2026-07-24T20:58:00Z",
    close_observed_price_ticks: 79_220,
    terminal_reason: "session_flatten_observed",
    observed_pnl_ticks: 20,
    observed_pnl_r: { numerator: 1, denominator: 2, display: "0.5" },
    hold_seconds: 3_480,
  },
] satisfies readonly Observation[];

export const unresolvedObservations = [
  {
    ...baseObservation,
    signal_id: "6".repeat(64),
    state: "unresolved",
    terminal_reason: "conflicting_terminal_evidence",
    conflicts: [
      {
        code: "terminal_conflict",
        detail: "Stop and target observations share the same authority sequence.",
      },
    ],
  },
] satisfies readonly Observation[];

export const readyLedger = {
  schema_version: "dashboard-api/v1",
  generated_at_utc: "2026-07-24T20:04:00Z",
  ledger: {
    status: "ready",
    open_observations: openObservations,
    closed_observations: closedObservations,
    unresolved_observations: unresolvedObservations,
    source: "verified_drive_plus_undelivered_outbox",
    execution: false,
    orders_placed: 0,
  },
} satisfies LedgerSnapshot;

export const blockedLedger = {
  schema_version: "dashboard-api/v1",
  generated_at_utc: "2026-07-24T20:04:00Z",
  ledger: {
    status: "blocked",
    blockers: ["SP0 release is not configured"],
    observation_count: 0,
    execution: false,
    orders_placed: 0,
  },
} satisfies LedgerSnapshot;

export const operationsStatus = {
  schema_version: "dashboard-api/v1",
  generated_at_utc: "2026-07-24T20:04:00Z",
  process_started_at_utc: "2026-07-24T19:00:00Z",
  components: [
    {
      component: "api",
      state: "running",
      detail: "Typed JSON/control API is running",
      observed_at_utc: "2026-07-24T20:04:00Z",
    },
    {
      component: "release",
      state: "ready",
      detail: "Signed release readiness passed",
      observed_at_utc: "2026-07-24T20:04:00Z",
    },
    {
      component: "drive",
      state: "ready",
      detail: "Verified Drive authority is available",
      observed_at_utc: "2026-07-24T20:04:00Z",
    },
    {
      component: "market_data",
      state: "unknown",
      detail: "Connection test has not run",
      observed_at_utc: null,
    },
    {
      component: "drive_sync",
      state: "ready",
      detail: "Most recent verified refresh completed",
      observed_at_utc: "2026-07-24T20:03:00Z",
    },
    {
      component: "watchdog",
      state: "ready",
      detail: "Current session cutoff evidence is verified",
      observed_at_utc: "2026-07-24T20:04:00Z",
    },
  ],
  outbox: {
    state: "ready",
    pending_count: 0,
    acknowledged_count: 6,
    maximum_pending_attempts: 0,
    detail: "No committed events await Drive acknowledgement",
  },
  drive_activity: {
    refresh: {
      observed_at_utc: "2026-07-24T20:03:00Z",
      affected_count: 6,
    },
    publish: {
      observed_at_utc: null,
      affected_count: 0,
    },
  },
  execution: false,
  orders_placed: 0,
} satisfies OperationsStatus;

export const rotations = [
  {
    schema_version: "dashboard-api/v1",
    rotation_id: "rotation-1",
    target: "databento",
    state: "requested",
    requested_at_utc: "2026-07-24T19:30:00Z",
    updated_at_utc: "2026-07-24T19:30:00Z",
    requested_by_email: primaryAdmin.email,
    detail: "Awaiting externally updated credential verification",
  },
] satisfies readonly Rotation[];

export const auditRecords = [
  {
    audit_id: 1,
    occurred_at_utc: "2026-07-24T19:30:00Z",
    actor_email: primaryAdmin.email,
    action: "key_rotation_requested",
    resource_type: "key_rotation",
    resource_id: "rotation-1",
    request_id: "1234567890abcdef1234567890abcdef",
    before: null,
    after: { state: "requested" },
    record_hash: "a".repeat(64),
  },
] satisfies readonly AuditRecord[];
