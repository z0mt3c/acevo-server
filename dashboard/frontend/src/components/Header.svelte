<script>
  import { dash } from "../lib/state.svelte.js";
  import ActionMenu from "./ActionMenu.svelte";
  import ProfileMenu from "./ProfileMenu.svelte";

  const running = $derived(dash.status.running);
  const updating = $derived(dash.status.update?.running);
  const online = $derived(dash.live.clients ?? dash.live.players ?? 0);
</script>

<header class="sticky top-0 z-20 border-b border-line bg-bg/95 backdrop-blur">
  <div class="mx-auto flex max-w-[1600px] items-center gap-3 px-3 py-2.5 sm:px-5">
    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <span
          class="size-2.5 shrink-0 rounded-full {updating
            ? 'bg-warn led-live'
            : running
              ? 'bg-ok led-live'
              : 'bg-muted/50'}"
          aria-hidden="true"
        ></span>
        <span class="truncate text-sm font-semibold">
          {dash.form?.server.server_name || "AC EVO Server"}
        </span>
      </div>
      <div class="mt-0.5 flex items-center gap-2 truncate text-xs text-muted">
        <span>{updating ? "Updating…" : running ? "Running" : "Stopped"}</span>
        {#if dash.track}
          <span aria-hidden="true">·</span>
          <span class="truncate">{dash.track.track} {dash.track.layout}</span>
        {/if}
        {#if running}
          <span aria-hidden="true">·</span>
          <span class="num">{online}/{dash.form?.server.max_players ?? "?"}</span>
        {/if}
      </div>
    </div>

    <div class="hidden sm:block"><ProfileMenu /></div>
    <ActionMenu />
  </div>
</header>
