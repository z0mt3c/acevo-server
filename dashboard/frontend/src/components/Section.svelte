<script>
  // Collapsible on phones, always open from md up: on a wide screen the columns
  // are the structure, on a narrow one the accordion is.
  let { title, subtitle = "", open = $bindable(true), children } = $props();
</script>

<section class="card overflow-hidden">
  <button
    class="flex w-full items-center gap-3 px-4 py-3 text-left md:cursor-default"
    onclick={() => (open = !open)}
    aria-expanded={open}
  >
    <div class="min-w-0 flex-1">
      <h2 class="text-[13px] font-semibold uppercase tracking-wider text-muted">{title}</h2>
      {#if subtitle}
        <p class="mt-0.5 truncate text-xs text-muted/70">{subtitle}</p>
      {/if}
    </div>
    <span class="text-muted transition-transform md:hidden {open ? 'rotate-90' : ''}" aria-hidden="true">›</span>
  </button>

  <div class="{open ? 'block' : 'hidden'} md:block">
    <div class="border-t border-line px-4 py-4">
      {@render children()}
    </div>
  </div>
</section>
