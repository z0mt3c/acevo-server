<script>
  import { api } from "../lib/api.js";

  let lines = $state([]);
  let text = $state("");
  let level = $state("all");
  let follow = $state(true);
  let tail = $state(400);
  let container = $state(null);

  const LEVELS = { error: "text-accent", warning: "text-warn", info: "text-ink/80" };

  function classify(line) {
    if (/\[error\]/i.test(line)) return "error";
    if (/\[warning\]/i.test(line)) return "warning";
    return "info";
  }

  const shown = $derived.by(() => {
    const needle = text.trim().toLowerCase();
    return lines.filter((line) => {
      if (level !== "all" && classify(line) !== level) return false;
      if (needle && !line.toLowerCase().includes(needle)) return false;
      return true;
    });
  });

  async function refresh() {
    const result = await api.logs(tail);
    lines = (result.lines || "").split("\n").filter(Boolean);
    if (follow && container) {
      // Wait for the DOM to grow before jumping to the end.
      requestAnimationFrame(() => (container.scrollTop = container.scrollHeight));
    }
  }

  $effect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  });

  /** Scrolling up means "let me read" — stop yanking the view to the bottom. */
  function onScroll() {
    if (!container) return;
    const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 40;
    if (!atBottom && follow) follow = false;
  }

  const copy = () => navigator.clipboard?.writeText(shown.join("\n"));
</script>

<div class="card flex h-[calc(100dvh-13rem)] flex-col overflow-hidden md:h-[calc(100dvh-10rem)]">
  <div class="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
    <input class="field flex-1 min-w-[8rem] py-1.5 text-sm" placeholder="Search…" bind:value={text} />
    <select class="field w-auto py-1.5 text-sm" bind:value={level}>
      <option value="all">all</option>
      <option value="error">errors</option>
      <option value="warning">warnings</option>
      <option value="info">info</option>
    </select>
    <select class="field w-auto py-1.5 text-sm" bind:value={tail} onchange={refresh}>
      {#each [200, 400, 1000, 5000] as size (size)}
        <option value={size}>{size} lines</option>
      {/each}
    </select>
    <button
      class="rounded-lg px-3 py-1.5 text-sm {follow ? 'bg-accent text-white' : 'bg-raised text-muted'}"
      onclick={() => {
        follow = !follow;
        if (follow && container) container.scrollTop = container.scrollHeight;
      }}
    >
      Follow
    </button>
    <button class="rounded-lg bg-raised px-3 py-1.5 text-sm text-muted hover:text-ink" onclick={copy}>Copy</button>
  </div>

  <div bind:this={container} onscroll={onScroll} class="flex-1 overflow-auto px-3 py-2">
    <!-- Keyed by index, not by content: a log repeats identical lines all the
         time, and duplicate keys make Svelte throw instead of render. -->
    <pre class="num text-[11.5px] leading-[1.5]">{#each shown as line, index (index)}<span
          class="block whitespace-pre-wrap {LEVELS[classify(line)]}">{line}</span
        >{/each}</pre>
    {#if shown.length === 0}
      <p class="py-8 text-center text-xs text-muted">Nothing matches — or the server has not logged anything yet.</p>
    {/if}
  </div>

  <div class="border-t border-line px-3 py-1.5 text-[11px] text-muted">
    {shown.length} of {lines.length} lines{level !== "all" || text ? " (filtered)" : ""}
  </div>
</div>
