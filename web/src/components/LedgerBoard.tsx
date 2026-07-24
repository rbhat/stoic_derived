import {
  formatHold,
  formatPacific,
  formatPnlTicks,
  formatPriceTicks,
  sentenceCase,
} from "../format";
import type { LedgerSnapshot, Observation } from "../schemas";

interface LedgerBoardProps {
  readonly snapshot: LedgerSnapshot;
}

interface Breakdown {
  readonly label: string;
  readonly count: number;
}

function countBy(
  observations: readonly Observation[],
  label: (observation: Observation) => string,
): readonly Breakdown[] {
  const counts = new Map<string, number>();
  for (const observation of observations) {
    const key = label(observation);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([itemLabel, count]) => ({ label: itemLabel, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

function BreakdownChart({
  title,
  description,
  items,
  id,
}: {
  readonly title: string;
  readonly description: string;
  readonly items: readonly Breakdown[];
  readonly id: string;
}) {
  const maximum = Math.max(1, ...items.map((item) => item.count));
  if (items.length === 0) {
    return <p className="empty-chart">No observations in this section.</p>;
  }
  return (
    <div className="chart-with-equivalent">
      <svg
        className="breakdown-chart"
        viewBox={`0 0 600 ${items.length * 42 + 32}`}
        role="img"
        aria-labelledby={`${id}-title ${id}-description`}
      >
        <title id={`${id}-title`}>{title}</title>
        <desc id={`${id}-description`}>{description}</desc>
        {items.map((item, index) => {
          const y = index * 42 + 12;
          const width = (item.count / maximum) * 360;
          return (
            <g key={item.label}>
              <text x="0" y={y + 15}>
                {item.label}
              </text>
              <rect x="190" y={y} width={width} height="22" rx="2" />
              <text className="chart-count" x={Math.min(580, 202 + width)} y={y + 16}>
                {item.count}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="chart-equivalent" aria-label={`${title} text equivalent`}>
        {items.map((item) => (
          <li key={item.label}>
            <span>{item.label}</span>
            <strong>{item.count}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StateLabel({ observation }: { readonly observation: Observation }) {
  const reason =
    observation.terminal_reason === null
      ? ""
      : ` · ${sentenceCase(observation.terminal_reason)}`;
  return (
    <span className={`observation-state observation-state-${observation.state}`}>
      {sentenceCase(observation.state)}
      {reason}
    </span>
  );
}

function PacificTime({ value }: { readonly value: string | null }) {
  if (value === null) {
    return <span>—</span>;
  }
  return (
    <time dateTime={value}>
      {formatPacific(value)}
      <span className="utc-line">UTC {value}</span>
    </time>
  );
}

function PlannedLevels({ observation }: { readonly observation: Observation }) {
  return (
    <dl className="level-stack">
      <div>
        <dt>Entry</dt>
        <dd>{formatPriceTicks(observation.planned_entry_price_ticks)}</dd>
      </div>
      <div>
        <dt>Stop</dt>
        <dd>{formatPriceTicks(observation.planned_stop_price_ticks)}</dd>
      </div>
      <div>
        <dt>Target</dt>
        <dd>{formatPriceTicks(observation.planned_target_price_ticks)}</dd>
      </div>
    </dl>
  );
}

function ObservationIdentity({ observation }: { readonly observation: Observation }) {
  return (
    <div className="observation-identity">
      <strong>
        {observation.instrument} · {observation.signal_type}
      </strong>
      <span>
        {sentenceCase(observation.direction)} · {observation.setup_type}
      </span>
      <code title={observation.signal_id}>{observation.signal_id.slice(0, 10)}</code>
    </div>
  );
}

function OpenTable({ observations }: { readonly observations: readonly Observation[] }) {
  return (
    <div className="table-scroll" tabIndex={0} aria-label="Scrollable open observations">
      <table>
        <caption>
          Pending and active observations. Prices are points encoded from exact ticks.
        </caption>
        <thead>
          <tr>
            <th scope="col">Observation</th>
            <th scope="col">State</th>
            <th scope="col">Signal time</th>
            <th scope="col">Planned levels</th>
            <th scope="col">Observed entry</th>
            <th scope="col">Time held</th>
          </tr>
        </thead>
        <tbody>
          {observations.map((observation) => (
            <tr key={observation.signal_id}>
              <th scope="row">
                <ObservationIdentity observation={observation} />
              </th>
              <td>
                <StateLabel observation={observation} />
              </td>
              <td>
                <PacificTime value={observation.signal_ts_utc} />
              </td>
              <td>
                <PlannedLevels observation={observation} />
              </td>
              <td>
                <span className="observed-price">
                  {formatPriceTicks(observation.entry_observed_price_ticks)}
                </span>
                <PacificTime value={observation.entry_observed_ts_utc} />
              </td>
              <td>{formatHold(observation.hold_seconds)}</td>
            </tr>
          ))}
          {observations.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-cell">
                No open observations are present in verified authority.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function ClosedTable({ observations }: { readonly observations: readonly Observation[] }) {
  return (
    <div className="table-scroll" tabIndex={0} aria-label="Scrollable closed observations">
      <table>
        <caption>
          Deterministically closed observations. P/L is observational ticks and exact R,
          never dollars.
        </caption>
        <thead>
          <tr>
            <th scope="col">Observation</th>
            <th scope="col">Outcome</th>
            <th scope="col">Observed entry</th>
            <th scope="col">Observed close</th>
            <th scope="col">Observed P/L</th>
            <th scope="col">Time held</th>
          </tr>
        </thead>
        <tbody>
          {observations.map((observation) => (
            <tr key={observation.signal_id}>
              <th scope="row">
                <ObservationIdentity observation={observation} />
              </th>
              <td>
                <StateLabel observation={observation} />
              </td>
              <td>
                <span className="observed-price">
                  {formatPriceTicks(observation.entry_observed_price_ticks)}
                </span>
                <PacificTime value={observation.entry_observed_ts_utc} />
              </td>
              <td>
                <span className="observed-price">
                  {formatPriceTicks(observation.close_observed_price_ticks)}
                </span>
                <PacificTime value={observation.close_observed_ts_utc} />
              </td>
              <td>
                <strong className="numeric">
                  {formatPnlTicks(observation.observed_pnl_ticks)}
                </strong>
                <span className="r-value">
                  {observation.observed_pnl_r === null
                    ? "No exact R"
                    : `${observation.observed_pnl_r.numerator > 0 ? "+" : ""}${observation.observed_pnl_r.display}R`}
                </span>
              </td>
              <td>{formatHold(observation.hold_seconds)}</td>
            </tr>
          ))}
          {observations.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-cell">
                No closed observations are present in verified authority.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function UnresolvedTable({
  observations,
}: {
  readonly observations: readonly Observation[];
}) {
  if (observations.length === 0) {
    return <p className="empty-copy">No unresolved observation chains.</p>;
  }
  return (
    <div className="table-scroll" tabIndex={0} aria-label="Scrollable unresolved observations">
      <table>
        <caption>
          Unresolved chains are excluded from closed results and exact P/L.
        </caption>
        <thead>
          <tr>
            <th scope="col">Observation</th>
            <th scope="col">State</th>
            <th scope="col">Signal time</th>
            <th scope="col">Evidence conflicts</th>
          </tr>
        </thead>
        <tbody>
          {observations.map((observation) => (
            <tr key={observation.signal_id}>
              <th scope="row">
                <ObservationIdentity observation={observation} />
              </th>
              <td>
                <StateLabel observation={observation} />
              </td>
              <td>
                <PacificTime value={observation.signal_ts_utc} />
              </td>
              <td>
                {observation.conflicts.length === 0 ? (
                  "Terminal evidence is incomplete."
                ) : (
                  <ul className="conflict-list">
                    {observation.conflicts.map((conflict) => (
                      <li key={`${conflict.code}:${conflict.detail}`}>
                        <strong>{conflict.code}</strong> — {conflict.detail}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function LedgerBoard({ snapshot }: LedgerBoardProps) {
  const ledger = snapshot.ledger;
  if (ledger.status === "blocked") {
    return (
      <section id="ledger" className="ruled-section" aria-labelledby="ledger-title">
        <p className="eyebrow">Observational ledger</p>
        <h2 id="ledger-title">Production remains blocked at zero</h2>
        <div className="blocked-boundary" role="status">
          <strong>No observations loaded.</strong>
          <p>
            The signed, semantically complete, human-approved SP0 release boundary has
            not passed.
          </p>
          <ul>
            {ledger.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      </section>
    );
  }
  if (ledger.status === "error") {
    return (
      <section id="ledger" className="ruled-section" aria-labelledby="ledger-title">
        <p className="eyebrow">Observational ledger</p>
        <h2 id="ledger-title">Verified ledger unavailable</h2>
        <p className="alert alert-fault" role="alert">
          {ledger.detail} No observations were accepted.
        </p>
      </section>
    );
  }

  const openBreakdown = countBy(
    ledger.open_observations,
    (item) => `${sentenceCase(item.state)} · ${item.signal_type}`,
  );
  const closedBreakdown = countBy(
    ledger.closed_observations,
    (item) => sentenceCase(item.terminal_reason ?? "Unspecified"),
  );

  return (
    <section id="ledger" className="ruled-section" aria-labelledby="ledger-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Observational ledger</p>
          <h2 id="ledger-title">Drive-authoritative lifecycle evidence</h2>
        </div>
        <p className="source-label">
          Verified Drive + undelivered local outbox
          <span>Generated UTC {snapshot.generated_at_utc}</span>
        </p>
      </div>

      <article className="ledger-section" aria-labelledby="open-title">
        <div className="ledger-heading">
          <h3 id="open-title">Open observations</h3>
          <span>{ledger.open_observations.length} total</span>
        </div>
        <BreakdownChart
          id="open-chart"
          title="Open observations by state and signal type"
          description="Counts of pending and active observations grouped by lifecycle state and signal type."
          items={openBreakdown}
        />
        <OpenTable observations={ledger.open_observations} />
      </article>

      <article className="ledger-section" aria-labelledby="closed-title">
        <div className="ledger-heading">
          <h3 id="closed-title">Closed observations</h3>
          <span>{ledger.closed_observations.length} total</span>
        </div>
        <BreakdownChart
          id="closed-chart"
          title="Closed observations by terminal reason"
          description="Counts of deterministically closed observations grouped by stop, target, session flatten, or other verified reason."
          items={closedBreakdown}
        />
        <ClosedTable observations={ledger.closed_observations} />
      </article>

      <article className="ledger-section unresolved-section" aria-labelledby="unresolved-title">
        <div className="ledger-heading">
          <h3 id="unresolved-title">Unresolved observations</h3>
          <span>{ledger.unresolved_observations.length} total</span>
        </div>
        <UnresolvedTable observations={ledger.unresolved_observations} />
      </article>
    </section>
  );
}
