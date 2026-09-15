# Theming — Runtime Palette Switching (When the Brief Asks for It)

`design-dna.md`'s color-lock (§3) assumes **one palette per shipped page** — that's still the default. Some briefs explicitly ask for more: a light/dark toggle, or a small set of swappable named themes the visitor (or the client previewing the build) can pick between at runtime. This file is the decision protocol + token architecture for *that* case.

**Don't reach for this unprompted.** A locked single palette is simpler, has no light/dark-safe-value tax on every token, and is what §3 already covers. Build a theme switcher only when the brief actually asks for one.

---

## 1. Full themes, not accent recolors

A theme swap must move the **whole coordinated system** together — bg, surface tones, ink, muted, dim, border, AND accent. Swapping only the accent hue while every "theme" keeps the same near-black bg reads as *one theme with five different highlight colors*, not five themes — a common near-miss: it technically responds to a click, but nothing about the page actually looks different.

**Boundary: an accent-only color picker is fine *alongside* a real light/dark toggle, but is not itself a theme.** A product dashboard letting a user pick a highlight hue (teal/indigo/plum/rose/…) while a *separate* control flips the whole surface stack light↔dark satisfies this section — the accent picker only ever recolors `--accent`/`--accent-light`/`--accent-dark` variants of whichever register (light or dark) is already active, and the dark toggle is the thing doing the real bg/ink/border swap described above. Keep the two controls conceptually separate in the implementation too: `applyTheme(name)` (accent-only) should read whether dark mode is on and pick that hue's dark-safe variant, then `applyMode(dark)` re-applies the current accent so neither one clobbers the other. Persist both independently to `localStorage`. What's *not* fine: presenting the hue swatches as if they were "themes" when the bg/ink never move — that's the "N shades of the same color, not N themes" near-miss above, just relabeled as a picker.

If the brief wants light options, ship an **actual light register** (`design-dna.md`'s light-page token convention: tinted off-white bg, near-black ink, a light-value `--dim` reserved for hairlines only) alongside the dark ones. Don't just nudge the same dark base a few percent lighter/darker per "theme" — that produces N shades of the same color, not N themes. A good spread: 2-3 genuinely dark jewel-tones + 1-2 genuinely light registers (pull straight from `design-dna.md`'s documented palette families — "Editorial light", "Quiet luxury light" — rather than inventing light values from scratch; they're already contrast-checked).

---

## 2. Token roles must survive the swap

Respect what each token means (`design-dna.md` §1) even as the *values* flip between themes:

- **`--dim` is for hairlines and tertiary decorative marks only — never real body text.** A dim value tuned to be "a bit visible" against a dark bg is, by definition, close to the bg — flip to a light theme and that same low-contrast logic makes it nearly invisible, because light-page `--dim` is *defined* as a barely-there hairline tone. Any CSS rule using `var(--dim)` as the color of real copy (a footer link, a caption, a list bullet's own label) is a latent bug that only surfaces the moment someone actually switches registers. Audit every `color: var(--dim)` call site before shipping multi-theme; route real secondary text through `--muted` instead, which is defined to stay legible in both registers.
- **`--ink` and `--bg` conceptually swap roles** (near-black text on light bg vs. near-white text on dark bg) but the *same variable name* must carry both across the switch — never hardcode either color anywhere a theme switch is expected to reach.
- **Add an explicit `--on-accent` token per theme** — the text/icon color placed on top of an accent-colored surface (a filled button, a selection highlight). Don't assume one fixed dark-or-light text color works for every theme's accent: a deep, dark accent (e.g. forest green on a light register) needs light text on top; a bright accent (e.g. brass gold on a dark register) needs dark text on top. Pick or compute this per theme — never hardcode one value globally and reuse it everywhere.

---

## 3. Nothing may hardcode the "first" theme's colors

Anything written as a literal color that was only ever eyeballed against the theme you built first will break silently on the others:

- **Gradients/overlays meant to fade to the page background** (vignettes, image-caption scrims, nav blur-on-scroll) must reference `color-mix(in srgb, var(--bg) X%, transparent)` instead of a literal `rgba(r,g,b,X)` copied from the first theme's bg value.
- **Any Canvas/WebGL/Three.js engine that draws page-colored elements** (arc lines, node dots, particle motes, text labels) must read the *current* theme's colors from a live JS state object updated on every theme switch — never hardcode the RGB that happened to look right during development. Keep a parallel JS palette map (or re-derive via `getComputedStyle` on the CSS custom properties) so switching themes recolors the engine too, not just the DOM around it. Otherwise a canvas hero built dark-first goes fully illegible the moment the page flips to a light register (light-colored lines on a now-light background).
- **Borders declared as a literal `rgba(255,255,255,.07)`** assume a dark bg; derive from `--ink` (via `color-mix` or a precomputed rgba per theme) so hairlines stay visible-but-subtle in both registers instead of vanishing or over-darkening.

---

## 4. Verification

Before calling multi-theme "done," switch to **every** theme once and recheck:
- Text contrast (`preflight.md`'s WCAG AA gate applies **per theme**, not just the one you designed first).
- Whether any gradient/vignette/border now reads as a mismatched patch of the wrong color.
- Whether canvas/engine elements are still visible — not blended into a background that now matches them.

A theme switcher that was only ever tested in the default theme is unverified, not done.
