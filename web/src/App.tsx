import { useCallback, useEffect, useState } from "react";

import { dashboardApi, ApiError } from "./api";
import { AdminConsole } from "./components/AdminConsole";
import { LedgerBoard } from "./components/LedgerBoard";
import { LoginView } from "./components/LoginView";
import { OperationsBoard } from "./components/OperationsBoard";
import { SessionChronology } from "./components/SessionChronology";
import type {
  AuditRecord,
  AuthConfig,
  LedgerSnapshot,
  OperationsStatus,
  Rotation,
  Session,
  User,
} from "./schemas";

type BootState =
  | { state: "loading" }
  | { state: "signed-out"; config: AuthConfig; authError: boolean }
  | {
      state: "ready";
      config: AuthConfig;
      session: Session;
      ledger: LedgerSnapshot;
      operations: OperationsStatus;
      users: readonly User[];
      rotations: readonly Rotation[];
      audit: readonly AuditRecord[];
    }
  | { state: "error"; detail: string };

function errorDetail(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "The dashboard could not load its verified state.";
}

function authWasDenied(): boolean {
  return new URLSearchParams(window.location.search).get("auth_error") === "access_denied";
}

export function App() {
  const [boot, setBoot] = useState<BootState>({ state: "loading" });
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setNotice("");
    try {
      const config = await dashboardApi.authConfig();
      let session: Session;
      try {
        session = await dashboardApi.session();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          setBoot({
            state: "signed-out",
            config,
            authError: authWasDenied(),
          });
          return;
        }
        throw error;
      }

      const [ledger, operations] = await Promise.all([
        dashboardApi.ledger(),
        dashboardApi.operations(),
      ]);
      if (session.user.role === "admin") {
        const [users, rotations, audit] = await Promise.all([
          dashboardApi.users(),
          dashboardApi.rotations(),
          dashboardApi.audit(),
        ]);
        setBoot({
          state: "ready",
          config,
          session,
          ledger,
          operations,
          users,
          rotations,
          audit,
        });
      } else {
        setBoot({
          state: "ready",
          config,
          session,
          ledger,
          operations,
          users: [],
          rotations: [],
          audit: [],
        });
      }
    } catch (error) {
      setBoot({ state: "error", detail: errorDetail(error) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (boot.state === "loading") {
    return (
      <main className="centered-state" aria-busy="true">
        <p className="eyebrow">Pacific session console</p>
        <h1>Checking authority</h1>
        <p>Verifying the current session and ledger boundary…</p>
      </main>
    );
  }

  if (boot.state === "signed-out") {
    return <LoginView config={boot.config} authError={boot.authError} />;
  }

  if (boot.state === "error") {
    return (
      <main className="centered-state">
        <p className="eyebrow">Contract-safe failure</p>
        <h1>Dashboard unavailable</h1>
        <p>{boot.detail}</p>
        <button type="button" onClick={() => void load()}>
          Try again
        </button>
      </main>
    );
  }

  const logout = async () => {
    try {
      await dashboardApi.logout(boot.session.csrf_token);
      window.history.replaceState({}, "", "/");
      await load();
    } catch (error) {
      setNotice(errorDetail(error));
    }
  };

  return (
    <>
      <a className="skip-link" href="#ledger">
        Skip to observational ledger
      </a>
      <header className="masthead">
        <div>
          <p className="eyebrow">Stoic Derived · Pacific session console</p>
          <h1>System truth, without execution</h1>
        </div>
        <div className="identity">
          <span>{boot.session.user.email}</span>
          <span className="role-label">{boot.session.user.role}</span>
          <button className="quiet-button" type="button" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>
      <nav className="section-nav" aria-label="Dashboard sections">
        <a href="#operations">Operations</a>
        <a href="#ledger">Ledger observations</a>
        {boot.session.user.role === "admin" && <a href="#management">Management</a>}
      </nav>
      <main>
        <div className="safety-banner">
          <strong>Observational system.</strong> No broker connection, orders, fills, or
          dollar P/L. Strategy controls are intentionally absent.
        </div>
        <p className="live-notice" role="status" aria-live="polite">
          {notice}
        </p>
        <SessionChronology generatedAtUtc={boot.operations.generated_at_utc} />
        <OperationsBoard operations={boot.operations} />
        <LedgerBoard snapshot={boot.ledger} />
        {boot.session.user.role === "admin" && (
          <AdminConsole
            csrfToken={boot.session.csrf_token}
            users={boot.users}
            rotations={boot.rotations}
            audit={boot.audit}
            onChanged={async (message) => {
              await load();
              setNotice(message);
            }}
            onFailure={(message) => setNotice(message)}
          />
        )}
      </main>
      <footer>
        <p>
          UTC remains canonical. Display times use America/Los_Angeles. Drive is the
          shared ledger authority.
        </p>
      </footer>
    </>
  );
}
