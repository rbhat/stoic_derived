const pacificDateTime = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Los_Angeles",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  timeZoneName: "short",
});

export function formatPacific(timestamp: string | null): string {
  if (timestamp === null) {
    return "—";
  }
  return pacificDateTime.format(new Date(timestamp));
}

export function formatPriceTicks(ticks: number | null): string {
  if (ticks === null) {
    return "—";
  }
  return (ticks / 4).toFixed(2);
}

export function formatPnlTicks(ticks: number | null): string {
  if (ticks === null) {
    return "Awaiting close";
  }
  return `${ticks > 0 ? "+" : ""}${ticks} ticks`;
}

export function formatHold(seconds: number | null): string {
  if (seconds === null) {
    return "—";
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${remaining}s`;
  }
  return `${remaining}s`;
}

export function sentenceCase(value: string): string {
  return value.replaceAll("_", " ").replace(/^\w/u, (character) => character.toUpperCase());
}

export function pacificMinutes(timestamp: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(timestamp));
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? "0");
  return hour * 60 + minute;
}
