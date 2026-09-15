# Mobile Floor — the six ways a crafted page breaks on a phone

Every rule in this file is a **hard floor**, not a preference. A page that violates one of them is not "less good on mobile" — it is *visibly broken*, and the break is the kind a visitor reads as a bug rather than a style.

> **When to load:** any build that will be viewed on a phone (i.e. almost all of them). Load it at implementation time, alongside `page-crafting.md` — these are implementation rules, not decisions.

**Test widths: 320 · 375 · 414 · 768.** Not "narrow the window until it looks off" — those four, deliberately. 320 is the floor (iPhone SE, older Androids); 768 is where a two-column layout is still tempted to hold on and shouldn't.

Why this file exists separately from `preflight.md`: the pre-flight check asks *"does it horizontally scroll at 375px?"* — that's the **symptom**. This file is the **causes**. Knowing the symptom doesn't tell you what to write.

---

## M1 · Root-level `overflow-x: clip` — `clip`, never `hidden`

```css
html, body { overflow-x: clip; }
```

Both elements. Setting it on `body` alone leaves `html` free to scroll.

**Why `clip` and not `hidden`.** They look identical until you have a sticky nav. `overflow: hidden` makes the element a *scroll container*, and a scroll container severs `position: sticky` and `position: fixed` for its descendants — they stop sticking to the viewport and start sticking to the (now scrollable) ancestor. The page stops scrolling sideways and your sticky header dies with it. `clip` clips without creating a scroll container, so sticky descendants keep working.

This is the single most common "I fixed the horizontal scroll and now the nav doesn't stick" bug. Ship `clip`.

**But clipping is the backstop, not the fix.** If something is overflowing, find it (M2 and M4 are the usual culprits). `overflow-x: clip` on a page with a genuinely 900px-wide element just hides the right third of it.

---

## M2 · Image-bearing grid tracks use `minmax(0, 1fr)`

```css
/* wrong */ grid-template-columns: 1fr 1fr;
/* right */ grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
```

**Why.** A bare `1fr` resolves to `minmax(auto, 1fr)`. The `auto` minimum is the track's **max-content size** — for a track containing a 1600px-wide image, that's a 1600px minimum width the track will not go below, no matter how narrow the viewport gets. The grid blows past the viewport and the whole page scrolls sideways.

`minmax(0, 1fr)` sets the floor to zero and lets the track actually shrink. One character per track.

**Applies to:** any track containing `<img>`, `<picture>`, `<video>`, `<canvas>`, an SVG with an intrinsic width, or a nested grid that itself contains one. Also applies to `grid-template-rows` in the rare case of a fixed-height row band.

**Same failure, different shape — flex.** A flex item's default `min-width: auto` does the same thing. Any flex child that can contain an image or a long string needs `min-width: 0`.

---

## M3 · Clickable text never wraps to two lines — at *any* width

Buttons, primary nav links, footer links, tab labels, breadcrumbs, CTAs. A two-line button label doesn't read as a design choice; it reads as a styling error, and it shrinks the tap target's perceived edge.

> **Note this supersedes the old wording.** `preflight.md` §G said "button text fits one line **at desktop**" — which checks the width where the problem never happens. The floor is every width from 320 up.

Fix in priority order — the first is almost always the right one:

1. **Shorten the label.** "Get started for free" → "Start free". A CTA that needs eight words is a copy problem wearing a layout costume. This is the fix in ~80% of cases.
2. `white-space: nowrap` on the affordance, and let the parent reflow (wrap the row, stack the group).
3. Drop a non-essential nav item at narrow widths.
4. Collapse the nav into a sheet or menu.

Never solve it by shrinking the font below the body scale, and never by letting it wrap "just on 320".

---

## M4 · Display headings get `overflow-wrap: anywhere; min-width: 0`

```css
.hero__display, h1, h2 { overflow-wrap: anywhere; min-width: 0; }
```

**Why.** Long hyphenated compounds ("AI-generated", "server-side-rendered") and all-caps compound brand names have exactly one break opportunity — the hyphen. At display sizes on a 320px screen, one unbreakable word is wider than the viewport, and it overflows regardless of the container's width. `overflow-wrap: anywhere` lets the engine break inside the word as a last resort.

