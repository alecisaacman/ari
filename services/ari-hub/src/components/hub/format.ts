// Times are shown in the Mac's own time zone, where ARI runs.
export function clock(value: string): string {
  return moment(value).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function day(value: string): string {
  return moment(value).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

// ARI's database keeps some times without a zone; those are UTC.
function moment(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) || !value.includes("T") ? value : `${value}Z`);
}

export function when(value: string): string {
  return `${day(value)}, ${clock(value)}`;
}

export function greeting(now: Date): string {
  const hour = now.getHours();
  return hour < 5 ? "Still up" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}
