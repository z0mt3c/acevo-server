<script>
  import { splitDuration, joinDuration, duration } from "../lib/format.js";

  // The API speaks seconds; nobody thinks in "10800".
  let { label, seconds = $bindable(0) } = $props();

  const parts = $derived(splitDuration(seconds));

  function update(hours, minutes) {
    seconds = joinDuration(hours, minutes);
  }
</script>

<div class="block">
  <span class="mb-1.5 flex items-baseline justify-between text-xs font-medium text-muted">
    {label}
    <span class="num text-[11px] text-muted/70">{duration(seconds)}</span>
  </span>
  <div class="flex items-center gap-2">
    <div class="relative min-w-0 flex-1">
      <input
        class="field num pr-8"
        type="number"
        min="0"
        max="99"
        value={parts.hours}
        oninput={(event) => update(event.currentTarget.value, parts.minutes)}
      />
      <span class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">h</span>
    </div>
    <div class="relative flex-1">
      <input
        class="field num pr-10"
        type="number"
        min="0"
        max="59"
        value={parts.minutes}
        oninput={(event) => update(parts.hours, event.currentTarget.value)}
      />
      <span class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">min</span>
    </div>
  </div>
</div>
