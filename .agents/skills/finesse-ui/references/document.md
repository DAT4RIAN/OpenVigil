# Document — Capture an Existing Project's Design System

`document` reads the code that's already there and writes a **`design-model.yaml`** (the format in `design-model.md`) — the de-facto soul, palette, type, substrate, and engine, extracted rather than invented. It's the companion to `init`: `init` captures *intent* (`PRODUCT.md`); `document` captures *the system already built* (`design-model.yaml`).

> Don't invent a second format. finesse already has `design-model.yaml` as its machine-readable token model — `document` populates it from real code, so later pages read it and match instead of drifting.

---

## When to run

- An existing codebase needs new pages/sections that must match what's there.
- The user asks to "extract / capture / document the design system".
- You're about to `redesign` and want a diffable record of the current soul before touching it.

---

## Flow

1. **Read the real tokens.** Open the CSS/theme/token files and a representative page or two. Pull *actual* values, not aspirational ones — what the code does, not what a brief wishes.
2. **Infer the soul.** From palette + type + motion, name the closest persona (`style-personas.md`) and estimate the Three Dials as-built. Note honestly if the code is inconsistent (two accents, mixed radii) — that's a finding, not something to smooth over.
3. **Inventory the engine.** Is there a real hero engine (Three.js/Canvas/GSAP/CSS)? What's its reduced-motion behavior? Record what exists, flag what's missing.
4. **Write `design-model.yaml`** per the template in `design-model.md`. For a 3+ page project, use the `MASTER.yaml` + page-overrides layout from that file.
5. **Report drift.** List where the code violates its own system (accent drift, untinted neutrals, missing reduced-motion) so the user can decide whether `document` should also trigger a `redesign`.

---

## What to extract (map to the `design-model.yaml` template)

- **color** — bg / surface / ink / muted / dim / accent(s) / border, as they actually appear. Mark the real accent (the one used most on interactive/brand elements). Name the `strategy` (restrained / committed / full / drenched).
- **type** — display + body + mono families, weights, the de-facto scale ratio, display tracking/leading.
- **substrate** — grain opacity (or "none — missing"), vignette y/n, the radius scale, the dominant motion easing.
- **hero_engine** — type + a one-line detail + the reduced-motion behavior (or "none").
- **structure** — section sequence, the layout families in use, the nav pattern.

---

## Rules

- **Extract, don't aspire.** If the code uses `#ffffff` and hard `#333` borders, write that down — then list it under drift. `document` records reality; `redesign` fixes it. Keep the two steps honest and separate.
- **One source of truth.** After `document`, `design-model.yaml` is what later pages read. If it disagrees with a fresh `PRODUCT.md` brief, surface the gap (the built system may have drifted from the intent).
- **Confidence, not invention.** Where the code is silent (no documented reason for a font), record the value and mark the rationale `inferred`. Don't manufacture a backstory.
