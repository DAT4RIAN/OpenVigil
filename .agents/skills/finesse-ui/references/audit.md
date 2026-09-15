# Audit — Read-Only Diagnostic

`audit` reports what's wrong with a page. **It never edits code.** Output a findings list the user can act on (or hand to `redesign` / `bolder` / `quieter` / `soul`).

> If the user wants the fixes applied, that's `redesign` (or a specific refine command), not `audit`. Keep this one read-only — that boundary is the whole point.

---

## Flow

1. **Identify the target & register.** Which file(s)/URL? Is it brand or product (§0.A)? The register decides which checks are load-bearing (a dashboard isn't failing for low SPECTACLE).
2. **Run the three scans below**, in order. Note failures — do not fix.
3. **Score & prioritize.** Group findings P0 (ships broken) → P1 (clearly cheap) → P2 (polish). Lead with the single highest-leverage fix.
4. **Report.** One-line verdict, then the prioritized list. Each finding carries **four** things: what it is *in plain sight*, where (`file:line` when possible), **what it costs the visitor**, and which command fixes it.

> **The consequence line is what makes an audit actionable.** `gradient text — #1 AI tell` states a professional judgment; the user cannot rank it, so he either fixes everything or nothing. `标题的颜色从紫渐变到蓝 → 访客第一眼会觉得是模板做的` gives him the two things he needs to triage: what to look for on screen, and what happens if he leaves it. Every finding gets both. Terms he may not know get a one-clause gloss the first time — `references/plain-words.md`.

---

## Scan 1 — Cheapness Blacklist (`anti-cheap.md`)

**First run the detector** (no network, pure local file scan) to get machine-verifiable hits, then add your own eye:

```bash
# Resolve the detector — it ships with the skill, NOT with the user's project.
# Under Codex it's in ~/.codex/skills/; under Claude Code ~/.claude/skills/ or the
# plugin dir. A hard-coded `skills/finesse-ui/…` only works on a vendored copy.
for p in skills/finesse-ui .claude/skills/finesse-ui \
         "$HOME/.claude/skills/finesse-ui" "$HOME/.codex/skills/finesse-ui"; do
  [ -f "$p/scripts/detect.mjs" ] && DETECT="$p/scripts/detect.mjs" && break
done
node "$DETECT" --json <target ...>
```

It reports findings grouped P0/P1/P2 with `file:line` and the fixing command in `files[]`, a `p0` count, and a `notCovered[]` list of the tells the regex layer **cannot** see. It **always exits 0** — findings are data in the JSON, not a tool failure; read `p0` to know the count (a non-zero exit is reserved for the `--strict` CI/git-hook mode). If the script can't be found (the skill was dropped into a project without it), don't treat that as a blocker — scan by hand against `anti-cheap.md` below. **A clean run means "no regex-detectable slop", not "this page is good"** — the `notCovered[]` items are exactly why Scan 1 always continues into the by-eye pass. Fold its hits into your report, then load `references/anti-cheap.md` and check the offenders the regex can't see (taste-level: default-category aesthetic, fake screenshots, generic card grids):

Each row is `technical name` — *what it looks like on screen* — **what it costs the visitor**. Report the second and third; the first is for your grep.

- [ ] **em-dashes** — *long dashes used for dramatic pauses in the copy* — reads as machine-written; the single most-recognized AI tell
- [ ] **gradient text** (`background-clip:text` + gradient) — *headline letters fading from one color to another* — the fastest way a visitor concludes "template"
- [ ] **default glassmorphism** — *frosted translucent cards showing the background through* — decorative-by-default; dates the page to one AI era
- [ ] **side-stripe card borders** (`border-left/right` > 1px) — *a colored bar down one edge of each card* — a stand-in for hierarchy the layout never earned
- [ ] **eyebrow spam** (count > ceil(sections/3)) — *a small all-caps line above every headline* — present in 55–95% of AI output; the most quantifiable tell
- [ ] **`01 · 02 · 03` scaffolding** — *numbers labeling sections that aren't a sequence* — implies an order the content doesn't have
- [ ] **identical card grids** — *6 cards, each icon + title + paragraph, same size* — nothing on screen says which one matters
- [ ] **div-based fake screenshots** — *a "product preview" drawn out of rectangles instead of a real screenshot* — visitors recognize the fake and stop trusting the claims around it
- [ ] **fake-precise numbers** (`92%`, `4.1×`) — *exact-looking stats with no source* — one unverifiable number discredits the real ones next to it
- [ ] **default-category palette** — *the color scheme anyone could guess from the industry alone* (beige+brass for craft, purple glow for AI/SaaS) — the brand becomes indistinguishable from its competitors
- [ ] **reflex fonts** — *`Inter` / `Fraunces` / `Instrument Serif` picked with no stated reason* — good fonts, so over-used they now read as "no typeface decision was made"
- [ ] **pure `#fff` / `#000`, hard `#333` borders** — *pure white/black areas and hard grey lines* — the flat "unfinished" look; real pages tint their neutrals
- [ ] **missing grain** — *large flat color areas with no texture at all* — reads plastic on a surface meant to feel expensive
- [ ] **accent drift** (color-lock broken) — *a different highlight color appears partway down the page* — reads as unfinished rather than varied
- [ ] **zero imagery on an image-implied brief** (food / hotel / fashion / travel) — *a page selling a physical experience with no photographs* — this is a bug, not minimalism

## Scan 2 — Spectacle Shown (§1.B, finesse-specific)

The check impeccable doesn't have. **This is finesse's signature audit.**

- [ ] What SPECTACLE does the page claim (stated, or inferred from the soul/brief)?
- [ ] If SPECTACLE ≥ 7: does the markup actually contain a working engine? Search for `three`, `canvas`, `gsap` / `ScrollTrigger`, `webgl`, `requestAnimationFrame`. **If claimed ≥7 but none present → P0 "spectacle claimed, not shown" — the page is broken, not just plain.**
- [ ] Does the engine degrade gracefully (readable with it removed)?
- [ ] `prefers-reduced-motion`: is there a still-frame / static fallback? Missing → P0.
- [ ] Motion motivated? Every ScrollTrigger / marquee / pin needs a one-sentence reason. > 1 marquee → flag.

> When the browser-verification step (P2-B, `preflight.md`) is available, don't just grep — open the page and confirm the engine renders real pixels (not white / not flat background). A page that greps clean but ships a white hero still fails this scan.

## Scan 3 — Pre-Flight Gates (`preflight.md`)

Load `references/preflight.md` and run the hard gates: substrate present, a11y (contrast ≥4.5:1 body, visible focus, 44px touch targets), responsive (no headline overflow at any breakpoint, `min-h-dvh`), performance (transform/opacity only, lazy-loaded engines). Any hard-rule failure is P0.

---

## Output shape

Three lines per finding: **what to look for**, **what it costs**, **the command**. Priority labels are spelled out, not left as codes.

```
Audit: {target} · verdict={1 line, plain}

P0 — ships broken
  • {finding name} ({file:line})
    On screen: {what the user would see if he looked}
    Cost: {what it does to a visitor / why it blocks shipping}
    → /finesse {command} {target}

P1 — clearly reads as AI-generated
  • …

P2 — polish
  • …

Fix this one first: /finesse {command} {target} — {one-line reason}
```

Worked example:

```
Audit: index.html · verdict=solid structure, but three details give away that it's AI-generated

P0 — ships broken
  • Button text unreadable on the hero photo (index.html:112)
    On screen: the white "Book a table" label sits on a bright part of the photo behind it.
    Cost: on a phone in daylight it disappears — the main action becomes invisible.
    → /finesse redesign index.html

P1 — clearly reads as AI-generated
  • Gradient headline (index.html:47)
    On screen: the main headline fades from purple to blue instead of one solid color.
    Cost: the single most-recognized AI-page signature; visitors assume a template.
    → /finesse quieter index.html

Fix this one first: /finesse redesign index.html — the invisible button costs you bookings today.
```

Keep it scannable. No fixes, no rewritten code — point at the command that does the fix.

**Two failure modes to avoid.** Writing `Cost:` as a restatement of the finding ("gradient text is an AI tell") teaches the user nothing — it must name what happens to a *visitor*, or to the launch. And a wall of P2s buries the P0: if the list runs past ~8 items, report the P0s and P1s in full and collapse the rest to a count ("plus 6 polish items — say `show polish` for the list").
