# AC EVO MCP server

Exposes the dashboard's HTTP API as MCP tools, so an assistant can read the race
state and change the configuration.

## Run

```bash
ACEVO_URL=https://acevo.example.w0rk.de uvx --from . acevo-mcp
```

| Variable                        | Default                 | Meaning                                             |
| ------------------------------- | ----------------------- | --------------------------------------------------- |
| `ACEVO_URL`                     | `http://127.0.0.1:8090` | dashboard base URL                                  |
| `ACEVO_USER` / `ACEVO_PASSWORD` | empty                   | only needed if the dashboard has basic auth enabled |
| `ACEVO_VERIFY`                  | `true`                  | set to `false` for an internal TLS certificate      |

## Claude Code / Claude Desktop

```json
{
  "mcpServers": {
    "acevo": {
      "command": "uvx",
      "args": ["--from", "/path/to/acevo-server/mcp-server", "acevo-mcp"],
      "env": { "ACEVO_URL": "https://acevo.example.w0rk.de", "ACEVO_VERIFY": "false" }
    }
  }
}
```

## Tools

Reading: `status`, `get_config`, `list_tracks`, `list_cars`, `logs`,
`list_profiles`, `list_results`.

Changing: `set_track`, `set_mode`, `set_session`, `set_server_options`,
`select_cars`, `balance_by_pi`, `apply_profile`, `save_profile`, `control`.

Every changing tool fetches the current configuration, edits it and saves it in
one call, so a failure never leaves a half-written config behind. They all take
`apply` — `false` (the default) only saves, `true` also restarts the server,
which disconnects anyone on track.

`set_mode` carries the same track-matching rule as the dashboard: the same
circuit has a different token per mode because the event name is part of it, so
it matches on track and layout. Tracks that only exist in one mode (Nürburgring
Touristenfahrten has no race variant) fall back to the first entry, and the
answer says so via `track_kept`.
