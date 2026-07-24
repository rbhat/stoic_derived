import { formatPacific, pacificMinutes } from "../format";

interface SessionChronologyProps {
  readonly generatedAtUtc: string;
}

const OPEN_MINUTES = 9 * 60 + 30;
const CUTOFF_MINUTES = 13 * 60 + 58;
const CLOSE_MINUTES = 14 * 60;

function sessionPosition(timestamp: string): number {
  const minutes = pacificMinutes(timestamp);
  const bounded = Math.min(Math.max(minutes, OPEN_MINUTES), CLOSE_MINUTES);
  return ((bounded - OPEN_MINUTES) / (CLOSE_MINUTES - OPEN_MINUTES)) * 100;
}

export function SessionChronology({ generatedAtUtc }: SessionChronologyProps) {
  const nowPosition = sessionPosition(generatedAtUtc);
  const cutoffPosition =
    ((CUTOFF_MINUTES - OPEN_MINUTES) / (CLOSE_MINUTES - OPEN_MINUTES)) * 100;

  return (
    <section className="chronology" aria-labelledby="chronology-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Pacific chronology</p>
          <h2 id="chronology-title">The session’s hard edge</h2>
        </div>
        <p className="timestamp-pair">
          Display <strong>{formatPacific(generatedAtUtc)}</strong>
          <span>Canonical UTC {generatedAtUtc}</span>
        </p>
      </div>
      <div
        className="time-rail"
        role="img"
        aria-label={`Pacific session rail from 9:30 AM to 2 PM. The cutoff is 1:58 PM. Current evidence time is ${formatPacific(generatedAtUtc)}.`}
      >
        <span className="rail-start">09:30</span>
        <span className="rail-end">14:00</span>
        <span
          className="rail-cutoff"
          style={{ left: `${cutoffPosition}%` }}
          aria-hidden="true"
        >
          <strong>13:58</strong>
          <small>cutoff</small>
        </span>
        <span
          className="rail-now"
          style={{ left: `${nowPosition}%` }}
          aria-hidden="true"
        >
          now
        </span>
      </div>
      <p className="chronology-note">
        Day, Swing, and Scalp observations flatten at the 13:58 Pacific boundary when
        their verified lifecycle reaches it. Position observations are exempt.
      </p>
    </section>
  );
}
