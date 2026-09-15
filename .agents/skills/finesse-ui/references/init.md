# Init — Set Up Project Design Memory

`init` writes a **`PRODUCT.md`** at the project root: the persistent brief finesse reads before every later task, so multi-page projects stay consistent and you stop re-guessing the register/soul/dials each time. Run it once per project (or when the brief has materially changed).

> Why this exists: finesse's §3 color-lock and §5 theme-lock are easy to *state* but hard to *hold* across many pages and many sessions. A committed `PRODUCT.md` is the anchor — the next page reads it instead of drifting.

---

## When to run

- The user starts a new project, or asks to "set up finesse / init".
- Any task begins and **no `PRODUCT.md` exists** at the project root → offer to run `init` first (don't force it; a one-off page doesn't need memory).
- `document` (existing code → `design-model.yaml`) is the companion: `init` captures *intent*, `document` captures *the system already built*. For a brand-new project run `init`; for an existing codebase run both.

---

## Flow

1. **Gather the brief.** From what the user gave you, fill as much as you can. For anything load-bearing and missing, ask **one** sharp question (§0.C discipline) — don't interrogate.
2. **Lock the Three Dials** as project defaults (individual pages can deviate with a reason).
3. **Name the anti-references** — the lazy defaults this brand must avoid, at both altitudes (`anti-cheap.md` §0).
4. **Write `PRODUCT.md`** in the shape below. Keep it short and committed — vague memory is worse than none.
5. Confirm the file with the user, then proceed to the original task reading it as the brief.

---

## PRODUCT.md shape

```markdown
# {Project} — finesse brief

register: {brand | product}            # decides soul+engine vs component+density
one-liner: {what this product literally is, no buzzwords}

## Users & context
{who uses it, where, under what light/mood — the physical scene that forces the theme}

## Brand personality
soul: {the persona — e.g. "cinematic + reverent", maps to style-personas.md}
voice: {2-3 adjectives for copy tone}

## Locked dials (project defaults)
SOUL: {1-10}   SPECTACLE: {1-10}   DENSITY: {1-10}

## Visual lock
accent: {the one accent that owns every page — name + OKLCH/hex}
theme: {dark | light, with the one-sentence scene that forced it}
type: {display family + body family + optional mono, each with the reason}

## Anti-references (must NOT look like)
- first-order: {category default rejected — "coffee → beige+brass"}
- second-order: {the obvious anti-reference also rejected — "not SaaS-cream → not editorial-typographic-by-reflex"}
- {any specific competitor/aesthetic the user named as off-limits}

## Notes
{anything else that constrains design but isn't in the code}
```

---

## Rules

- **Tell the user what got locked, and how to unlock it.** Writing the file silently is how page 5 becomes a mystery: he asks for a different color, finesse holds the line, and he has no idea what is holding it or where. One short notice at write time, naming the constraints in plain terms and the sentence that releases them — never the filename or the schema (`plain-words.md`):

  ```
  Locked for this project: warm amber accent (#C8A06A), Fraunces headlines, dark theme.
  Every later page will follow these. Say "change the accent" (or the type, or the theme)
  and I'll update this page and the ones already built.
  ```

  The same applies when `document` writes `design-model.yaml`. A constraint the user can't see is one he'll experience as the tool being stubborn.
- **`PRODUCT.md` overrides your guesses.** Once it exists, §0 Brand Read reads it instead of inferring register/soul from scratch. If the user's new request contradicts it, surface the conflict rather than silently overriding.
- **Don't pad it.** Every line is a constraint the next page must honor. If you don't know a field, ask or leave it explicitly `TBD` — never invent a confident-sounding default.
- **Dials are defaults, not handcuffs.** A single page may run hotter/cooler SPECTACLE with a stated reason; the locked value is the gravity it returns to.
- After writing it, if the project already has code, suggest running `document` to capture the built design system as `design-model.yaml`.
