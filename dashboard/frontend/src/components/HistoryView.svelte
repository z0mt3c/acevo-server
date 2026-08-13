<script>
  import { api } from "../lib/api.js";
  import { dash } from "../lib/state.svelte.js";
  import { lapTime, carLabel } from "../lib/format.js";

  let mode = $state("leaderboard"); // leaderboard | records | sessions
  let track = $state("");
  let carFilter = $state("");
  let classFilter = $state("");
  let phaseFilter = $state("");
  let leaderboard = $state([]);
  let records = $state([]);
  let sessions = $state([]);
  let detail = $state(null);
  let loaded = $state(false);

  // Tracks that actually have laps recorded, for the picker.
  const knownTracks = $derived([...new Set(records.map((row) => row.track))]);

  // Car suggestions come from the history itself: suggesting a car nobody has
  // driven yet would only ever produce an empty leaderboard.
  const knownCars = $derived.by(() => {
    const seen = new Map();
    for (const row of records) {
      if (row.car && !seen.has(row.car)) seen.set(row.car, carLabel(row.car, dash.meta.cars));
    }
    return [...seen].map(([internal, label]) => ({ internal, label }));
  });

  // The input shows display names, the API filters on internal names.
  const resolveCar = (text) =>
    knownCars.find((entry) => entry.label.toLowerCase() === (text || "").toLowerCase())?.internal ?? text;

  const loadBoard = async () =>
    ((await api.leaderboard(track, resolveCar(carFilter), classFilter, phaseFilter)).leaderboard ?? []);

  async function refresh() {
    const [bestsResult, sessionsResult] = await Promise.all([api.bests("", ""), api.sessions()]);
    records = bestsResult.bests || [];
    sessions = sessionsResult.sessions || [];
    if (!track && records.length) track = records[0].track;
    if (track) leaderboard = await loadBoard();
    loaded = true;
  }

  const knownClasses = $derived([...new Set(records.map((row) => row.car_class).filter(Boolean))]);

  $effect(() => {
    refresh();
  });

  async function pickTrack(value) {
    track = value;
    leaderboard = await loadBoard();
  }

  async function pickCarFilter(value) {
    carFilter = value;
    if (track) leaderboard = await loadBoard();
  }

  async function pickClass(value) {
    classFilter = value;
    if (track) leaderboard = await loadBoard();
  }

  async function pickPhase(value) {
    phaseFilter = value;
    if (track) leaderboard = await loadBoard();
  }

  async function openSession(id) {
    detail = await api.session(id);
  }

  const gap = (ms, best) => (ms === best ? "" : `+${((ms - best) / 1000).toFixed(3)}`);

  function date(value) {
    if (!value) return "—";
    // SQLite writes UTC without a zone marker.
    return new Date(value.replace(" ", "T") + "Z").toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
</script>

<div class="grid gap-3">
  <div class="inline-flex gap-1 self-start rounded-xl bg-surface p-1">
    {#each [["leaderboard", "Leaderboard"], ["records", "Records"], ["sessions", "Sessions"]] as [key, label] (key)}
      <button
        class="rounded-lg px-4 py-2 text-sm transition {mode === key
          ? 'bg-raised font-semibold text-ink'
          : 'text-muted hover:text-ink'}"
        onclick={() => (mode = key)}
      >
        {label}
      </button>
    {/each}
  </div>

  {#if !loaded}
    <div class="card px-4 py-8 text-center text-sm text-muted">Loading…</div>
  {:else if records.length === 0}
    <div class="card px-4 py-12 text-center">
      <p class="text-sm text-muted">No laps recorded yet.</p>
      <p class="mt-1 text-xs text-muted/60">
        Every lap driven on the server lands here automatically — drive one and refresh.
      </p>
    </div>
  {:else if mode === "leaderboard"}
    <div class="card overflow-hidden">
      <div class="flex flex-wrap gap-2 border-b border-line px-3 py-2">
        <select class="field w-auto min-w-[14rem] py-1.5 text-sm" value={track} onchange={(e) => pickTrack(e.currentTarget.value)}>
          {#each knownTracks as name (name)}
            <option value={name}>{name}</option>
          {/each}
        </select>
        <input
          class="field w-auto flex-1 py-1.5 text-sm"
          placeholder="Filter by car…"
          list="leaderboard-cars"
          value={carFilter}
          onchange={(e) => pickCarFilter(e.currentTarget.value)}
        />
        <select class="field w-auto py-1.5 text-sm" value={classFilter} onchange={(e) => pickClass(e.currentTarget.value)}>
          <option value="">All classes</option>
          {#each knownClasses as cls (cls)}
            <option value={cls.toLowerCase()}>{cls}</option>
          {/each}
        </select>
        <select class="field w-auto py-1.5 text-sm" value={phaseFilter} onchange={(e) => pickPhase(e.currentTarget.value)}>
          <option value="">All phases</option>
          <option value="practice">Practice</option>
          <option value="qualify">Qualify</option>
          <option value="warmup">Warmup</option>
          <option value="race">Race</option>
        </select>
        <datalist id="leaderboard-cars">
          {#each knownCars as entry (entry.internal)}
            <option value={entry.label}></option>
          {/each}
        </datalist>
      </div>
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
            <th class="px-3 py-2 font-medium">P</th>
            <th class="px-3 py-2 font-medium">Driver</th>
            <th class="hidden px-3 py-2 font-medium sm:table-cell">Car</th>
            <th class="px-3 py-2 text-right font-medium">Best</th>
            <th class="px-3 py-2 text-right font-medium">Gap</th>
            <th class="hidden px-3 py-2 text-right font-medium sm:table-cell">Laps</th>
          </tr>
        </thead>
        <tbody>
          {#each leaderboard as row, index (row.steam_id || row.driver)}
            <tr class="border-b border-line/50 last:border-0">
              <td class="num px-3 py-2.5 {index === 0 ? 'text-accent' : 'text-muted'}">{index + 1}</td>
              <td class="px-3 py-2.5 font-medium">
                {row.driver || "Unknown"}
                <span class="num block text-[10px] text-muted/60 sm:hidden">{carLabel(row.car, dash.meta.cars)}</span>
              </td>
              <td class="hidden truncate px-3 py-2.5 text-xs text-muted sm:table-cell">
                {carLabel(row.car, dash.meta.cars)}
              </td>
              <td class="num px-3 py-2.5 text-right">{lapTime(row.best_ms)}</td>
              <td class="num px-3 py-2.5 text-right text-muted">{gap(row.best_ms, leaderboard[0].best_ms)}</td>
              <td class="num hidden px-3 py-2.5 text-right text-muted sm:table-cell">{row.laps}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if mode === "records"}
    <div class="card overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
            <th class="px-3 py-2 font-medium">Track</th>
            <th class="px-3 py-2 font-medium">Car</th>
            <th class="px-3 py-2 font-medium">Holder</th>
            <th class="px-3 py-2 text-right font-medium">Time</th>
            <th class="hidden px-3 py-2 text-right font-medium sm:table-cell">Date</th>
          </tr>
        </thead>
        <tbody>
          {#each records as row (row.track + row.car)}
            <tr class="border-b border-line/50 last:border-0">
              <td class="px-3 py-2.5 text-xs text-muted">{row.track}</td>
              <td class="truncate px-3 py-2.5">{carLabel(row.car, dash.meta.cars)}</td>
              <td class="px-3 py-2.5 font-medium">{row.driver || "Unknown"}</td>
              <td class="num px-3 py-2.5 text-right">{lapTime(row.best_ms)}</td>
              <td class="num hidden px-3 py-2.5 text-right text-muted sm:table-cell">{date(row.at)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="grid gap-3 lg:grid-cols-2">
      <div class="card overflow-hidden">
        {#each sessions as session (session.id)}
          <button
            class="flex w-full items-center gap-3 border-b border-line/50 px-3 py-2.5 text-left last:border-0
                   hover:bg-raised/50 {detail?.session?.id === session.id ? 'bg-raised/70' : ''}"
            onclick={() => openSession(session.id)}
          >
            <div class="min-w-0 flex-1">
              <span class="block truncate text-sm font-medium">{session.track || "Unknown track"}</span>
              <span class="num block text-[11px] text-muted">{date(session.started_at)} · {session.mode}</span>
            </div>
            <div class="num text-right text-xs text-muted">
              <span class="block">{session.drivers} drivers</span>
              <span class="block">{session.laps} laps · {lapTime(session.best_ms)}</span>
            </div>
          </button>
        {/each}
      </div>

      {#if detail?.session}
        <div class="card overflow-hidden self-start">
          <div class="border-b border-line px-3 py-2 text-sm">
            <span class="font-medium">{detail.session.track}</span>
            <span class="num ml-2 text-xs text-muted">{date(detail.session.started_at)}</span>
          </div>
          <table class="w-full text-sm">
            <tbody>
              {#each detail.standings as row, index (row.driver + row.car)}
                <tr class="border-b border-line/50 last:border-0">
                  <td class="num px-3 py-2 {index === 0 ? 'text-accent' : 'text-muted'}">{index + 1}</td>
                  <td class="px-3 py-2 font-medium">{row.driver || "Unknown"}</td>
                  <td class="truncate px-3 py-2 text-xs text-muted">{carLabel(row.car, dash.meta.cars)}</td>
                  <td class="num px-3 py-2 text-right">{lapTime(row.best_ms)}</td>
                  <td class="num px-3 py-2 text-right text-muted">{row.laps} laps</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  {/if}
</div>
