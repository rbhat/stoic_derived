import { useState, type FormEvent } from "react";

import { dashboardApi } from "../api";
import { formatPacific, sentenceCase } from "../format";
import type { AuditRecord, Operation, Rotation, User } from "../schemas";

interface AdminConsoleProps {
  readonly csrfToken: string;
  readonly users: readonly User[];
  readonly rotations: readonly Rotation[];
  readonly audit: readonly AuditRecord[];
  readonly onChanged: (message: string) => Promise<void>;
  readonly onFailure: (message: string) => void;
}

function failureMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The control request failed.";
}

function OperationResult({ result }: { readonly result: Operation | null }) {
  if (result === null) {
    return null;
  }
  return (
    <div className={`operation-result operation-${result.state}`} role="status">
      <strong>
        {sentenceCase(result.operation)} · {sentenceCase(result.state)}
      </strong>
      <p>{result.detail}</p>
      <span>
        {result.affected_count} affected · {formatPacific(result.observed_at_utc)}
      </span>
    </div>
  );
}

export function AdminConsole({
  csrfToken,
  users,
  rotations,
  audit,
  onChanged,
  onFailure,
}: AdminConsoleProps) {
  const [busy, setBusy] = useState("");
  const [operationResult, setOperationResult] = useState<Operation | null>(null);
  const [publishArmed, setPublishArmed] = useState(false);
  const [removeArmed, setRemoveArmed] = useState("");

  const run = async <T,>(
    key: string,
    action: () => Promise<T>,
    message: (result: T) => string,
  ) => {
    setBusy(key);
    onFailure("");
    try {
      const result = await action();
      await onChanged(message(result));
    } catch (error) {
      onFailure(failureMessage(error));
    } finally {
      setBusy("");
    }
  };

  const runOperation = async (
    key: string,
    action: () => Promise<Operation>,
  ) => {
    setBusy(key);
    setOperationResult(null);
    onFailure("");
    try {
      const result = await action();
      setOperationResult(result);
      await onChanged(`${sentenceCase(result.operation)}: ${result.detail}`);
    } catch (error) {
      onFailure(failureMessage(error));
    } finally {
      setBusy("");
      setPublishArmed(false);
    }
  };

  return (
    <section id="management" className="ruled-section" aria-labelledby="management-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Administrator boundary</p>
          <h2 id="management-title">Management and audit</h2>
        </div>
        <p className="source-label">
          Every mutation is CSRF-protected
          <span>Every intent and result is append-only evidence</span>
        </p>
      </div>

      <div className="management-grid">
        <article className="control-panel" aria-labelledby="connections-title">
          <h3 id="connections-title">Connection tests</h3>
          <p>Bounded, read-only probes. No control accepts a URL or credential.</p>
          <div className="button-row">
            <button
              type="button"
              disabled={busy !== ""}
              onClick={() =>
                void runOperation("market", () =>
                  dashboardApi.testConnection(csrfToken, "market_data"),
                )
              }
            >
              {busy === "market" ? "Testing…" : "Test market data"}
            </button>
            <button
              type="button"
              disabled={busy !== ""}
              onClick={() =>
                void runOperation("drive-test", () =>
                  dashboardApi.testConnection(csrfToken, "drive"),
                )
              }
            >
              {busy === "drive-test" ? "Testing…" : "Test Drive"}
            </button>
          </div>
        </article>

        <article className="control-panel" aria-labelledby="drive-title">
          <h3 id="drive-title">Drive authority</h3>
          <p>
            Refresh is read-only. Publish retries only committed outbox events, then
            verifies Drive authority.
          </p>
          <div className="button-row">
            <button
              type="button"
              disabled={busy !== ""}
              onClick={() =>
                void runOperation("refresh", () => dashboardApi.refreshDrive(csrfToken))
              }
            >
              {busy === "refresh" ? "Refreshing…" : "Refresh verified ledger"}
            </button>
            <button
              className={publishArmed ? "warning-button" : "secondary-button"}
              type="button"
              disabled={busy !== ""}
              onClick={() => {
                if (!publishArmed) {
                  setPublishArmed(true);
                  return;
                }
                void runOperation("publish", () => dashboardApi.publishDrive(csrfToken));
              }}
            >
              {busy === "publish"
                ? "Publishing…"
                : publishArmed
                  ? "Confirm outbox publication"
                  : "Publish committed outbox"}
            </button>
            {publishArmed && busy === "" && (
              <button
                className="quiet-button"
                type="button"
                onClick={() => setPublishArmed(false)}
              >
                Cancel
              </button>
            )}
          </div>
        </article>
      </div>

      <OperationResult result={operationResult} />

      <UserManagement
        csrfToken={csrfToken}
        users={users}
        busy={busy}
        removeArmed={removeArmed}
        setRemoveArmed={setRemoveArmed}
        run={run}
      />
      <RotationManagement
        csrfToken={csrfToken}
        rotations={rotations}
        busy={busy}
        run={run}
      />
      <AuditEvidence records={audit} />
    </section>
  );
}

