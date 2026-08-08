<script>
  import { dash } from "../lib/state.svelte.js";

  let open = $state(false);
  let root = $state(null);
  // In the bottom nav the trigger sits at the very bottom of the screen, so a
  // menu that always drops downwards is invisible. Flip it when there is more
  // room above than below.
  let dropUp = $state(false);

  function toggle() {
    if (!open && root) {
      const box = root.getBoundingClientRect();
      dropUp = window.innerHeight - box.bottom < 280;
    }
    open = !open;
  }

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
    onclick={toggle}
  >
    <span aria-hidden="true">▤</span>
    Profiles
    <span class="text-[10px]">▾</span>
  </button>

  {#if open}
    <div
      class="card absolute z-30 w-64 overflow-hidden p-1 shadow-2xl {dropUp
        ? 'bottom-full mb-2 right-0'
        : 'top-full mt-2 left-0'}"
    >
      {#if dash.profiles.length === 0}
        <p class="px-3 py-2 text-xs text-muted">No profiles saved yet.</p>
      {:else}
        {#each dash.profiles as profile (profile.name)}
          <div class="group flex items-center rounded-lg hover:bg-raised">
            <button
              class="min-w-0 flex-1 px-3 py-2 text-left"
              onclick={() => {
                open = false;
                dash.applyProfile(profile.name);
              }}
            >
              <span class="block truncate text-sm">{profile.name}</span>
              <span class="block truncate text-[11px] text-muted">
                {(profile.track || "").split("|").slice(0, 2).join(" ")}
                {profile.mode ? `· ${/RACE_WEEKEND/i.test(profile.mode) ? "Race" : "Practice"}` : ""}
              </span>
            </button>
            <button
              class="px-2 py-2 text-xs text-muted opacity-0 group-hover:opacity-100 hover:text-accent"
              aria-label={`Delete ${profile.name}`}
              onclick={(event) => remove(profile.name, event)}
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
