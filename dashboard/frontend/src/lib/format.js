export function lapTime(ms) {
  if (ms == null) return "—";
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  const millis = ms % 1000;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

/** Seconds as "3h 0min" / "45min" / "30s" — sessions are configured in seconds. */
export function duration(totalSeconds) {
  const value = Number(totalSeconds) || 0;
  if (value <= 0) return "off";
  const hours = Math.floor(value / 3600);
  const minutes = Math.round((value % 3600) / 60);
  if (hours && minutes) return `${hours}h ${minutes}min`;
  if (hours) return `${hours}h`;
  if (minutes) return `${minutes}min`;
  return `${value}s`;
}

export const splitDuration = (totalSeconds) => ({
  hours: Math.floor((Number(totalSeconds) || 0) / 3600),
  minutes: Math.round(((Number(totalSeconds) || 0) % 3600) / 60),
});

export const joinDuration = (hours, minutes) =>
  Math.max(0, Math.round(Number(hours) || 0) * 3600 + Math.round(Number(minutes) || 0) * 60);

export function carLabel(internalName, cars) {
  const hit = cars?.find((car) => car.internal_name === internalName);
  return hit ? hit.display_name : internalName || "—";
}

/** "Laguna Seca|GP|GP Time Attack|3602" — the event name differs per mode. */
export const trackIdentity = (token) => (token || "").split("|").slice(0, 2).join("|");
