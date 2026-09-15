# Divergence — Why Every Page Comes Out the Same, and the Machine That Fixes It

The most common complaint about AI-built interfaces is not that they're ugly. It's that they're **all the same page**. Same hero, same three-column card grid, same eyebrow above every headline, same accent. finesse has an anti-cheap blacklist that raises the *floor* — but a floor does not create *variety*. Negative constraints stop bad pages; they do not produce different ones.

This file is the positive half: a **divergence machine** that makes two briefs produce two visually unrelated pages, by construction rather than by hope.

> **When to load:** at §0 Brand Read, *before* the Design Read line — i.e. before you have committed to anything. Also load it whenever the user says "feels generic", "looks like every other AI site", "I've seen this before", or when they've run finesse several times and the outputs are converging.

---

## 0. Register Boundary — READ THIS FIRST, or you will break a dashboard

**Divergence is not a universal good. It is a goal for `brand`, and a bounded tactic for `product`.**

A landing page fails by being **forgettable** — so on brand, novelty is the objective, and the more unlike other pages it is, the better it works.

A dashboard fails by being **unusable** — and usability is *built on convention*. The sidebar is on the left, nav items carry icons **and** labels, KPIs sit above the fold, a table sorts when you click its header. Those aren't defaults you should be proud of beating; they are the user's existing mental model, and every one you "innovate" on is a tax the user pays every day. **A dashboard with a surprising navigation paradigm is a worse dashboard.**

So the axes split by register:

