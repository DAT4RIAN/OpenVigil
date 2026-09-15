# Component Scope — when the brief is one element, not a page

Most day-to-day requests are component-shaped, not page-shaped. "Make me a button." "This input looks cheap." "Build a toast." Running the full page flow on those is wrong in both directions: it spends a Brand Read, a skeleton pick, and an engine decision on something that has no hero and no sections — **and** it never checks the one thing that actually determines whether a component is well-made, which is whether every state was shipped.

This file is the alternate route.

> **When to load:** at §0, *before* the Brand Read, when the scope signals below fire. It replaces §2/§4/§5 for this build; it does not replace the craft floor.

---

## 0. Scope detection — route on two signals

Run this before §0.A. If **two or more** fire, take the component route:

- The brief names a **single UI element**: button · input · textarea · select · checkbox · radio · switch · slider · card · modal · drawer · dropdown · menu · tooltip · popover · tab strip · chip · badge · tag · avatar · breadcrumb · pagination · toast · snackbar · banner · accordion row · date picker · file upload.
- The brief is **short (≤ 30 words) and refers to one thing**.
- The **target is a single component file** — `Button.tsx`, `components/input.css`, `Card.vue`, `ui/toast.svelte`.
- The user says **"just the X" / "only the Y" / "this one element" / "单独一个" / "就这个组件"**.

**Counter-signals — stay on the page flow** even if one of the above fires: the brief names multiple sections, asks for a layout, says "page"/"landing"/"dashboard"/"页面", or names a whole surface ("the settings screen").

**Ambiguous?** Ask exactly one question, then commit:

> *"One pricing card, or the whole pricing page?"*

**Default to component when the user doesn't engage.** A single artifact is far cheaper to redirect than a full page.

---

## 1. What the component route keeps

Not much is skipped from the *floor* — a component in a premium product still has to look premium.

- **§0.A register** — a component inherits the register of the surface it lives in. A button in a dashboard is product-register; a button on a launch page is brand-register. If there's no surrounding code to read, ask or default to product.
- **The universal craft floor** (`design-dna.md` §1) — tinted neutrals, no pure `#fff`/`#000`, translucent/hairline borders, hue-tinted shadows, contrast floors. Non-negotiable at any scope.
- **Existing tokens win.** Read the project first. If a `design-model.yaml`, a `PRODUCT.md`, a `tokens.css`, or a `:root` block exists, the component **consumes those tokens by name** and invents nothing. A button that ships its own `#4F46E5` into a project with a locked accent is a defect, not a design.
- **`product-palettes.md`** — only when there is no existing palette to inherit.
- **The cheapness blacklist** (`anti-cheap.md`) — the universal items: no gradient text, no side-stripe borders, no glassmorphism-as-decoration, no untinted neutrals, no contrast failures, no mixed radius scales.
- **`mobile-floor.md` M3** — a button label that wraps to two lines is the single most common component-level break.
- **`prefers-reduced-motion`** — if the component animates at all.

---

## 2. What the component route skips — say so out loud

State this in one line so the user knows why the usual apparatus didn't appear:

> *"Component scope — skipping the skeleton, hero engine, and divergence rotation."*

- **§5 page skeletons** — a component has no section sequence.
- **§4 hero engine** — a button has no hero. SPECTACLE is not a meaningful dial here.
- **Divergence rotation and the used-list** (`divergence.md` §3/§4) — components do **not** rotate and do **not** get an entry in `.finesse/log.json`. Variety across components within one product is a *defect*: a project's buttons should all look like siblings. Divergence is a page-level goal.
- **The `/* finesse · ... */` five-axis stamp** — page-level. Components use the component stamp in §5 below.
- **`examples/`** — the corpus is pages. Opening one to build a button invites lifting a whole shell.

---

## 3. The eight states — the one hard gate

**Every interactive component ships code for all eight.** This is the component route's only mandatory checklist, and it is not advisory.

