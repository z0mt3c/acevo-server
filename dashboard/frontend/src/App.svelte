<script>
  import { dash } from "./lib/state.svelte.js";
  import Header from "./components/Header.svelte";
  import ConfigView from "./components/ConfigView.svelte";
  import LogsView from "./components/LogsView.svelte";
  import LiveView from "./components/LiveView.svelte";
  import HistoryView from "./components/HistoryView.svelte";
  import ProfileMenu from "./components/ProfileMenu.svelte";

  let view = $state("config");
  let ready = $state(false);
  let error = $state("");

  const TABS = [
    { key: "config", label: "Config", icon: "⚙" },
    { key: "live", label: "Live", icon: "◉" },
    { key: "history", label: "History", icon: "⏱" },
    { key: "logs", label: "Logs", icon: "▤" },
  ];

  $effect(() => {
    dash
      .load()
      .then(() => (ready = true))
      .catch((cause) => (error = String(cause)));
    const timer = setInterval(() => dash.refreshStatus(), 5000);
    return () => clearInterval(timer);
  });

  // Revalidate while typing, but not on every keystroke.
  let validateTimer;
  $effect(() => {
    JSON.stringify(dash.form);
    if (!ready) return;
    clearTimeout(validateTimer);
    validateTimer = setTimeout(() => dash.validate(), 600);
  });
</script>

{#if error}
  <div class="p-6 text-sm text-accent">Could not load the dashboard: {error}</div>
{:else if !ready}
  <div class="grid h-dvh place-items-center text-sm text-muted">Loading…</div>
{:else}
  <Header />

  <main class="mx-auto max-w-[1600px] px-3 pb-32 pt-3 sm:px-5 md:pb-24">
    <nav class="mb-3 hidden gap-1 rounded-xl bg-surface p-1 md:inline-flex">
      {#each TABS as tab (tab.key)}
        <button
          class="rounded-lg px-4 py-2 text-sm transition {view === tab.key
            ? 'bg-raised font-semibold text-ink'
            : 'text-muted hover:text-ink'}"
          onclick={() => (view = tab.key)}
        >
          {tab.label}
        </button>
      {/each}
    </nav>

    {#if view === "config"}
      <ConfigView />
    {:else if view === "live"}
      <LiveView />
    {:else if view === "history"}
      <HistoryView />
    {:else}
      <LogsView />
    {/if}
  </main>

  <!-- Change bar: only shows up when there is something to save. -->
  {#if dash.dirty}
    <div class="fixed inset-x-0 bottom-[4.25rem] z-30 px-3 md:bottom-4">
      <div
        class="mx-auto flex max-w-[1600px] items-center gap-2 rounded-2xl border border-accent/40 bg-raised/95
               px-3 py-2.5 shadow-2xl backdrop-blur"
      >
        <span class="num flex-1 text-sm">
          {dash.changes}
          {dash.changes === 1 ? "change" : "changes"}
        </span>
        <button class="rounded-lg px-3 py-2 text-sm text-muted hover:text-ink" onclick={() => dash.discard()}>
          Discard
        </button>
        <button
          class="rounded-lg bg-raised px-3 py-2 text-sm ring-1 ring-line hover:ring-accent"
          disabled={dash.busy}
          onclick={() => dash.save()}
        >
          Save
        </button>
        <button
          class="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          disabled={dash.busy}
          onclick={() => dash.save({ apply: true })}
        >
          Save & apply
        </button>
      </div>
    </div>
  {/if}

  <nav
    class="fixed inset-x-0 bottom-0 z-20 grid grid-cols-5 border-t border-line bg-bg/95 pb-[env(safe-area-inset-bottom)]
           backdrop-blur md:hidden"
  >
    {#each TABS as tab (tab.key)}
      <button
        class="flex flex-col items-center gap-0.5 py-2.5 text-[11px] {view === tab.key ? 'text-accent' : 'text-muted'}"
        onclick={() => (view = tab.key)}
      >
        <span class="text-base" aria-hidden="true">{tab.icon}</span>
        {tab.label}
      </button>
    {/each}
    <div class="flex items-center justify-center py-2.5"><ProfileMenu /></div>
  </nav>

  {#if dash.toastMessage}
    <div class="fixed inset-x-0 top-16 z-40 flex justify-center px-4">
      <div class="card max-w-md px-4 py-2.5 text-sm shadow-2xl">{dash.toastMessage}</div>
    </div>
  {/if}
{/if}