| | `brand` | `product` (dashboard · console · admin) | `h5` (phone-only) |
|---|---|---|---|
| **Diverge freely on** | all five axes (§3) — palette, type, layout family, engine, material | **palette** (`product-palettes.md` — the real fix for "every dashboard is blue"), **shell morphology** (`product-ui.md` §1 — sidebar / floating panel / bento / triptych), **density**, surface treatment, chart style | **palette**, **type**, **material/metaphor**, **morphology** (`h5-mobile.md` §4 — app shell / deck / snap narrative / commerce stack / longform / ambient), chart language, transition character |
| **Never diverge on** | — | **navigation conventions** (position, icon+label, depth ≤3), **interaction affordances** (what's clickable, sort, filter, selection), **table & form behavior**, **status color semantics** (red = bad, green = good), the §7 a11y floor | **the frame** (`h5-mobile.md` §1 — viewport contract, locked `body`, the 560px phone frame), **safe-area math** (§2), **the native furniture** (§5 — where the back button is, which edge the TabBar sits on, that a sheet rises from the bottom with a grab handle), **touch affordances** (§3 — 44px, `:active`, no tap flash) |
| **The failure this prevents** | a forgettable page | an unusable one | a page that feels *wrong* in the hand |

Concretely: two dashboards for two different clients **should** look unrelated — different neutral ramp, different accent, different shell, different chart language. They should **not** navigate differently. Product-register sameness is fixed by `product-palettes.md` and shell selection, **not** by reinventing the shell.

**The h5 column is the same carve-out, one step stricter.** OS furniture is a convention users navigate by muscle memory, and muscle memory is exactly the thing originality destroys. A TabBar that sits on the left, a sheet that slides in from the side, a back button top-right — each of these is "distinctive" and each makes the page feel broken rather than fresh. Diverge on the palette, the type, the metaphor, the transitions. **Never on where things are.** Note also that h5 is a *container* register: when it wraps `product`, that column's bans apply too.

Everything below §1 is written for **brand**. Apply it to product and h5 only through the columns above.

---

## 1. The Five Reasons Output Converges

Diagnose honestly before fixing. Every one of these is a real mechanism, not a vibe:

1. **The "don't repeat" rule is unenforceable.** `style-personas.md` says *"Rotate; never ship the same lane twice in a row."* **You have no memory of the last run.** Across sessions, "twice in a row" is a rule that can never fire. It reads like discipline and does nothing. → fixed by §4 (`.finesse/log.json` + the CSS stamp — a written record with a defined read step and a defined write step).
2. **Personas are a closed list.** Ten rows in a table, six of them quoted in SKILL §2. A model choosing from ten options, weighted by training-data familiarity, will land on the same two or three most of the time. → fixed by §3 (compose, don't select).
3. **`examples/` teaches structure, not just craft.** The instruction is *"lift patterns, not whole files."* That is a soft constraint against a strong pull: a model with an open example file will mirror its section order, its card counts, its shell. This is why every dashboard converges on the sidebar+topbar+KPI-row. **The examples that raise your quality floor are the same examples flattening your variety.** → fixed by §5 (read examples as coordinates, not templates).
4. **The dial presets are a lookup table.** `"landing page" → SOUL 7 · SPECTACLE 6 · DENSITY 4`. Same words in, same numbers out, same page out. The preset is a *starting* point that is almost never moved off. → fixed by §3's forced perturbation.
5. **The training-data attractor.** Absent a strong constraint, every model falls toward the same aesthetic basin: Inter, a purple-to-blue gradient, glassmorphism cards, an eyebrow, three feature columns. `anti-cheap.md` bans the symptoms one by one — but banning the *known* tells just relocates the attractor, it doesn't remove it. → fixed by §2 (name and reject before generating).

---

## 2. Anti-Default: Name It, Then Beat It

Before any generation, write **one sentence** naming the lazy default for this brief, and **one** naming what you're doing instead. This is SKILL §0.D, and it is mandatory — but do it at **two altitudes**, because the second-order default is the one that catches you:

> **First-order:** "Coffee brand → the default is warm beige + brass serif + kraft texture. Rejected."
> **Second-order:** "The *obvious* rejection of that is editorial-typographic-on-cream. That's also a default. Rejected. Going: cold graphite + a single acid green, mono-forward, industrial roastery-as-laboratory."

The second-order move matters because "reject the cliché" is itself a cliché with its own attractor. Every AI that has been told to avoid beige-and-brass reaches for editorial serif on cream. Name it and step off it too.

---

## 3. Compose the Soul, Don't Select It

**A closed list of 10 personas yields 10 outputs. Five orthogonal axes yield thousands.** Instead of picking a row from `style-personas.md`, draw one value per axis and let the *combination* be the soul. The persona table becomes a set of **known-good example combinations**, not the menu.

| Axis | Options (not exhaustive — extend freely) |
|---|---|
| **A · Palette structure** | mono + one acid pop · dual-hue conflict (warm object, cool ground) · full monochrome by opacity ladder only · earth + one saturated · near-black + dual metal · light substrate + ink + one signal |
| **B · Type relationship** | display and body from the *same* superfamily · extreme weight contrast (900 vs 300) · serif italic used *inside* a sans headline as the only human note · mono-forward with sans as support · one variable font doing all roles via axes · display so large it becomes the layout |
| **C · Dominant layout family** | hover-expand accordion / filmstrip · horizontal pinned track · generative (algorithmically split) grid · table/list rows instead of cards · geometric collage · asymmetric weighted grid (`1.4fr 1fr`) · exploded-view diagram · full-bleed photographic stack · pinned panel stepper |
| **D · Engine** | Three.js structure · Canvas 2D field · WebGL FBO (fluid / reaction-diffusion / raymarch) · GSAP scrub-choreography · CSS-only geometry · variable-font morph · **no engine, typography carries it** |
| **E · Material / metaphor** | film & contact sheet · paper & press · machined metal · water & fluid · signal & phosphor · laboratory & specimen · textile & thread · concrete & light · circuitry & grid |

**Procedure:**

1. Draw a value on each axis that the **brief motivates** — not the one you like. The material axis (E) is the highest-leverage: it's where the page's *reason* lives, and it constrains the other four honestly.
2. **Check the combination against the used-list (§4).** If A+C+E collides with a recent build, redraw the colliding axis.
3. **Perturb one dial off its preset** (§1.4) and say why in one line. If the preset for "landing page" is SPECTACLE 6, a brief about a silent product may want 3 — and that decision is the page's personality.
4. If the resulting combination is incoherent (machined metal + botanical particles + Cormorant italic), *don't force it* — but interrogate it once before discarding. The corpus's strongest page pairs a monochrome graphite chassis with a four-neon canvas, on the argument *"the machine is grey, the sound is not."* **A defensible collision beats a safe match.** If you can write that one-sentence argument, keep it.

The 10 personas in `style-personas.md` are simply the 10 combinations already validated. Use them as calibration, not as the ballot.

---

## 4. Make "Don't Repeat" Actually Executable

`PRODUCT.md` locks **intra-project consistency** (one accent, one theme, one type system — so page 7 matches page 1). That is the *opposite* goal from divergence, and until now it was the only memory finesse had. Nothing tracked what you'd already built **across** pages, so §1.1's rotation rule could never fire.

**The two jobs are opposites and must not share a file.** `PRODUCT.md` answers *"what must stay the same?"*. The build log answers *"what must change?"*. Putting the second inside the first is why the earlier version of this rule stayed a suggestion — there was no path, no schema, and no step in the main flow that read it.

### 4.1 The build log — `.finesse/log.json`

At the **project root**. A JSON array, **newest entry first**, trimmed to the last **20** entries.

```json
[
  {
    "date": "2026-07-21",
    "page": "acme-launch",
    "register": "brand",
    "axes": {
      "palette":  "mono + acid lime",
      "type":     "900/300 contrast",
      "layout":   "pinned h-track",
      "engine":   "GSAP scrub",
      "material": "machined metal"
    },
    "dials": { "soul": 8, "spectacle": 7, "density": 4 },
    "brief": "industrial keyboard launch"
  }
]
```

Create `.finesse/` and the file if absent.

**Gitignore it.** `.finesse/log.json` is local build history, not a project asset — every build rewrites it, so committing it buys nothing but noise in the diff and a merge conflict every time two people build in parallel. Add `.finesse/` to the project's `.gitignore` on first write.

That decision is only affordable **because the stamp is committed.** The two halves split the job: the log is fast local memory for consecutive runs on one machine; the stamp travels with the code, so a fresh clone — or a collaborator who has never run finesse here — can still read what the last build chose and rotate off it. Ignore the log, keep the stamp. Losing both is how a project silently goes back to having no memory at all.

### 4.2 The stamp — the fallback when there is no log

The first non-empty line of the page's CSS (or the top of the inline `<style>`) carries the same coordinates:

```css
/* finesse · register=brand · A=mono+acid-lime · B=900/300 · C=pinned-h-track
 * D=GSAP-scrub · E=machined-metal · SOUL=8 SPECTACLE=7 DENSITY=4 */
```

The log is the primary memory; the stamp is the **backstop**. It survives the cases the log doesn't: the user copied one HTML file out of the project, `.finesse/` is gitignored, the page came from somewhere else. If there is no `log.json`, **grep the target for `/* finesse ·` and infer one entry from the stamp.**

Component-scope builds stamp differently and are **not** logged — see `component-scope.md` §5.

**Short form for back-filled builds.** When stamping a page that already existed (its dials were never recorded), emit the axes and omit `SOUL/SPECTACLE/DENSITY` rather than inventing values — a fabricated dial is worse than an absent one, because the next run will rotate against it as if it were real. The 17 pages in `examples/` carry exactly this short form. Product-register pages record `shell=…` in place of the five axes, per the register boundary in §0.

### 4.3 Wiring — where it reads and where it writes

A memory nothing reads is not a memory. Both ends are mandatory:

| When | Do |
|---|---|
| **§0, before the Design Read** | Read `.finesse/log.json`. If absent, grep the codebase for a `/* finesse ·` stamp and infer one entry. If neither exists, this is the first run — no constraint. |
| **§0.B, with the Design Read** | **Say the rotation out loud — as a plain sentence, not axis letters** (§4.4). Pick on the page, not in your head. |
| **§8, after Pre-Flight passes** | Prepend one entry to the array, trim to 20. Write the stamp into the CSS. |

### 4.4 The threshold, and saying it out loud

**The new page must differ from the most recent entry on ≥3 of the 5 axes.** A collision on one axis is fine; a collision on three is a repeat — redraw the colliding axis.

State it before drawing, next to the Design Read. **Two audiences, two forms — and they are not interchangeable.**

**To yourself (recorded, never shown):** the five-axis coordinates, written to `.finesse/log.json` at §8 and stamped into the CSS.

```
Recent (3): machined-metal / paper-press / signal-phosphor
This build: water & fluid · differs on E + C + A (3/5 ✓)
```

**To the user (in the §0.B Design Read):** one plain sentence naming the directions avoided and the one chosen.

```
Rotation: deliberately steering clear of the last three builds (machined metal / paper press /
          phosphor terminal) — this one is water and drift.
```

Without a written record the rotation is unfalsifiable: afterwards, neither you nor anyone else can tell whether it happened or was merely narrated. That argument justifies **writing it down** — it does not justify printing axis letters at a person. `differs on E + C + A (3/5 ✓)` is unfalsifiable *to the user* in the way that matters: he cannot decode E, so he cannot object that machined metal was actually what he wanted. The plain sentence keeps the veto available; the log and the stamp keep the audit trail. Ship both, in their own channels — and never emit the coordinate form in conversation (`plain-words.md`, "terms to never say to a user").

**Two things it is not:**

- **Not a rule for components.** Components don't rotate; a project's buttons should look like siblings. `component-scope.md` skips this entirely.
- **Not a rule that outranks the user.** If they want the same soul — a sister page, a sub-brand, a second surface of one product — that's a `design-model.yaml` consistency job. The log is advisory; an explicit request always wins. Note the override in the entry's `brief` field so the *next* run doesn't read it as drift.

Two lines of upkeep per build buys the only real memory in the system.

---

## 5. Read `examples/` as Coordinates, Not as Templates

The corpus exists to show *craft applied*, and it will quietly teach you *structure copied* if you let it. Defend against it:

- **Open the closest example for the thing you're building** (this is `product-ui.md` §0's rule and it stands — it's how the quality floor holds).
- **Then locate it on the §3 axes and deliberately move.** If the example is `mono + acid` / `pinned track` / `metal`, and your brief lands on the same three, you are about to rebuild it. Change at least one axis on purpose.
- **Lift the craft primitives** (the scrim stack, the DPR math, the motion gate, the coordinate normalization) — those *should* be identical across every page; they're the floor.
- **Never lift the section sequence, the card count, or the shell.** Those are the page's identity.

`EXAMPLES.md` annotates each example with its axis coordinates precisely so you can see what to move off of.

---

## 6. Breaking the Argmax — you cannot decide your way out of a determinism problem

Everything above is a *reasoning* fix, and reasoning fixes have a ceiling. The deepest cause of convergence is mechanical: **given the same brief, a model maximizes the same objective and lands on the same answer.** "Try to be more varied" is an instruction to sample differently from a distribution whose mode hasn't moved. It will drift back.

So inject a source of variance the model doesn't control.

**The cheap version — a die roll, zero dependencies.** Draw an integer and let it pick the starting point on the highest-leverage axis (E · material, or C · layout family):

```bash
date +%S    # → 0-59; take (n % 9) + 1 to index the Material axis, or (n % 9) + 1 for Layout
```

Then **honor the draw** — you may reject it, but you must reject it *in writing*, with a reason ("the draw gave *textile & thread* for a security product; nothing in the brief supports it — redrawing"). Silent redraws are just the argmax with extra steps.

**The stronger version — draw a seed, not a palette.** A frozen 4-color palette drifts back to safe defaults regardless of brief. A *single seed color* plus a required composition step does not: the same seed becomes a dark-mode jazz club or a light hospitality brand depending on what the brief demands of it. If you keep a seed library, weight the draw by **inverse frequency** across hue buckets, so the library's own bias (everyone collects reds) doesn't become your bias.

**What the die roll does not do:** it does not exempt you from `anti-cheap.md`. Random entry + reflex-reject lists are two halves of one mechanism — the draw moves you off the mode, the ban list stops you sliding back to it. A draw that lands you on beige+brass is still beige+brass.

> **The one exception that outranks everything here:** an **observed** brand fact always beats a ban list and a die roll. If the client's actual brand color is beige and their actual typeface is Playfair, that is data, not a default. The bans and the dice exist to stop **you** defaulting — never to overrule a real brand.

---

## 7. The Direction Proposal — assert, don't poll

The old §0.B Design Read emits **one** direction, and the user rubber-stamps it. The obvious fix — "offer three options and let the user choose" — is **wrong, and it has been tested to failure.**

> **Text menus don't work.** A user staring at three paragraphs of adjectives has no basis to choose. "Cinematic + reverent" versus "restrained editorial" is not a decision anyone can make from words. They will pick the first one, or the one with the nicest name, and you have learned nothing while charging them a round-trip.

There are exactly two honest modes. Pick by whether the brief actually forks.

### Mode 1 · Assert-then-confirm (the default — use it most of the time)

When the brief plus `PRODUCT.md` make one direction clearly right, **name it and ask for a veto, not a vote.** One line, in the §0.B Design Read format, plus the rejected default:

```
Lazy default (rejected): dark page, violet glow, floating 3D render, three feature cards.
Design Read: high-end mechanical keyboard · machined + instrumental · register=brand ·
             SPECTACLE=5 · layout=exploded-view scrub · material=machined metal
Going with this unless you'd rather push it toward {one named alternative}.
```

A three-option menu when the answer is already obvious is theater — it *looks* like consultation and costs a round-trip. Assert. Let them override.

### Mode 2 · Three real visuals — two triggers

**Trigger A — the brief genuinely forks.** It legitimately supports very different readings: a "premium" brand that could be austere-Nordic *or* maximal-baroque; a personal site that could be a portfolio *or* a manifesto.

**Trigger B — the user cannot evaluate an assertion.** Mode 1 assumes a veto is available. It isn't when the brief carried no directional information at all — only undirected praise-words ("好看", "高级", "有质感", "premium", "clean", "modern"), or an explicit "I can't really say what I want." Such a user will approve *any* well-written `You'll see:` line, because he has nothing to compare it against. A rubber-stamp is not consent, and you will find out it wasn't at delivery.

Trigger B is the more common one and the easier one to miss: nothing about the brief *looks* ambiguous — "落地页，要高级一点" reads like a clear instruction, and the category default supplies a confident direction. The ambiguity is on the user's side, not the brief's. **Test:** could this person tell your direction apart from two plausible alternatives, in words? If not, showing him one is theater no matter how plainly it's phrased.

In either case, **do not describe the options. Build them.**

- Produce **three actual pages** — low-fidelity is fine, but they must render and be screenshot-able. The user chooses by *looking*, which is the only way anyone has ever chosen a design.
- **Each variant moves on a different axis** (§3). Three variants of "the same page in three accent colors" is not a choice.
- Build them **independently** — separate agents, or serially with the prior variants explicitly out of context. Variants that can see each other converge. If you're running them serially in one context, physically isolate them: fix a different anchor for each (a different material, a different layout family) and don't re-read the previous one.

### The squint test (mandatory before showing any trio)

Label each variant with **one concrete noun** of your own choosing — *exhibition · cockpit · storefront · playbill · field-manual · specimen-drawer · pressroom*.

- **If two variants could take the same label, they are the same page. Rework.**
- **If the labels only differ by adjective** ("dark cockpit" / "light cockpit"), that is not divergence.
- **Two dark variants plus one dark variant is not a trio.** When the moving axis is color or theme, the three may not share theme *and* dominant hue.

Then, whichever mode you're in: **recommend one, with a one-sentence reason.** A designer who presents options without an opinion has abdicated. And if the user says "just make it good" — take your recommendation and go. But *construct* the alternatives internally regardless: **the act of building three real candidates is what stops you shipping the first thing you thought of**, whether or not the user ever sees them.

---

## 8. Self-Check — and why a checklist is the weakest form of it

- [ ] Did I name the first-order **and** second-order default, and reject both? (§2)
- [ ] Can I state my page's coordinates on all five axes? If any axis is "whatever was easiest", **that is the axis that made it generic**. (§3)
- [ ] Did I read `.finesse/log.json` (or the CSS stamp), say the rotation out loud, and does this page differ from the last on **≥3 axes**? (§4)
- [ ] Did I write the log entry and the stamp after Pre-Flight? An unrecorded build is one the next run will collide with. (§4.3)
- [ ] If I opened an example, did I deliberately move off at least one of its axes? (§5)
- [ ] Did the die roll happen, and if I overrode it, did I write down why? (§6)
- [ ] If I showed a trio, does it pass the squint test — three different concrete nouns? (§7)
- [ ] Is there **one** decision on this page a different designer would argue with? If every choice is safe, it's generic. "Inoffensive" and "forgettable" are the same score.
- [ ] Layout families: ≥4 distinct across the page, none appearing more than twice? (SKILL §5)

> **Know what this list is worth.** A prose checklist is self-graded, and a model grading its own work ticks the boxes. The items above that can be **mechanically counted** — eyebrow count ≤ `ceil(sections / 3)`, ≥4 layout families, no 3 consecutive zigzags, zero banned-default fonts, contrast ratios — should be *counted*, not felt. And the strongest check of all is not on this list: **render the page, screenshot it, and look at it.** Then ask one question, honestly:
>
> *"Does any part of this read as default-LLM aesthetics — violet glow on near-black, an Inter headline, a row of empty card-grid boxes?"*
>
> A generated page that has never been looked at has not been checked — but **the one looking is him, not you.** Ship it with the question attached instead of spending a browser round-trip to answer it yourself:
>
> ```
> 你打开看一眼 —— 有没有哪块像是 AI 默认那套？（近黑底上的紫光、Inter 大标题、一排空卡片）
> ```
>
> What you may never do is skip both and write about the page as if you'd seen it.
