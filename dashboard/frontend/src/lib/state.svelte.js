import { api } from "./api.js";
import { trackIdentity } from "./format.js";
import { SESSION_PRESETS, DEFAULT_WEEKEND } from "./presets.js";

const clone = (value) => JSON.parse(JSON.stringify(value));

/** Leaf-level diff, so the change bar can say "3 changes" instead of "dirty". */
function countChanges(a, b, path = "") {
  if (a === b) return 0;
  if (Array.isArray(a) || Array.isArray(b)) {
    return JSON.stringify(a) === JSON.stringify(b) ? 0 : 1;
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
    let total = 0;
    for (const key of keys) total += countChanges(a[key], b[key], `${path}.${key}`);
    return total;
  }
  return 1;
}

class Dashboard {
  meta = $state(null);
  form = $state(null);
  savedForm = $state(null);
  status = $state({ running: false, state: "unknown", update: { running: false } });
  live = $state({ drivers: [], players: 0, clients: null });
  profiles = $state([]);
  report = $state(null);
  toastMessage = $state("");
  busy = $state(false);

  changes = $derived(this.form && this.savedForm ? countChanges(this.form, this.savedForm) : 0);
  dirty = $derived(this.changes > 0);

  tracks = $derived.by(() => {
    if (!this.meta || !this.form) return [];
    return /RACE_WEEKEND/i.test(this.form.event.type || "") ? this.meta.tracks.race_weekend : this.meta.tracks.practice;
  });

  track = $derived.by(() => this.tracks.find((t) => t.token === this.form?.event.track) || null);
  pitLimit = $derived(this.track?.max_pit_slot ?? 50);

  async load() {
    const [meta, config, profiles] = await Promise.all([api.metadata(), api.config(), api.profiles()]);
    this.meta = meta;
    this.form = config.form;
    this.savedForm = clone(config.form);
    this.profiles = profiles.profiles || [];
    await this.refreshStatus();
    this.validate();
  }

  async refreshStatus() {
    try {
      this.status = await api.status();
      if (this.status.running) this.live = await api.live();
    } catch {
      /* transient — the poller tries again */
    }
  }

  toast(message) {
    this.toastMessage = message;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => (this.toastMessage = ""), 3500);
  }

  async validate() {
    try {
      this.report = await api.validate($state.snapshot(this.form));
    } catch {
      this.report = null;
    }
  }

  /**
   * The same circuit has a different token per mode, because the event name is
   * part of it ("GP Time Attack" vs "GP Race"). Match on track+layout so
   * switching Practice ⇄ Race Weekend keeps the track instead of resetting it.
   */
  applySessionPreset(key) {
    const preset = SESSION_PRESETS.find((entry) => entry.key === key);
    if (!preset) return;
    for (const [session, length] of Object.entries(preset.sessions)) {
      this.form.sessions[session].length_sec = length;
    }
    // A timed race is the sane default; laps stay available in the race panel.
    if (preset.sessions.race > 0) {
      this.form.sessions.race.duration_type = "GameModeSelectionDuration_TIME";
    }
    this.toast(`Sessions set to "${preset.label}".`);
  }

  setEventType(type) {
    const previous = this.form.event.track;
    this.form.event.type = type;
    const isRace = /RACE_WEEKEND/i.test(type);

    // A race weekend with a zero-length race is not a weekend. Only fill in when
    // the user has nothing set, so an existing schedule is never overwritten.
    if (isRace && !this.form.sessions.race.length_sec && !this.form.sessions.qualify.length_sec) {
      this.applySessionPreset(DEFAULT_WEEKEND);
    }

    const list = /RACE_WEEKEND/i.test(type) ? this.meta.tracks.race_weekend : this.meta.tracks.practice;
    if (list.some((t) => t.token === previous)) return;
    const sameTrack = list.find((t) => trackIdentity(t.token) === trackIdentity(previous));
    if (sameTrack) {
      this.form.event.track = sameTrack.token;
    } else {
      this.form.event.track = list[0]?.token || "";
      this.toast("Track is not available in this mode — switched to the first one.");
    }
    this.clampPlayers();
  }

  setTrack(token) {
    this.form.event.track = token;
    this.clampPlayers();
  }

  /** Every track has a pit-slot limit; the server silently downscales past it. */
  clampPlayers() {
    const limit = this.pitLimit;
    this.form.server.max_players_limit = limit;
    if (this.form.server.max_players > limit) {
      this.form.server.max_players = limit;
      this.toast(`Max players reduced to ${limit} — that is all the pit slots this track has.`);
    }
  }

  async save({ apply } = { apply: false }) {
    this.busy = true;
    try {
      const result = await api.save($state.snapshot(this.form));
      if (result.error) {
        this.toast(`Save failed: ${result.error}`);
        return false;
      }
      this.savedForm = clone($state.snapshot(this.form));
      this.report = result;
      this.toast(apply ? "Saved — restarting the server…" : "Saved.");
      if (apply) await this.serverAction("restart");
      return true;
    } finally {
      this.busy = false;
    }
  }

  discard() {
    this.form = clone($state.snapshot(this.savedForm));
    this.toast("Changes discarded.");
    this.validate();
  }

  async serverAction(action) {
    this.busy = true;
    try {
      const result = await api[action]();
      this.toast(result.ok ? `${action}: ok` : `${action} failed: ${result.error || ""}`);
      await this.refreshStatus();
    } finally {
      this.busy = false;
    }
  }

  async applyProfile(name) {
    const result = await api.profile(name);
    if (result.error) return this.toast(result.error);
    this.form = result.form;
    this.clampPlayers();
    this.validate();
    this.toast(`Profile "${name}" loaded — not saved yet.`);
  }

  async saveProfile(name) {
    const result = await api.saveProfile(name, $state.snapshot(this.form));
    if (result.error) return this.toast(result.error);
    this.profiles = (await api.profiles()).profiles || [];
    this.toast(`Profile "${name}" saved.`);
  }

  async deleteProfile(name) {
    await api.deleteProfile(name);
    this.profiles = (await api.profiles()).profiles || [];
    this.toast(`Profile "${name}" deleted.`);
  }
}

export const dash = new Dashboard();
