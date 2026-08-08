<script>
  import { dash } from "../lib/state.svelte.js";

  let open = $state(false);
  let root = $state(null);

  // Close on any click outside, without hanging a handler on a plain <div>.
  $effect(() => {
    if (!open) return;
    const close = (event) => {
      if (root && !root.contains(event.target)) open = false;
    };
    const escape = (event) => event.key === "Escape" && (open = false);
    document.addEventListener("click", close, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("click", close, true);
      document.removeEventListener("keydown", escape);
    };
  });

  // The primary action is whatever the server state calls for; everything else
  // lives behind the caret. Six equal buttons was the old mistake.
  const primary = $derived(
    dash.status.running ? { key: "restart", label: "Restart", icon: "↻" } : { key: "start", label: "Start", icon: "▶" },
  );
  const rest = $derived(
    [
      dash.status.running ? { key: "stop", label: "Stop", icon: "■" } : null,
      dash.status.running ? null : { key: "restart", label: "Restart", icon: "↻" },
      { key: "update", label: "Update via SteamCMD", icon: "⭳" },
    ].filter(Boolean),
  );

  function run(key) {
    open = false;
    if (key === "stop" && !confirm("Stop the server? Connected drivers get disconnected.")) return;
    if (key === "update" && !confirm("Run a SteamCMD update? The server stops and restarts.")) return;
    dash.serverAction(key);
  }
</script>

<div class="relative flex" bind:this={root}>
  <button
    class="flex items-center gap-2 rounded-l-xl bg-accent px-4 py-2 font-semibold text-white
           disabled:opacity-50 active:scale-[0.98]"
    disabled={dash.busy || dash.status.update?.running}
    onclick={() => run(primary.key)}
  >
    <span aria-hidden="true">{primary.icon}</span>
    <span class="hidden sm:inline">{primary.label}</span>
  </button>
  <button
    class="rounded-r-xl border-l border-black/25 bg-accent px-2 py-2 text-white disabled:opacity-50"
    disabled={dash.busy}
    aria-label="More server actions"
    onclick={() => (open = !open)}
  >
    ▾
  </button>

  {#if open}
    <div class="card absolute right-0 top-full z-30 mt-2 w-56 overflow-hidden p-1 shadow-2xl">
      {#each rest as item (item.key)}
        <button
          class="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-raised"
          onclick={() => run(item.key)}
        >
          <span class="w-4 text-muted" aria-hidden="true">{item.icon}</span>
          {item.label}
        </button>
      {/each}
    </div>
  {/if}
</div>
