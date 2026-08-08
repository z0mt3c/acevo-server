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

/**
 * Racing classes. The metadata has no class field — `type` only knows
 * road/race/track — so the class comes out of the display name. Every rule is
 * additionally gated on type "race", because road cars carry names like
 * "718 Cayman GT4 RS" and would otherwise land in the GT4 grid.
 */
export const CAR_CLASSES = [
  {
    key: "formula",
    label: "Formula",
    test: (car) => isRace(car) && /SF-25|F2004|Formula|\bF1\b/.test(car.display_name),
  },
  {
    key: "gt3",
    label: "GT3",
    test: (car) => isRace(car) && /\bGT3\b/.test(car.display_name) && !car.display_name.includes("GT3 Cup"),
  },
  { key: "gt2", label: "GT2", test: (car) => isRace(car) && /\bGT2\b/.test(car.display_name) },
  { key: "gt4", label: "GT4", test: (car) => isRace(car) && /\bGT4\b/.test(car.display_name) },
  {
    key: "cup",
    label: "Cup / one-make",
    test: (car) => isRace(car) && /Cup|Challenge|Trofeo|Academy/.test(car.display_name),
  },
  {
    key: "race",
    label: "Race (other)",
    test: (car) => isRace(car) && !CAR_CLASSES.slice(0, 5).some((c) => c.test(car)),
  },
  { key: "track", label: "Track toys", test: (car) => car.type === "track" },
  { key: "road", label: "Road", test: (car) => car.type === "road" },
  { key: "vintage", label: "Vintage", test: (car) => car.era === "vintage" },
  { key: "electric", label: "Electric", test: (car) => car.engine === "ev" },
];

const isRace = (car) => car.type === "race";
