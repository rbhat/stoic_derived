import { formatPacific, sentenceCase } from "../format";
import type { OperationsStatus } from "../schemas";

interface OperationsBoardProps {
  readonly operations: OperationsStatus;
}

const preferredOrder = [
  "api",
  "release",
  "drive",
  "market_data",
  "drive_connection",
  "sync",
  "watchdog",
];

function stateClass(state: string): string {
  return `state state-${state}`;
}

export function OperationsBoard({ operations }: OperationsBoardProps) {
  const ordered = [...operations.components].sort(
    (left, right) => {
      const leftIndex = preferredOrder.indexOf(left.component);
      const rightIndex = preferredOrder.indexOf(right.component);
      return (leftIndex < 0 ? preferredOrder.length : leftIndex) -
        (rightIndex < 0 ? preferredOrder.length : rightIndex);
    },
  );

  return (
    <section id="operations" className="ruled-section" aria-labelledby="operations-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Operating state</p>
          <h2 id="operations-title">Connectivity and readiness</h2>
        </div>
        <p className="timestamp-pair">
          Process started <strong>{formatPacific(operations.process_started_at_utc)}</strong>
          <span>UTC {operations.process_started_at_utc}</span>
        </p>
      </div>
      <ul className="status-strip" aria-label="System component states">
        {ordered.map((item) => (
          <li key={item.component}>
            <div className="status-name">
              <span aria-hidden="true" className={stateClass(item.state)} />
              <strong>{sentenceCase(item.component)}</strong>
            </div>
            <span className="state-word">{sentenceCase(item.state)}</span>
            <p>{item.detail}</p>
            {item.observed_at_utc !== null && (
              <time dateTime={item.observed_at_utc}>
                {formatPacific(item.observed_at_utc)}
              </time>
            )}
          </li>
        ))}
      </ul>
      <div className="outbox-line">
        <div>
          <span aria-hidden="true" className={stateClass(operations.outbox.state)} />
          <strong>Outbox / sync</strong>
          <span className="state-word">{sentenceCase(operations.outbox.state)}</span>
        </div>
        <dl>
          <div>
            <dt>Pending</dt>
            <dd>{operations.outbox.pending_count}</dd>
          </div>
          <div>
            <dt>Acknowledged</dt>
            <dd>{operations.outbox.acknowledged_count}</dd>
          </div>
          <div>
            <dt>Max attempts</dt>
            <dd>{operations.outbox.maximum_pending_attempts}</dd>
          </div>
        </dl>
        <p>{operations.outbox.detail}</p>
      </div>
      <div className="drive-activity" aria-label="Last successful Drive activity">
        <h3>Last successful Drive activity</h3>
        <dl>
          <div>
            <dt>Verified refresh</dt>
            <dd>
              {operations.drive_activity.refresh.observed_at_utc === null ? (
                "Not recorded"
              ) : (
                <time dateTime={operations.drive_activity.refresh.observed_at_utc}>
                  {formatPacific(operations.drive_activity.refresh.observed_at_utc)}
                  <span className="utc-line">
                    UTC {operations.drive_activity.refresh.observed_at_utc}
                  </span>
                </time>
              )}
              <span>{operations.drive_activity.refresh.affected_count} observations</span>
            </dd>
          </div>
          <div>
            <dt>Verified publication</dt>
            <dd>
              {operations.drive_activity.publish.observed_at_utc === null ? (
                "Not recorded"
              ) : (
                <time dateTime={operations.drive_activity.publish.observed_at_utc}>
                  {formatPacific(operations.drive_activity.publish.observed_at_utc)}
                  <span className="utc-line">
                    UTC {operations.drive_activity.publish.observed_at_utc}
                  </span>
                </time>
              )}
              <span>{operations.drive_activity.publish.affected_count} events</span>
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