`min-width: 0` is the flex/grid half of the same fix — without it, the heading's parent track refuses to shrink below the word's intrinsic width (same mechanism as M2).

Use `anywhere` rather than `break-word`: `break-word` doesn't affect intrinsic size contributions, so it fixes the visual overflow but leaves the track still sized to the long word.

---

## M5 · Only one element sticks at `top: 0`

If the page has a sticky nav, **every other sticky element needs a vertical offset.** Two elements both pinned at `top: 0` occupy the same strip of viewport during scroll, and the one deeper in the DOM paints over the nav. It reads as a section header bleeding through the navigation bar.

```css
:root { --nav-h: 64px; --z-sticky: 200; --z-nav: 300; }

.nav          { position: sticky; top: 0;            z-index: var(--z-nav); }
.section__head{ position: sticky; top: var(--nav-h); z-index: var(--z-sticky); }
```

Two things, both required:

- **Offset** the secondary sticky by the nav's height so it docks *beneath* the nav.
- **Split the z-index token.** `--z-nav` above `--z-sticky`, so the nav always out-paints an in-page sticky when they momentarily overlap during scroll.

This fires on any page with sticky section heads, a sticky table-of-contents, a scroll-synced pinned pane (`page-crafting.md` §3), or a sticky filter bar. Pages with a single sticky nav pass trivially.

---

## M6 · All-caps display headings: `line-height` floor is `1.0`

**This is a conditional override of the substrate rule in SKILL §3 — read it carefully, the two rules are in tension and the tension is real.**

SKILL §3 and `preflight.md` §B call for display type at `line-height: .86–.95`. That is correct **for mixed case**: lowercase letters carry descenders (g, y, p, q), which occupy the space below the baseline and keep consecutive lines optically apart even at a tight leading.

**All-caps has no descenders.** Cap-tops sit at the very top of the line box and nothing occupies the space below the baseline. At `line-height: .86`, the cap-tops of line 2 collide with the baseline — and with any comma or period — of line 1. The two lines fuse into a single band of ink.

On a wide viewport a short all-caps headline sits on one line and the bug never appears. **On a phone it wraps, and the bug is guaranteed.** This matters specifically because several souls in `style-personas.md` lead with all-caps display faces — the brutal-typographic lane (Anton, Bebas Neue) is exactly the case that breaks.

**The rule:**

| Heading | `line-height` |
|---|---|
| Mixed-case display | `.86–.95` — unchanged, this is the substrate rule |
| `text-transform: uppercase` display | **`1.0` floor · `1.02–1.08` recommended** |

Two ways out, pick one:

- Raise the leading on the uppercase heading to `1.02–1.08`.
- Drop `text-transform: uppercase` and keep the tight leading.

Do not split the difference. `line-height: .98` on all-caps still collides; it just collides less often.

**Condensed faces make it worse.** Anton, Bebas Neue, and Inter Tight at weight 900 have tall caps relative to their em box — they collide before a normal-width face would. On those, use the top of the recommended range.

---

## The check

Run at 320 · 375 · 414 · 768 before shipping:

- [ ] **M1** — `overflow-x: clip` on both `html` and `body`; not `hidden`. Sticky nav still sticks.
- [ ] **M2** — every grid track that can hold an image is `minmax(0, 1fr)`; flex children that can hold one have `min-width: 0`.
- [ ] **M3** — no button, nav link, footer link, tab, breadcrumb, or CTA wraps to two lines at any width.
- [ ] **M4** — display headings carry `overflow-wrap: anywhere; min-width: 0`.
- [ ] **M5** — exactly one sticky element at `top: 0`; all others offset by `--nav-h`; `--z-nav` > `--z-sticky`.
- [ ] **M6** — no element has both `text-transform: uppercase` and `line-height < 1.0`.
- [ ] Touch targets ≥ 44px. `min-h-dvh` over `100vh`. Multi-column sections declare their collapse.

`scripts/detect.mjs` mechanically catches M1, M2, M5, and M6. It **cannot** catch M3 or M4 — those need a rendered page at 320px. Run the detector, then look at the page.

> A page that has only been checked by narrowing a desktop browser window has not been checked. Open it at 320 and read it.
