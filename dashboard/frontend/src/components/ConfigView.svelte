<script>
  import { dash } from "../lib/state.svelte.js";
  import Section from "./Section.svelte";
  import Field from "./Field.svelte";
  import DurationField from "./DurationField.svelte";
  import CarPicker from "./CarPicker.svelte";
  import { duration } from "../lib/format.js";
  import { SESSION_PRESETS } from "../lib/presets.js";

  const server = $derived(dash.form.server);
  const event = $derived(dash.form.event);
  const isRace = $derived(/RACE_WEEKEND/i.test(event.type || ""));
  const sessionKeys = $derived(isRace ? ["practice", "qualify", "warmup", "race"] : ["practice"]);

  let showPasswords = $state(false);
</script>

<div class="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
  <Section title="Server" subtitle={server.server_name}>
    <div class="grid gap-3 sm:grid-cols-2">
      <Field label="Server name" wide>
        <input class="field" bind:value={server.server_name} />
      </Field>
      <Field label="Max players" hint={`Track limit: ${dash.pitLimit} pit slots`}>
        <input
          class="field num"
          type="number"
          min="1"
          max={dash.pitLimit}
          bind:value={server.max_players}
          onblur={() => dash.clampPlayers()}
        />
      </Field>
      <Field label="Server type">
        <select class="field" bind:value={server.server_type}>
          {#each dash.meta.enums.server_type as option (option.value)}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </Field>
      <Field label="Tuning">
        <select class="field" bind:value={server.tuning_type}>
          {#each dash.meta.enums.tuning_type as option (option.value)}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </Field>

      <label class="flex items-center justify-between rounded-xl bg-raised px-3 py-2.5 sm:col-span-2">
        <span class="text-sm">Cycle sessions</span>
        <input type="checkbox" class="size-4 accent-[var(--color-accent)]" bind:checked={server.cycle_enabled} />
      </label>

      <div class="sm:col-span-2">
        <div class="mb-1.5 flex items-center justify-between">
          <span class="text-xs font-medium text-muted">Passwords</span>
          <button class="text-[11px] text-muted hover:text-ink" onclick={() => (showPasswords = !showPasswords)}>
            {showPasswords ? "Hide" : "Show"}
          </button>
        </div>
        <div class="grid gap-2 sm:grid-cols-3">
          {#each [["driver_password", "Driver"], ["admin_password", "Admin"], ["spectator_password", "Spectator"]] as [key, label] (key)}
            <input
              class="field"
              type={showPasswords ? "text" : "password"}
              placeholder={label}
              bind:value={server[key]}
            />
          {/each}
        </div>
      </div>
    </div>
  </Section>

  <Section title="Event" subtitle={dash.track ? dash.track.display : ""} open={false}>
    <div class="grid gap-3 sm:grid-cols-2">
      <Field label="Mode" wide>
        <div class="grid grid-cols-2 gap-1 rounded-xl bg-raised p-1">
          {#each dash.meta.enums.event_type as option (option.value)}
            <button
              class="rounded-lg px-3 py-2 text-sm transition {event.type === option.value
                ? 'bg-accent font-semibold text-white'
                : 'text-muted hover:text-ink'}"
              onclick={() => dash.setEventType(option.value)}
            >
              {option.label}
            </button>
          {/each}
        </div>
      </Field>

      <Field label="Track" wide hint={dash.track ? `${(dash.track.length_m / 1000).toFixed(2)} km` : ""}>
        <select class="field" value={event.track} onchange={(e) => dash.setTrack(e.currentTarget.value)}>
          {#each dash.tracks as track (track.token)}
            <option value={track.token}>{track.display}</option>
          {/each}
        </select>
      </Field>

      <Field label="Weather">
        <select class="field" bind:value={event.weather}>
          {#each dash.meta.enums.weather as option (option.value)}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </Field>
      <Field label="Weather behaviour">
        <select class="field" bind:value={event.weather_behaviour}>
          {#each dash.meta.enums.weather_behaviour as option (option.value)}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </Field>
      <Field label="Initial grip" wide>
        <select class="field" bind:value={event.initial_grip}>
          {#each dash.meta.enums.initial_grip as option (option.value)}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </Field>
    </div>
  </Section>

  <Section
    title="Sessions"
    subtitle={sessionKeys.map((key) => duration(dash.form.sessions[key].length_sec)).join(" · ")}
    open={false}
  >
    {#if isRace}
      <div class="mb-3 flex flex-wrap gap-1.5">
        {#each SESSION_PRESETS as preset (preset.key)}
          <button
            class="rounded-full border border-line bg-raised px-3 py-1.5 text-xs hover:border-accent"
            title={preset.hint}
            onclick={() => dash.applySessionPreset(preset.key)}
          >
            {preset.label}
            <span class="num ml-1 text-[10px] text-muted">{preset.hint}</span>
          </button>
        {/each}
      </div>
    {/if}

    <div class="grid gap-4">
      {#each sessionKeys as key (key)}
        {@const session = dash.form.sessions[key]}
        <div class="rounded-xl bg-raised/40 p-3">
          <h3 class="mb-2 text-sm font-semibold capitalize">{key}</h3>
          <div class="grid gap-3 sm:grid-cols-2">
            {#if key === "race"}
              <Field label="Race length">
                <div class="mb-2 grid grid-cols-2 gap-1 rounded-xl bg-bg/60 p-1">
                  {#each dash.meta.enums.duration_type as option (option.value)}
                    <button
                      class="rounded-lg px-2 py-1.5 text-xs {session.duration_type === option.value
                        ? 'bg-accent font-semibold text-white'
                        : 'text-muted hover:text-ink'}"
                      onclick={() => (session.duration_type = option.value)}
                    >
                      {option.label}
                    </button>
                  {/each}
                </div>
                {#if /LAPS/i.test(session.duration_type || "")}
                  <input class="field num" type="number" min="1" bind:value={session.laps} />
                {:else}
                  <DurationField label="" bind:seconds={session.length_sec} />
                {/if}
              </Field>
            {:else}
              <DurationField label="Length" bind:seconds={session.length_sec} />
            {/if}
            <Field label="Start time">
              <div class="flex items-center gap-2">
                <input class="field num min-w-0" type="number" min="0" max="23" bind:value={session.hour} />
                <span class="text-muted">:</span>
                <input class="field num min-w-0" type="number" min="0" max="59" bind:value={session.minute} />
              </div>
            </Field>
            <Field label="Time multiplier">
              <input class="field num" type="number" min="0" bind:value={session.time_multiplier} />
            </Field>
          </div>
        </div>
      {/each}
    </div>
  </Section>

  <div class="lg:col-span-2 xl:col-span-3">
    <CarPicker />
  </div>

  <Section title="Advanced" subtitle="Ports, entry list, results" open={false}>
    <div class="grid gap-3 sm:grid-cols-2">
      <div class="rounded-xl bg-raised/40 p-3 sm:col-span-2">
        <p class="mb-2 text-[11px] text-muted">
          Ports are pinned by the container environment so they match the published Docker ports — changing them here
          has no effect until the stack changes too.
        </p>
        <div class="grid gap-3 sm:grid-cols-3">
          <Field label="TCP port"><input class="field num" type="number" bind:value={server.tcp_port} /></Field>
          <Field label="UDP port"><input class="field num" type="number" bind:value={server.udp_port} /></Field>
          <Field label="HTTP port"><input class="field num" type="number" bind:value={server.http_port} /></Field>
        </div>
      </div>

      <Field label="Entry list URL" wide hint="Server pulls the allowed SteamIDs from here">
        <input class="field" bind:value={server.entry_list_url} />
      </Field>
      <Field label="Entry list path" wide>
        <input class="field" bind:value={server.entry_list_path} />
      </Field>
      <Field label="Results POST URL" wide hint="Server pushes session results here">
        <input class="field" bind:value={server.results_post_url} />
      </Field>
      <Field label="Results path" wide hint="Server writes result files into this folder">
        <input class="field" bind:value={server.results_path} />
      </Field>
    </div>
  </Section>

  <Section
    title="Validation"
    subtitle={dash.report?.warnings?.length ? `${dash.report.warnings.length} warnings` : "ok"}
    open={false}
  >
    {#if dash.report?.warnings?.length}
      <ul class="space-y-1.5 text-xs">
        {#each dash.report.warnings as warning}
          <li class="flex gap-2 text-warn"><span aria-hidden="true">▲</span>{warning}</li>
        {/each}
      </ul>
    {:else}
      <p class="text-xs text-ok">Configuration is valid.</p>
    {/if}
  </Section>
</div>
