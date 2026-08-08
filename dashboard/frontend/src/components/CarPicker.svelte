<script>
  import { dash } from "../lib/state.svelte.js";
  import Section from "./Section.svelte";
  import { CAR_CLASSES } from "../lib/format.js";

  // Filters are UI state, not config — remembered locally so a reload does not
  // throw away the view you had set up.
  const STORAGE_KEY = "acevo.carfilters";
  const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

  let text = $state(stored.text || "");
  let types = $state(new Set(stored.types || []));
  let eras = $state(new Set(stored.eras || []));
  let engines = $state(new Set(stored.engines || []));
  let onlySelected = $state(stored.onlySelected || false);
  let piMin = $state(stored.piMin ?? dash.meta.pi_min);
  let piMax = $state(stored.piMax ?? dash.meta.pi_max);

  $effect(() => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        text,
        types: [...types],
        eras: [...eras],
        engines: [...engines],
        onlySelected,
        piMin,
        piMax,
      }),
    );
  });

  const byName = new Map(dash.meta.cars.map((car) => [car.internal_name, car]));
  const entry = (name) => dash.form.cars.find((car) => car.name === name);
  const selectedCount = $derived(dash.form.cars.filter((car) => car.is_selected).length);

  const visible = $derived.by(() => {
    const needle = text.trim().toLowerCase();
    return dash.meta.cars.filter((car) => {
      if (needle && !car.display_name.toLowerCase().includes(needle)) return false;
      if (types.size && !types.has(car.type)) return false;
      if (eras.size && !eras.has(car.era)) return false;
      if (engines.size && !engines.has(car.engine)) return false;
      if (car.pi < piMin || car.pi > piMax) return false;
      if (onlySelected && !entry(car.internal_name)?.is_selected) return false;
      return true;
    });
  });

  function toggleFacet(set, value) {
    const next = new Set(set);
    next.has(value) ? next.delete(value) : next.add(value);
    return next;
  }

  function setVisible(selected) {
    for (const car of visible) {
      const item = entry(car.internal_name);
      if (item) item.is_selected = selected;
    }
  }

  function invertVisible() {
    for (const car of visible) {
      const item = entry(car.internal_name);
      if (item) item.is_selected = !item.is_selected;
    }
  }

  // Only offer classes that actually exist in this build's car list, with their
  // size — a "GT3" chip that selects nothing is worse than no chip.
  const classes = $derived(
    CAR_CLASSES.map((entry) => ({ ...entry, count: dash.meta.cars.filter(entry.test).length })).filter(
      (entry) => entry.count > 0,
    ),
  );

  function selectClass(entry, additive) {
    for (const car of dash.form.cars) {
      const meta = byName.get(car.name);
      const matches = meta ? entry.test(meta) : false;
      if (additive) {
        if (matches) car.is_selected = true;
      } else {
        car.is_selected = matches;
      }
    }
  }

  const selectAll = (value) => dash.form.cars.forEach((car) => (car.is_selected = value));
</script>

