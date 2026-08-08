<script>
  import { dash } from "../lib/state.svelte.js";
  import { lapTime, carLabel } from "../lib/format.js";

  const drivers = $derived(dash.live.drivers || []);
  const onTrack = $derived(drivers.filter((driver) => driver.connected));
  const gone = $derived(drivers.filter((driver) => !driver.connected));
  const fastest = $derived(
    onTrack.reduce((best, d) => (d.best_lap_ms && (!best || d.best_lap_ms < best) ? d.best_lap_ms : best), null),
  );

  const delta = (ms) => (ms == null || fastest == null || ms === fastest ? null : `+${((ms - fastest) / 1000).toFixed(3)}`);
</script>

<div class="grid gap-3">
  <div class="grid grid-cols-3 gap-3">
    {#each [["On track", onTrack.length], ["Connected", dash.live.clients ?? "—"], ["Slots", dash.form.server.max_players]] as [label, value] (label)}
      <div class="card px-4 py-3">
        <div class="text-[11px] uppercase tracking-wider text-muted">{label}</div>
        <div class="num mt-1 text-2xl">{value}</div>
      </div>
    {/each}
  </div>

  {#if drivers.length === 0}
    <div class="card px-4 py-12 text-center">
      <p class="text-sm text-muted">
        {dash.status.running ? "Nobody on track." : "Server is stopped."}
      </p>
      <p class="mt-1 text-xs text-muted/60">
        Drivers show up here as soon as they connect — name, car and lap times come from the server log.
      </p>
    </div>
  {:else}
    <div class="card overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
            <th class="px-3 py-2 font-medium">#</th>
            <th class="px-3 py-2 font-medium">Driver</th>
            <th class="hidden px-3 py-2 font-medium sm:table-cell">Car</th>
            <th class="px-3 py-2 text-right font-medium">Laps</th>
            <th class="px-3 py-2 text-right font-medium">Best</th>
            <th class="hidden px-3 py-2 text-right font-medium sm:table-cell">Last</th>
          </tr>
        </thead>
        <tbody>
          {#each [...onTrack, ...gone] as driver (driver.car_id)}
            <tr class="border-b border-line/50 last:border-0 {driver.connected ? '' : 'opacity-40'}">
              <td class="num px-3 py-2.5 text-muted">{driver.number ?? "—"}</td>
              <td class="px-3 py-2.5">
                <div class="flex items-center gap-2">
                  <span class="size-1.5 rounded-full {driver.connected ? 'bg-ok' : 'bg-muted/40'}"></span>
                  <span class="truncate font-medium">{driver.name || "Unknown"}</span>
                </div>
                <span class="num block text-[10px] text-muted/60 sm:hidden">
                  {carLabel(driver.car, dash.meta.cars)}
                </span>
              </td>
              <td class="hidden truncate px-3 py-2.5 text-xs text-muted sm:table-cell">
                {carLabel(driver.car, dash.meta.cars)}
              </td>
              <td class="num px-3 py-2.5 text-right">{driver.laps}</td>
              <td class="num px-3 py-2.5 text-right">
                {lapTime(driver.best_lap_ms)}
                {#if delta(driver.best_lap_ms)}
                  <span class="block text-[10px] text-muted">{delta(driver.best_lap_ms)}</span>
                {/if}
              </td>
              <td class="num hidden px-3 py-2.5 text-right text-muted sm:table-cell">{lapTime(driver.last_lap_ms)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
