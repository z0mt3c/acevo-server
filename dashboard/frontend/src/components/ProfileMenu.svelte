<script>
  import { dash } from "../lib/state.svelte.js";

  let open = $state(false);
  let root = $state(null);

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

  async function saveAs() {
    open = false;
    const name = prompt("Save the current configuration as a profile named:");
    if (name) await dash.saveProfile(name.trim());
  }

  async function remove(name, event) {
    event.stopPropagation();
    if (!confirm(`Delete profile "${name}"?`)) return;
    await dash.deleteProfile(name);
  }
</script>

<div class="relative" bind:this={root}>
  <button
    class="flex items-center gap-1.5 rounded-lg border border-line bg-raised px-2.5 py-1.5 text-xs text-muted
           hover:text-ink"
    onclick={() => (open = !open)}
  >
    <span aria-hidden="true">▤</span>
    Profiles
    <span class="text-[10px]">▾</span>
  </button>

  {#if open}
    <div class="card absolute left-0 top-full z-30 mt-2 w-64 overflow-hidden p-1 shadow-2xl">
      {#if dash.profiles.length === 0}
        <p class="px-3 py-2 text-xs text-muted">No profiles saved yet.</p>
      {:else}
        {#each dash.profiles as name (name)}
          <div class="group flex items-center rounded-lg hover:bg-raised">
            <button
              class="flex-1 px-3 py-2 text-left text-sm"
              onclick={() => {
                open = false;
                dash.applyProfile(name);
              }}
            >
              {name}
            </button>
            <button
              class="px-2 py-2 text-xs text-muted opacity-0 group-hover:opacity-100 hover:text-accent"
              aria-label={`Delete ${name}`}
              onclick={(event) => remove(name, event)}
            >
              ✕
            </button>
          </div>
        {/each}
      {/if}
      <div class="mt-1 border-t border-line pt-1">
        <button class="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-raised" onclick={saveAs}>
          + Save current as profile…
        </button>
      </div>
    </div>
  {/if}
</div>