<Section title="Cars" subtitle={`${selectedCount} of ${dash.meta.cars.length} selected`} open={false}>
  <div class="mb-1 flex flex-wrap gap-1.5">
    <button
      class="rounded-full border border-line bg-raised px-3 py-1.5 text-xs hover:border-accent"
      onclick={() => selectAll(true)}>All</button
    >
    <button
      class="rounded-full border border-line bg-raised px-3 py-1.5 text-xs hover:border-accent"
      onclick={() => selectAll(false)}>None</button
    >
    {#each classes as entry (entry.key)}
      <button
        class="flex items-center gap-1.5 rounded-full border border-line bg-raised px-3 py-1.5 text-xs hover:border-accent"
        title={`Click: only ${entry.label} · Shift-click: add to the selection`}
        onclick={(event) => selectClass(entry, event.shiftKey)}
      >
        {entry.label}
        <span class="num text-[10px] text-muted">{entry.count}</span>
      </button>
    {/each}
  </div>
  <p class="mb-3 text-[11px] text-muted/70">Click a class to race only that one, shift-click to add it.</p>

  <input class="field mb-2" placeholder="Filter by name…" bind:value={text} />

  <div class="mb-2 flex flex-wrap gap-1">
    {#each [["type", dash.meta.categories.type], ["era", dash.meta.categories.era], ["engine", dash.meta.categories.engine]] as [facet, options] (facet)}
      {#each options as option (option.value)}
        {@const active =
          facet === "type" ? types.has(option.value) : facet === "era" ? eras.has(option.value) : engines.has(option.value)}
        <button
          class="rounded-full px-2.5 py-1 text-[11px] {active ? 'bg-accent text-white' : 'bg-raised text-muted'}"
          onclick={() => {
            if (facet === "type") types = toggleFacet(types, option.value);
            else if (facet === "era") eras = toggleFacet(eras, option.value);
            else engines = toggleFacet(engines, option.value);
          }}
        >
          {option.label}
        </button>
      {/each}
    {/each}
  </div>

  <div class="mb-3 flex flex-wrap items-center gap-3 text-xs text-muted">
    <span class="num">PI {piMin} – {piMax}</span>
    <input type="range" class="flex-1" min={dash.meta.pi_min} max={dash.meta.pi_max} step="0.1" bind:value={piMin} />
    <input type="range" class="flex-1" min={dash.meta.pi_min} max={dash.meta.pi_max} step="0.1" bind:value={piMax} />
    <label class="flex items-center gap-1.5">
      <input type="checkbox" class="size-3.5 accent-[var(--color-accent)]" bind:checked={onlySelected} />
      only selected
    </label>
  </div>

  <div class="mb-2 flex items-center justify-between border-t border-line pt-2 text-xs text-muted">
    <span>{visible.length} shown</span>
    <span class="flex gap-2">
      <button class="hover:text-ink" onclick={() => setVisible(true)}>select shown</button>
      <button class="hover:text-ink" onclick={() => setVisible(false)}>clear shown</button>
      <button class="hover:text-ink" onclick={invertVisible}>invert</button>
    </span>
  </div>

  <div class="max-h-[26rem] overflow-y-auto rounded-xl border border-line">
    <!-- Balance of performance: ballast is whole units of added weight, the
         restrictor is fractional and throttles power. Both are passed to the
         server unvalidated, so the ranges are whatever AC EVO accepts. -->
    <div
      class="sticky top-0 z-10 flex items-center gap-3 border-b border-line bg-surface px-3 py-1.5
             text-[10px] uppercase tracking-wider text-muted"
    >
      <span class="w-4"></span>
      <span class="flex-1">Car</span>
      <span class="w-16 text-center" title="Added weight — makes the car slower">Ballast</span>
      <span class="w-16 text-center" title="Air restrictor — cuts power">Restr.</span>
    </div>
    {#each visible as car (car.internal_name)}
      {@const item = entry(car.internal_name)}
      {#if item}
        <label class="flex items-center gap-3 border-b border-line/60 px-3 py-2 last:border-0 hover:bg-raised/50">
          <input type="checkbox" class="size-4 shrink-0 accent-[var(--color-accent)]" bind:checked={item.is_selected} />
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm">{car.display_name}</span>
            <span class="num block text-[11px] text-muted">
              PI {car.pi} · {car.type}/{car.era}/{car.engine}
            </span>
          </span>
          <input
            class="field num w-16 px-2 py-1 text-xs"
            type="number"
            min="0"
            step="1"
            title="Ballast — added weight, whole numbers"
            bind:value={item.ballast}
          />
          <input
            class="field num w-16 px-2 py-1 text-xs"
            type="number"
            min="0"
            step="0.1"
            title="Restrictor — cuts power, fractional"
            bind:value={item.restrictor}
          />
        </label>
      {/if}
    {/each}
    {#if visible.length === 0}
      <p class="px-3 py-6 text-center text-xs text-muted">No car matches these filters.</p>
    {/if}
  </div>
</Section>
