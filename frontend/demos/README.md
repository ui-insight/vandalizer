# Reproducible product demos

Each JSON file in `demos/recipes/` is a versioned product-demo recipe. It captures the details that must remain stable when the interface changes: the bundled source document and checksum, exact request, captions, pacing, approval gate, editorial cuts, branding, and voice-over settings.

Generated MP4s, raw recordings, audio, posters, and run timelines are deliberately ignored under `public/videos/generated/`. They can be recreated from a recipe and must not be hand-edited into the repository.

## Validate every recipe

From `frontend`:

```bash
npm run demo:check
```

This is offline. It validates the schema-level fields and confirms the checked-in source document and AI4RA logo match the SHA-256 values in each recipe.

## Re-render a demo after an interface change

The renderer creates a new isolated local recording account for each run. Login is intentionally outside the recorded context. It uploads only the recipe’s bundled sample document and performs the explicit in-product confirmation recorded in the recipe.

```bash
MINDROUTER_API_KEY='…' DEMO_ORIGIN=http://127.0.0.1 npm run demo:render -- ai4ra-proposal-review
```

`MINDROUTER_API_KEY` is read only at runtime to synthesize the committed voice-over script; it is never written to the recipe, manifest, or logs. Set `DEMO_ACCOUNT_PASSWORD` only if a fixed local recording password is required. Otherwise the renderer creates one in memory for its ephemeral account.

The run produces ignored artifacts in `public/videos/generated/`: the raw recording, milestone timeline, paced product footage, AI4RA-branded narrated MP4, and poster still.

To re-run only the deterministic post-production pass from the last raw recording and timeline, use:

```bash
npm run demo:render -- ai4ra-proposal-review --render-only
```

The recipe’s edit segments refer to product milestones rather than fixed wall-clock timestamps. That is what lets the same narrative survive variable model latency and a future UI refresh.