interface RunControl {
  <T>(key: string, action: () => Promise<T>, message: (result: T) => string): Promise<void>;
}

function UserManagement({
  csrfToken,
  users,
  busy,
  removeArmed,
  setRemoveArmed,
  run,
}: {
  readonly csrfToken: string;
  readonly users: readonly User[];
  readonly busy: string;
  readonly removeArmed: string;
  readonly setRemoveArmed: (userId: string) => void;
  readonly run: RunControl;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "viewer">("viewer");

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void run(
      "invite",
      () => dashboardApi.inviteUser(csrfToken, email, role),
      (user) => {
        setEmail("");
        return `${user.email} was invited as ${user.role}.`;
      },
    );
  };

  return (
    <article className="management-section" aria-labelledby="users-title">
      <div className="ledger-heading">
        <div>
          <h3 id="users-title">Invite-only users</h3>
          <p>Role and enabled-state changes revoke affected sessions immediately.</p>
        </div>
        <span>{users.length} users</span>
      </div>
      <form className="invite-form" onSubmit={submit}>
        <label>
          Google account email
          <input
            type="email"
            autoComplete="email"
            required
            maxLength={320}
            value={email}
            onChange={(event) => setEmail(event.currentTarget.value)}
          />
        </label>
        <label>
          Initial role
          <select
            value={role}
            onChange={(event) =>
              setRole(event.currentTarget.value === "admin" ? "admin" : "viewer")
            }
          >
            <option value="viewer">Viewer · read only</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <button type="submit" disabled={busy !== ""}>
          {busy === "invite" ? "Inviting…" : "Invite user"}
        </button>
      </form>
      <div className="table-scroll" tabIndex={0} aria-label="Scrollable user list">
        <table>
          <caption>Enabled and disabled Google identities on the dashboard whitelist.</caption>
          <thead>
            <tr>
              <th scope="col">Identity</th>
              <th scope="col">Role</th>
              <th scope="col">State</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.user_id}>
                <th scope="row">
                  <strong>{user.email}</strong>
                  <span className="utc-line">
                    {user.primary
                      ? "Immutable primary administrator"
                      : user.identity_bound
                        ? "Google identity bound"
                        : "Invitation awaiting first login"}
                  </span>
                </th>
                <td>
                  {user.primary ? (
                    "Administrator"
                  ) : (
                    <label className="visually-labelled">
                      <span className="sr-only">Role for {user.email}</span>
                      <select
                        aria-label={`Role for ${user.email}`}
                        value={user.role}
                        disabled={busy !== ""}
                        onChange={(event) => {
                          const nextRole =
                            event.currentTarget.value === "admin" ? "admin" : "viewer";
                          void run(
                            `role-${user.user_id}`,
                            () =>
                              dashboardApi.updateUser(csrfToken, user.user_id, {
                                role: nextRole,
                              }),
                            (updated) => `${updated.email} is now ${updated.role}.`,
                          );
                        }}
                      >
                        <option value="viewer">Viewer</option>
                        <option value="admin">Administrator</option>
                      </select>
                    </label>
                  )}
                </td>
                <td>{user.enabled ? "Enabled" : "Disabled"}</td>
                <td>
                  {user.primary ? (
                    <span className="protected-label">Protected in SQLite</span>
                  ) : (
                    <div className="compact-actions">
                      <button
                        className="quiet-button"
                        type="button"
                        disabled={busy !== ""}
                        onClick={() =>
                          void run(
                            `toggle-${user.user_id}`,
                            () =>
                              dashboardApi.updateUser(csrfToken, user.user_id, {
                                enabled: !user.enabled,
                              }),
                            (updated) =>
                              `${updated.email} was ${updated.enabled ? "enabled" : "disabled"}.`,
                          )
                        }
                      >
                        {user.enabled ? "Disable" : "Enable"}
                      </button>
                      <button
                        className={removeArmed === user.user_id ? "danger-button" : "quiet-button"}
                        type="button"
                        disabled={busy !== ""}
                        onClick={() => {
                          if (removeArmed !== user.user_id) {
                            setRemoveArmed(user.user_id);
                            return;
                          }
                          void run(
                            `remove-${user.user_id}`,
                            () => dashboardApi.removeUser(csrfToken, user.user_id),
                            () => `${user.email} was removed from the whitelist.`,
                          );
                        }}
                      >
                        {removeArmed === user.user_id ? "Confirm removal" : "Remove"}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function RotationManagement({
  csrfToken,
  rotations,
  busy,
  run,
}: {
  readonly csrfToken: string;
  readonly rotations: readonly Rotation[];
  readonly busy: string;
  readonly run: RunControl;
}) {
  return (
    <article className="management-section" aria-labelledby="rotations-title">
      <div className="ledger-heading">
        <div>
          <h3 id="rotations-title">Databento key rotation</h3>
          <p>
            This workflow never accepts a key. Update the external secret first, then
            verify the active credential here.
          </p>
        </div>
        <button
          type="button"
          disabled={busy !== "" || rotations.some((item) => item.state === "requested")}
          onClick={() =>
            void run(
              "rotation-create",
              () => dashboardApi.createRotation(csrfToken),
              () => "A secret-free Databento rotation workflow was opened.",
            )
          }
        >
          {busy === "rotation-create" ? "Opening…" : "Start rotation workflow"}
        </button>
      </div>
      {rotations.length === 0 ? (
        <p className="empty-copy">No key-rotation workflows recorded.</p>
      ) : (
        <ul className="rotation-list">
          {rotations.map((rotation) => (
            <li key={rotation.rotation_id}>
              <div>
                <strong>{sentenceCase(rotation.state)}</strong>
                <span>{rotation.detail}</span>
                <time dateTime={rotation.updated_at_utc}>
                  {formatPacific(rotation.updated_at_utc)}
                </time>
              </div>
              {rotation.state === "requested" && (
                <div className="compact-actions">
                  <button
                    type="button"
                    disabled={busy !== ""}
                    onClick={() =>
                      void run(
                        `rotation-verify-${rotation.rotation_id}`,
                        () => dashboardApi.verifyRotation(csrfToken, rotation.rotation_id),
                        (updated) => `Rotation verification is ${updated.state}.`,
                      )
                    }
                  >
                    Verify external update
                  </button>
                  <button
                    className="quiet-button"
                    type="button"
                    disabled={busy !== ""}
                    onClick={() =>
                      void run(
                        `rotation-cancel-${rotation.rotation_id}`,
                        () => dashboardApi.cancelRotation(csrfToken, rotation.rotation_id),
                        () => "Rotation workflow cancelled.",
                      )
                    }
                  >
                    Cancel
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function AuditEvidence({ records }: { readonly records: readonly AuditRecord[] }) {
  return (
    <article className="management-section" aria-labelledby="audit-title">
      <div className="ledger-heading">
        <div>
          <h3 id="audit-title">Append-only audit evidence</h3>
          <p>Recent administrative intent and result records, newest first.</p>
        </div>
        <span>{records.length} shown</span>
      </div>
      <div className="table-scroll" tabIndex={0} aria-label="Scrollable audit evidence">
        <table>
          <caption>Recent records from the verified SQLite audit hash chain.</caption>
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Actor</th>
              <th scope="col">Action</th>
              <th scope="col">Resource</th>
              <th scope="col">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.audit_id}>
                <td>
                  <time dateTime={record.occurred_at_utc}>
                    {formatPacific(record.occurred_at_utc)}
                    <span className="utc-line">UTC {record.occurred_at_utc}</span>
                  </time>
                </td>
                <td>{record.actor_email}</td>
                <td>{sentenceCase(record.action)}</td>
                <td>
                  {sentenceCase(record.resource_type)}
                  <span className="utc-line">{record.resource_id}</span>
                </td>
                <td>
                  <code title={record.record_hash}>{record.record_hash.slice(0, 12)}</code>
                  <span className="utc-line">request {record.request_id.slice(0, 12)}</span>
                </td>
              </tr>
            ))}
            {records.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-cell">
                  No administrative mutation records yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}
