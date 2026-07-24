import { useEffect, useRef, useState } from "react";

import type { AuthConfig } from "../schemas";

interface LoginViewProps {
  readonly config: AuthConfig;
  readonly authError: boolean;
}

const GIS_SCRIPT = "https://accounts.google.com/gsi/client";

export function LoginView({ config, authError }: LoginViewProps) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const [scriptFailed, setScriptFailed] = useState(false);

  useEffect(() => {
    const render = () => {
      if (buttonRef.current === null || window.google === undefined) {
        return;
      }
      window.google.accounts.id.initialize({
        client_id: config.client_id,
        login_uri: config.login_uri,
        ux_mode: "redirect",
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        type: "standard",
        theme: "outline",
        size: "large",
        text: "sign_in_with",
        shape: "rectangular",
        logo_alignment: "left",
        width: 280,
      });
    };

    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GIS_SCRIPT}"]`);
    if (existing !== null) {
      if (window.google !== undefined) {
        render();
      } else {
        existing.addEventListener("load", render, { once: true });
      }
      return () => existing.removeEventListener("load", render);
    }

    const script = document.createElement("script");
    script.src = GIS_SCRIPT;
    script.async = true;
    script.defer = true;
    script.addEventListener("load", render, { once: true });
    script.addEventListener("error", () => setScriptFailed(true), { once: true });
    document.head.append(script);
    return () => script.removeEventListener("load", render);
  }, [config.client_id, config.login_uri]);

  return (
    <main className="login-shell">
      <section className="login-panel" aria-labelledby="login-title">
        <div>
          <p className="eyebrow">Stoic Derived · Pacific session console</p>
          <h1 id="login-title">Observe the system’s evidence</h1>
          <p className="login-lede">
            A read-first view of verified ledger observations, release readiness,
            Drive synchronization, and the 13:58 Pacific safety boundary.
          </p>
          <ul className="plain-list">
            <li>No brokerage or order placement</li>
            <li>No dollar P/L without position size</li>
            <li>Invite-only Google identity</li>
          </ul>
        </div>
        <div className="sign-in-block">
          <p className="cutoff-time" aria-label="Session cutoff at 1:58 PM Pacific">
            13:58 <small>PT cutoff</small>
          </p>
          {authError && (
            <p className="alert alert-fault" role="alert">
              Google verified the identity, but it is not on the enabled invitation
              list.
            </p>
          )}
          {scriptFailed ? (
            <p className="alert alert-fault" role="alert">
              Google Sign-In could not load. Check network access and try again.
            </p>
          ) : (
            <>
              <div ref={buttonRef} className="google-button" />
              <p className="fine-print">
                Authentication only. Dashboard users do not grant Google Drive
                authorization.
              </p>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