| State | Requirement |
|---|---|
| **default** | The resting state. |
| **hover** | Pointer feedback. Gate behind `@media (hover: hover)` so it never sticks on touch. |
| **focus-visible** | A visible ring at **≥3:1 against the adjacent surface**. **Never animate its appearance** — keyboard users need it the instant focus lands. Use `outline` + `outline-offset`, not `border` (see below). |
| **active** | The pressed state. A 1px translate or a fill-darken. Most commonly the missing one. |
| **disabled** | Three channels, not one: `opacity: .5` **and** `cursor: not-allowed` **and** the native `disabled` attribute (or `aria-disabled="true"`). Opacity alone is not a disabled state — it's a faded enabled one. |
| **loading** | Reserve the final width so the label swap doesn't reflow the layout. Feedback past ~300ms. |
| **error** | States cause *and* fix ("Password needs 8+ characters"), never "Invalid". |
| **success** | Silent success is usually right — if the effect is already visible on screen, don't celebrate it. A toast for something the user can see is noise. |

**How this relates to the rules already in the skill.** These eight are not a new system — they are the existing requirements collected at component granularity and made complete:

- `product-ui.md` §4 already requires six **input** states (default/hover/focus/disabled/error/success) — this adds `active` and sharpens `focus` to `:focus-visible`.
- `product-ui.md` §5 already requires five **view** states (loading/empty/error/success/disabled) — `empty` is a view-level state and does not apply to a single control, which is why it isn't here.

**Geometry rules that break layouts if you get them wrong:**

- **Never change `border-width` between states.** Default / hover / focus / error all keep the same border width. State goes to `background-color`, `border-color`, `outline`, or `box-shadow` — changing width shifts every neighbour by a pixel.
- **Build the focus ring from `outline`, not `border`.** Reserve `outline: 2px solid transparent` at rest so activating focus causes no geometry shift.
- **One base height across a form row.** A 38px input beside a 44px button is the most common tuning tell. Pick one height (44px floor for touch) and share it.
- **Reserve the helper/error slot.** `min-height: 1lh` even when empty, so an appearing error doesn't push the page down.

---

## 4. Ship two files

**1 · The component**, matching the project's existing conventions — `Button.tsx` / `Button.vue` / `Button.svelte` / `button.css` + markup. It consumes tokens by name (`var(--accent)`), never inlines a literal color.

**2 · `<Name>.preview.html`** — a standalone page rendering all eight states stacked and labelled. The user opens it once, confirms the component works, and deletes it. It is not production code; say so when you hand it over.

```
Button — 8 states
─────────────────────────────────────
default    [ Save changes        ]
hover      [ Save changes        ]   ← .is-hover
focus      [ Save changes        ]   ← .is-focus
active     [ Save changes        ]   ← .is-active
disabled   [ Save changes        ]   ← disabled attr
loading    [ Saving…             ]   ← data-state="loading"
error      [ Try again           ]   ← data-state="error"
success    [ Saved               ]   ← data-state="success"
```

The trick that makes all eight render at once: each state's CSS targets **both** the real pseudo-class and a forcing class, so the preview can pin a state that would otherwise need a live pointer.

```css
.btn:hover,         .btn.is-hover  { background: var(--surface-2); }
.btn:focus-visible, .btn.is-focus  { outline: 2px solid var(--focus); outline-offset: 2px; }
.btn:active,        .btn.is-active { transform: translateY(1px); }
```

Cost: one extra selector per state. Benefit: the eight-state requirement becomes *visible* instead of *claimed*, which is the only reason it holds.

---

## 5. Stamp format

Components stamp differently from pages — no five-axis coordinate, because components don't rotate:

```css
/* finesse · component: button · register=product
 * states: default · hover · focus-visible · active · disabled · loading · error · success
 * tokens: inherited (design-model.yaml) */
```

The `component:` prefix tells a later finesse run that this artifact is component-scoped, so it is **not** counted as a page for divergence purposes and must not be rotated against. The `states:` line is a checklist, not a caption — every state named there must have actual styling in the file.

---

## 6. Before handing back

- [ ] All eight states have real styling — verified by opening the preview, not by claiming it.
- [ ] Focus ring ≥3:1 against the adjacent surface, and does **not** fade in.
- [ ] `border-width` is constant across every state.
- [ ] Disabled uses all three channels (opacity + cursor + attribute).
- [ ] Every color and font references a named token; no literals in the component file.
- [ ] Label doesn't wrap at 320px (`mobile-floor.md` M3); touch target ≥44px.
- [ ] Hover is gated behind `@media (hover: hover)`.
- [ ] Motion, if any, has a `prefers-reduced-motion` terminal state.
- [ ] No `.finesse/log.json` entry was written, and no five-axis page stamp was emitted.
