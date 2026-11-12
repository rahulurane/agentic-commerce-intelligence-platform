# ACIP Demo UI (React)

A self-contained React 18 + TypeScript + Vite single-page app that is a **thin
presentation layer** over the existing `checkout-api`. It POSTs a checkout to
`POST /v1/checkout`, then polls `GET /v1/transactions/{id}` for the six per-agent
verdicts (tolerating empty / partial / 404 while the agents commit). It never
re-implements any decision logic — the backend is the source of truth.

This project is **not** part of the Python uv workspace. It has its own
`package.json` + committed `package-lock.json`.

## Prerequisites

- Node 20 and npm (only needed for the host dev/build/test workflow; the Docker image
  builds the bundle in a `node:20-alpine` stage, so no host Node is needed to run the
  container).

## Scripts

```sh
npm ci          # install exact, locked deps
npm run dev     # Vite dev server on http://localhost:5173
npm run build   # tsc -b && vite build -> ui/dist
npm run preview # serve the built bundle locally
npm run lint    # eslint .
npm run format:check # prettier --check
npm run typecheck    # tsc --noEmit
npm run test    # vitest run (single run)
```

## Backend URL configuration

The checkout-api base URL comes from `import.meta.env.VITE_CHECKOUT_API_URL` and
defaults to `http://localhost:8080`.

**Decision:** the Docker image bakes this in at **build time** via the
`VITE_CHECKOUT_API_URL` build arg (see `ui/Dockerfile` and the `demo-ui` service in
`deploy/docker-compose.yml`, which sets it to `http://localhost:8080`). Because the
browser runs on the host, the URL must be the host-reachable published port
(`localhost:8080`), not the in-network service name. For local development, set it in a
`.env` file or inline:

```sh
VITE_CHECKOUT_API_URL=http://localhost:8080 npm run dev
```

## Where it runs

- **Docker mode:** served by nginx at <http://localhost:8090> (the `demo-ui` compose
  service).
- **Local mode:** the Vite dev server at <http://localhost:5173>.

## Design system and branding

- Styles live in `src/styles/`: `brand.css` (the only file with brand colours),
  `tokens.css` (semantic tokens, light and dark), `base.css`, `layout.css`,
  `components.css`. To re-skin the UI, edit the variables in `brand.css`.
- Logo slot: drop the official logo at `ui/src/assets/brand/logo.svg`. Until it exists
  the header shows a text wordmark (see `src/assets/brand/README.md`).
- Theme: light by default, with a dark toggle stored in `localStorage` (`acip.theme`).
- Decision thresholds shown in the UI live only in `src/config/thresholds.ts`. They are
  labelled as defaults and are never used to compute a decision (the backend decides).

## Help and tour

- Help guide: the `Help` header button or the `?` key (ignored while typing in a form
  field). `HelpDrawer` is loaded with `React.lazy`, so it builds into its own chunk.
  Copy is in `src/content/{help,glossary,tooltips,tour,stages}.ts`.
- Guided tour: six steps anchored by `data-tour` attributes, shown once on first load
  (`acip.tour.done` in `localStorage`). Replay it from the header `Tour` button, the
  empty state or the Help guide.

## Configuration

- `VITE_CHECKOUT_API_URL`: checkout-api base URL (default `http://localhost:8080`).
- `VITE_JAEGER_URL`: target of the "Open Jaeger" link (default `http://localhost:16686`).
