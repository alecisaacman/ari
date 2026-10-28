// Times are shown in the Mac's own time zone, where ARI runs.
export function clock(value: string): string {
  return new Date(value).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function day(value: string): string {
  return new Date(value).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export function when(value: string): string {
  return `${day(value)}, ${clock(value)}`;
}

export function greeting(now: Date): string {
  const hour = now.getHours();
  return hour < 5 ? "Still up" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}
