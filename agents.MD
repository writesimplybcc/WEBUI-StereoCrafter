# AGENTS.md

Always utilise sequential-thinking

## Development Workflow

### Starting the Development Server

The server is started with `bun run dev` (always running for development purposes):
- **Vite dev server**: `http://localhost:5173` (frontend with hot reload)
- **Express server**: `http://localhost:3006` (backend API)
- **OpenCode CLI**: port `3358` (AI backend)

**Frontend changes** (files in `src/`) reload **instantly** in the browser - no restart needed!

### When to Restart `bun run dev`

Only restart when:
1. **Backend changes** (`server/index.js`, Express routes)
2. **Package changes** (installed new npm package with `bun install`)
3. **Config changes** (`.env`, `vite.config.ts`)
4. **Weird errors** (sometimes a fresh restart helps)

### Stopping the Development Server

**Option 1: Ctrl+C** (recommended for the user)
- Press `Ctrl+C` in the terminal where `bun run dev` is running

**Option 2: Stop script** 
```bash
bun run dev:stop
```
or
```bash
powershell -ExecutionPolicy Bypass -File dev-stop.ps1
```

### Pro Tips

1. **Keep Terminal Visible** - Watch for errors in the terminal where `bun run dev` is running:
   ```
   [0] ✓ built in 123ms
   [1] [OpenCode] API is ready
   ```

## Architecture

- **SDK operations** (sessions, messages, permissions, providers): Use `@opencode-ai/sdk` v2 via `src/lib/opencode.ts`, routed through Express proxy at `/api`.
- **Express routes** (filesystem, git, terminal, MCP config): Handled directly in `server/index.js`.
- **SDK v2 response shape**: All responses wrapped in `{ data: ... }` — always unwrap with `resp?.data ?? resp`.

## Critical Quirks

- **Bun Windows `WriteFailed` panic**: MCP config writes in `server/index.js` must use `fs.promises.writeFile` (async), never sync writes.
- **OpenCode CORS**: Server spawns OpenCode with `--cors` flags (see `server/index.js`). If you see CORS errors, restart the dev server.
- **Vite polyfills**: `vite.config.ts` defines `process.env`, `process.platform`, `global` for browser builds — don't remove these or the SDK will fail.

## Configuration

- **Ports**: Set in `.env` (`PORT=3006`, `OPENCODE_PORT=3358`, `VITE_PORT=5173`).
- **Working directory**: `WORKING_DIR` in `.env` (default: `WORKSPACE/`). Can be relative to repo root or absolute.
- **OpenCode config**: `.opencode/opencode.jsonc` (copy from `.opencode/opencode.jsonc.example`). MCP servers, providers, permissions configured here.

## TypeScript

- Strict mode enabled with `noUnusedLocals` and `noUnusedParameters` — clean up unused vars/params in edited files.
- Target: ES2020, module: ESNext, JSX: react-jsx.

## File Scope

- Default working directory for AI operations: `WORKSPACE/` (or whatever `WORKING_DIR` points to).
- Only modify root-level code (`src/`, `server/`, `cli/`) when explicitly asked.
