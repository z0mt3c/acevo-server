const minutes = (value) => value * 60;

/** In-game start times; without them a weekend configured via preset runs at midnight. */
export const DAYTIME_STARTS = { practice: 10, qualify: 13, warmup: 13, race: 14 };

/**
 * Race weekend shapes. Switching the mode used to leave qualify, warmup and race
 * at zero, which is a weekend without a race — so a preset is applied whenever
 * the target mode would otherwise have nothing to drive.
 */
export const SESSION_PRESETS = [
  {
    key: "sprint",
    label: "Sprint",
    hint: "15 / 10 / – / 20",
    sessions: { practice: minutes(15), qualify: minutes(10), warmup: 0, race: minutes(20) },
  },
  {
    key: "standard",
    label: "Standard",
    hint: "30 / 15 / 5 / 45",
    sessions: { practice: minutes(30), qualify: minutes(15), warmup: minutes(5), race: minutes(45) },
  },
  {
    key: "endurance",
    label: "Endurance",
    hint: "45 / 20 / 10 / 120",
    sessions: { practice: minutes(45), qualify: minutes(20), warmup: minutes(10), race: minutes(120) },
  },
  {
    key: "practice",
    label: "Practice only",
    hint: "3h open track",
    sessions: { practice: minutes(180), qualify: 0, warmup: 0, race: 0 },
  },
];

export const DEFAULT_WEEKEND = "standard";
