<script>
  let { label, hint = "", wide = false, children } = $props();
</script>

<label class="block {wide ? 'sm:col-span-2' : ''}">
  <span class="mb-1.5 block text-xs font-medium text-muted">{label}</span>
  {@render children()}
  {#if hint}
    <span class="mt-1 block text-[11px] text-muted/70">{hint}</span>
  {/if}
</label>
