# AI Console — the delegation layer, not a page type

> **This file is a capability layer, not a category.** It answers *"something other than the user is doing the work — how does the page stay trustworthy?"*, and it **stacks on top of** whatever the page already is:
>
> | The page underneath | What you already picked | This file adds |
> |---|---|---|
> | **工作台 · desktop body** | `product-ui.md` shell at A.1's density and soul | §8's three-column shell, and everything below |
> | **工作台 · phone body** | `h5-mobile.md` morph A.1 | **§9** — the phone form, which replaces §8 entirely |
> | **后台** that grew an agent | `product-ui.md` (+ `workflow-ui.md`) | the stream, states, stop and receipt — **it stays a 后台** |
>
> **Adding an agent never changes what the page is** (SKILL.md §1's resolver decides that: 围着一批业务对象 → 后台, 围着他反复做的一件事 → 工作台). It changes what the page must prove. Don't reach for this file to decide a register; reach for it once something is running.

`product-ui.md` splits a 后台 by the page's job: pages you **read** (a dashboard fails by being unreadable) and pages you **operate** (a console fails by being unfinishable, per `workflow-ui.md`). **Delegated work is a third failure mode on either of them, and on a 工作台 too** — building it out of read-or-operate parts alone produces a page that is pleasant and useless.

**A page you delegate on fails by being untrustworthy.** Not ugly, not slow, not confusing: untrustworthy. The user handed a task to something that acts on its own, and the page's entire job is to answer four questions continuously, without being asked:

| The question | What answers it | What happens when the page doesn't |
|---|---|---|
| **What is it doing right now?** | the live step in the run stream (§2) | the user watches a spinner and cancels a run that was 4 seconds from done |
| **Why did it do that?** | the expandable tool-call evidence (§2.B) | one wrong output and the user never trusts any output |
| **What is this costing me?** | per-run tokens / time / model (§6) | the bill arrives at the end of the month and the tool gets switched off |
| **How do I stop it?** | a resident stop control (§4) | the user closes the tab, which stops nothing |

Every rule in this file is downstream of those four. If a decision doesn't serve one of them, it's decoration, and this is a register where decoration reads as *evasion*.

> **This file is a sub-type of `product`, not a fifth register.** Load `product-ui.md` first: the substrate (§0), the shell IA (§1), the tables, the interaction states and the density rules are all unchanged. This file replaces the *middle* — what sits in the main column, what the primary action is, and which states exist. Pull `workflow-ui.md` as well when the agent's output has to be committed by a human (§5 is that file's pre-submit check, relocated). On a phone, wrap it in `h5-mobile.md` (§9).

---

## 0. Is this an AI console?

Yes when **the page shows work being done by something that isn't the user, over a duration**. The tells:

- An **agent / assistant / copilot / 智能体 / AI 助手** runs multi-step tasks and reports back.
- The page has a **conversation or an instruction box** that produces *actions*, not just answers.
- There is a **queue**: tasks waiting, running, done. The user supervises rather than performs.
- Output arrives **streamed or asynchronously**, and a run can fail halfway.

**None of these tells say anything about *what the page is*** — they say something is running on it. Decide 后台 vs 工作台 first (SKILL.md §1), pick the body (desktop shell or morph A.1), *then* layer this file on.

**Not a delegation surface** — don't drag the machinery in:

- A **chatbot** with no tools, no queue, no artifacts: that's a single component plus a message list, and the whole apparatus below is overkill. `component-scope.md`.
- A **dashboard about** AI usage (model spend, request volume, latency percentiles): that is a page you *read*. `product-ui.md`, unchanged.
- A **prompt/config form** that produces a saved setting: `workflow-ui.md`.

**The tiebreak, when the brief just says "AI 工作台":** *"这个页面主要是在等 AI 干完活，还是在看它干过的活？"* Waiting on live work → this file. Reviewing finished work → a dashboard with a run log, which is `product-ui.md` plus §2's stream as one card.

---

## 1. The three tenses, on one screen

A dashboard shows the **past**. A wizard shows the **present**. An AI console has to show all three at once, because the user's next decision depends on which tense the trouble is in.

```
FUTURE   queue / plan / scheduled runs      "what's about to happen, and can I stop it before it does"
PRESENT  the live run, step by step          "what is happening right now, and is it stuck"
PAST     history, artifacts, cost            "what happened, why, and what did it produce"
```

**All three must be reachable without navigation.** Not three tabs: three regions. The moment "what's queued" costs a click, the user stops trusting the queue, and a queue nobody trusts is a queue that silently drains a budget.

The cheapest correct implementation on desktop is the three-column shell (§8). On a phone it is a **pinned strip (future) + stream (present) + a sheet (past)** (§9). What is *not* acceptable in either: showing only the present, which is what every chat UI does and why every chat UI makes a bad workbench.

---

## 2. The run stream — the centerpiece that replaces the chart

In a dashboard, the load-bearing element is a chart. Here it is the **run stream**: a vertical, time-ordered list of what the agent did, one row per step, newest at the bottom, auto-scrolling only while the user is already at the bottom.

### 2.A The row

One step is one row, and a row is legible **collapsed**:

```
[icon] [step label]                    [duration] [chevron]
       ↳ one line of the actual result, truncated
```

- **The icon carries the step type** (thinking · tool call · file write · network · waiting on you · output). Type by shape, not only by color: an icon set that differs only in hue fails the moment someone is colorblind or the row is greyed out as historical.
- **The label names the tool and its object**, not the category: `读取 orders.csv (2,481 行)`, not `工具调用`. A stream of `工具调用 ×7` is a progress bar wearing a costume.
- **Duration is always shown, per step.** It is the only thing that distinguishes "slow" from "hung", and the user is making that judgement every few seconds whether or not you help.
- **Rows are connected by a rail** (a 1px vertical hairline through the icon column) so the stream reads as one process, not as a list of notifications.

### 2.B Expansion is where the trust is

Collapsed rows keep the page scannable; the expanded row is what makes the page *auditable*. On expand, show the evidence and nothing else:

```
入参    { "file": "orders.csv", "sheet": "2026-Q2" }
出参    3 columns changed · 2,481 rows scanned          [查看完整结果]
耗时    1.42s          模型  —          token  —
```

Monospace the payloads, `tabular-nums` the numbers, cap the block at ~240px with its own scroll. **Never render a tool payload as prose.** The value of the evidence is that it is verbatim; prettifying it destroys the only property that matters.

Default state: **collapsed for successful steps, expanded for failed ones**. A failure the user has to click to see is a failure you are hiding.

### 2.C Streaming text

Token-by-token output is legitimate *inside a step's output block*, at 1 chunk/frame max, with a block cursor, and it must be **skippable** (a click, or `Esc`, jumps to the final text). Two hard rules:

- The stream is **not** the loading indicator. A typing cursor tells the user something is emitting text; it does not tell them which of nine steps they are in, and the step rail must be doing that job independently.
- The container must **not** reflow the page as text arrives. Reserve the block's height or grow it downward only. A stream that pushes the stop button around the screen is actively hostile: the one control the user reaches for while anxious is the one that keeps moving.

---

## 3. The nine run states

`product-ui.md` §5 ships eight interaction states for a component (default, hover, focus, active, disabled, loading, empty, error). Those describe a **control**. A run is a different animal and needs its own set. Ship all nine, name them once in the token layer, and reuse the same visual language in the queue, the stream row, and the history table.

| State | Reads as | Must offer | The failure if you skip it |
|---|---|---|---|
| `queued` | dimmed row, position number | remove from queue | user can't tell "not started" from "stuck" |
| `thinking` | pulsing rail dot, elapsed timer | stop | the classic infinite spinner |
| `tool` | tool name + spinner on that row | stop | user can't see what it's touching |
| `streaming` | live text + cursor | stop, skip animation | — |
| `awaiting-input` | **accent-filled card**, sound-free but unmissable | approve / edit / reject (§5) | the run silently blocks and the user finds out in an hour |
| `succeeded` | check, muted, collapsed | open artifact, rerun | — |
| `failed` | `--down` rail, expanded by default, error verbatim | **retry from this step**, retry all, copy error | retry-all is a tax on the user for the agent's mistake |
| `stopped` | half-tone, "stopped by 你 at step 4/9" | resume, discard | user can't tell their stop from a crash |
| `partial` | succeeded-with-warnings | see what was skipped | the most dangerous state to render as success |

**`partial` is the one nobody builds and everybody needs.** An agent that processed 2,400 of 2,481 rows has not succeeded, and rendering it green is how a data pipeline quietly loses 81 rows for six weeks. Give it its own color slot (`--warn`) and its own verb: *查看跳过的 81 条*.

---

## 4. Stop is a primary control

The single most-violated rule in this register. In a dashboard, the primary action is a filter. In a wizard, it's 提交. Here it is **停止**, and it belongs to the same tier as the submit button in `workflow-ui.md`:

- **Resident, not conditional.** The control occupies its slot at all times; it disables between runs rather than unmounting. A button that appears only during a run appears exactly when the layout is already shifting, and the user chases it.
- **Never inside a menu, never behind a hover.** On desktop it sits in the composer row; on a phone it sits in the thumb zone (§9), 44px minimum.
- **Distinct from 清空 / 删除.** Stopping is reversible-ish and frequent; deleting is destructive and rare. If they are the same shape in the same corner, the user will eventually hit the wrong one at the worst moment.
- **It must actually settle.** On press: the run goes to `stopped` **within one frame** at the UI layer, with the step it died on named. A stop that waits for a server round-trip before changing anything on screen is indistinguishable from a stop that didn't work, and the user presses it four more times.

```js
// optimistic, then reconcile — the UI state is not the server's to own
stopBtn.addEventListener('click', () => {
  run.state = 'stopped';           // paint immediately
  render(run);                     // "已在第 4/9 步停止"
  api.stop(run.id).catch(() => {   // reconcile; never silently revert
    banner('停止请求没送达，任务可能仍在运行', 'warn');
  });
});
```

---

## 5. The approval card — human-in-the-loop

Before an agent does anything **consequential and irreversible** — sends a message to a customer, writes to a production table, spends money, publishes — the run stops and emits an approval card *into the stream*, in place, where the user is already looking.

This is `workflow-ui.md`'s pre-submit check with the author changed. Same anatomy, four parts, in this order:

```
要做什么   给 37 位客户发送补发优惠券短信
影响什么   37 条短信 · ¥0.06/条 · 预计 ¥2.22 · 不可撤回
凭什么     ↳ 基于第 3 步筛出的「已付款未发货 > 48h」名单   [查看名单]
           [ 批准并继续 ]  [ 改一下 ]  [ 拒绝 ]
```

- **凭什么 is the part that gets dropped and the part that decides the answer.** An approval card without a link back to the evidence is a dialog box asking the user to trust a stranger. It must reference the step that produced the list, and that reference must be clickable.
- **The scary number is typeset large**, in `--warn` or `--down` when it is money, volume, or irreversibility. 37 is not a detail; it is the whole decision.
- **改一下 is not optional.** Approve/reject alone forces a full rerun to change one parameter, which trains the user to approve things they would have edited.
- **The card blocks the run, not the page.** The rest of the console stays live: other runs continue, history stays browsable. A modal here is wrong twice over — it hides the evidence behind it, and it implies the whole workbench is halted when only one run is.
- **Never pre-check the risky option.** Same rule as `commerce-ui.md`'s dark patterns, and it matters more here because the agent, not the user, wrote the proposal.

**Timeout policy must be stated on the card**: what happens if nobody answers. Auto-approving on a timeout is a bug with a plan; auto-cancelling is fine if it says so.

---

## 6. Cost and context are first-class

Every other product register can treat resource use as an admin concern. This one can't: cost is per-action, variable, and invisible, which is the exact profile of a thing that gets abandoned after one surprising invoice.

- **Per-run footer**: `9 步 · 42.6s · 18.2k token · ¥0.41`. Mono, tabular, quiet. Not a badge, not a chart — a receipt line.
- **Per-step token counts** live in the expanded row (§2.B), not the collapsed one. Collapsed rows show duration only; token counts at rest turn the stream into a spreadsheet.
- **Budget as a bounded meter, not a number.** `¥18.4 / ¥50 本月` with a thin fill bar is legible at a glance; `¥18.4` alone answers nothing. Show the fill in `--accent`, cross into `--warn` at 80%, `--down` at 100% — and at 100% say what actually stops.
- **Context/window pressure is a real state**, not a hidden truncation. When a long run starts dropping earlier context, say so in the stream as a step (`↳ 上下文已裁剪，丢弃了第 1–3 步的原文`). Silent truncation is the source of the "it forgot what I told it" complaint that the user will otherwise blame on the whole product.
- **Model identity is metadata on the run**, shown once in the header and once per step only when the run mixes models. A model picker permanently occupying prime real estate is a settings page leaking into a workbench.

---

## 7. The artifact surface

Anything the agent *produces* — a table, a document, a chart, a diff, a piece of code — must land on a **surface you can look at and act on**, not stay inside a message bubble. Bubbles are for talk; artifacts are for work.

- **Desktop**: the right column (§8), one artifact at a time, with the run stream keeping its scroll position. Tabs only when the run genuinely produced several.
- **Phone**: a push layer or a sheet (§9), opened from the step that produced it.
- **Always three affordances on an artifact**: 复制 · 下载/导出 · 在哪一步生成的 (a link back into the stream). The third one is what makes an artifact defensible later; without it, an output is an assertion.
- **A diff is the highest-value artifact form** when the agent modified something that already existed. Show before/after, not just after. This is the difference between "trust me" and "check me".

---

## 8. Desktop shell — the three-column console

```
┌──────────┬───────────────────────────────┬──────────────┐
│  RAIL    │   RUN STREAM (the present)    │  ARTIFACT /  │
│  queue + │   ────────────────────────    │  APPROVAL /  │
│  history │   step · step · step …        │  CONTEXT     │
│  (future │                               │  (the past   │
│  + past) │   ─────────────────────────   │  and the     │
│          │   [ composer ] [停止] [发送]  │  evidence)   │
└──────────┴───────────────────────────────┴──────────────┘
   260–300px          1fr (min 0)              320–380px
```

- The **stream column carries the scroll**; the rail and the aside scroll independently (`min-height: 0` on the grid children or the whole thing overflows the page — the same failure `mobile-floor.md` M2 describes, in the vertical direction).
- The **composer is pinned to the bottom of the stream column**, not to the viewport. It belongs to the run, and pinning it to the viewport makes it float over the aside on narrow screens.
- **The aside is contextual, and it has a resting state.** When there is no artifact and no approval pending, it holds the run's context: which files/data the agent can see, which tools it may call, the budget meter. An aside that is empty half the time will be collapsed by the user on day two and then miss the approval card on day three.
- **Below ~1180px**, the aside becomes an overlay drawer, the rail becomes icons. **Below ~860px**, treat it as the phone layout (§9) rather than shrinking three columns into a stripe.
- **Two-tone shell fits this register unusually well** (`product-palettes.md` §4.A): dark rail for the queue, light content for the stream. It gives the "what's queued" region a physically different surface from "what's happening", which is exactly the distinction §1 is trying to make. The rail must be tinted to the page's hue.

**The alternative shell — canvas-dominant** — flips the weights: a large artifact canvas (a table, a board, a document) with the stream as a narrow right rail. Use it when the artifact is the product and the agent is an assistant to it (a spreadsheet copilot, a design canvas). Same components, different `fr`. Say which one you rejected and why.

---

## 9. Phone shell — what changes

Wrap this file in `h5-mobile.md` **morphology A (app shell)** and keep its frame contract exactly (§1 viewport + locked `body` + scrolling container, §2 safe areas). What changes is which of §1's three tenses gets which piece of the screen:

| Desktop | Phone |
|---|---|
| left rail (queue) | a **pinned run strip** under the status bar: `● 2 个任务在跑 · 客服值守 3/9 步` — tap to expand into the queue sheet |
| center stream | the **whole scroll container**; this is the page |
| right aside | a **bottom sheet** (artifact, evidence, context) pushed from the step that owns it |
| composer + stop at bottom of column | the **thumb bar**: `[输入] [停止] [发送]`, `padding-bottom: calc(env(safe-area-inset-bottom) + 11px)` |

Phone-specific rules that have no desktop equivalent:

- **停止 goes in the thumb bar and stays there.** It is the reason this page is open on a phone at all: the user is away from their desk and something needs to be stopped or approved. 44px minimum, `:active` press state, and never adjacent enough to 发送 to be mis-tapped (≥12px gap, or put them on opposite ends).
- **The approval card must survive a locked screen.** It renders as a full-width card in the stream *and* the pinned strip flips to `--warn` with a count (`1 个任务在等你`), because the user will come back to this page rather than watching it. Nothing in an H5 page can push a notification; the strip is the entire recovery mechanism.
- **Auto-scroll is off by default on touch.** A stream that yanks itself down while a thumb is scrolling is unusable. Resume auto-scroll only when the user is within ~40px of the bottom, and show a `↓ 3 条新步骤` pill otherwise.
- **The keyboard eats half the frame.** When the composer focuses, the stream must keep its last row visible: listen to `visualViewport.resize` and translate the thumb bar, rather than trusting the browser.
- **Expanded evidence goes to a sheet, not inline.** A 240px payload block inside a 390px-wide stream turns the page into a two-line-per-row mess. Tap a step → sheet.

---

## 10. Color and motion for this register

**Reject the default first, out loud.** The lazy default for AI is now fixed and instantly recognizable: near-black page, violet/indigo accent, purple radial glow behind a floating orb, sparkle icon, gradient text on the word "AI". `anti-cheap.md` bans the glow and the gradient text on every register; here the whole *palette* is the tell. `product-palettes.md` has sixteen accents and twelve sets — the number of them that read as "AI" is zero, which is the point.

**What color must do in this register, before it does anything aesthetic:** separate what the agent did on its own from what needs a human. That is a two-color semantic system, and it should be visible from across the room:

```css
--auto:   var(--accent-2);   /* it handled this itself           */
--needs:  var(--accent);     /* it is waiting on you             */
--warn:   …                  /* partial / budget pressure        */
--down:   …                  /* failed / irreversible in an approval card */
```

Pick the pair so that `--needs` is the more saturated of the two: the user's eye should land on the thing that is blocked, not on the 200 rows that resolved themselves. A palette where success is loud and blocking is quiet is backwards, and it is the default in every framework's stock components.

**Motion is `product-ui.md` §0.4 — feedback only, SPECTACLE 1–3 — with one addition and one ban.**

- The addition: **a liveness signal**. Exactly one element on the page may pulse while a run is active (the rail dot on the current step, ~1.6s, opacity only). It answers "is this frozen or working" without a spinner, and it is the only continuous animation this register earns.
- The ban: **no orb, no aurora, no shimmering gradient border, no particles**. Ambient motion means "look at me" and everything here that means "look at me" must mean something is wrong.
- `prefers-reduced-motion` freezes the liveness pulse to its mid-opacity and swaps streaming text to whole-block appends. Both must still communicate state — a frozen pulse next to an elapsed-time counter still reads as running, which is why §2.A makes duration mandatory.

---

## 11. Anti-patterns *(add to `product-ui.md` §9)*

- **The chat window pretending to be a workbench.** Alternating left/right bubbles, avatar per message, a send button and nothing else. It has no queue, no state set, no stop, no artifacts — and it is what a model produces when asked for an "AI 工作台" without this file. Right-aligned user bubbles are fine; *only* bubbles is the failure.
- **The single spinner.** One indeterminate loader standing in for nine steps. Every question in this file's opening table is unanswerable while it spins.
- **Stop hidden until hover, or absent.** §4.
- **Green success on a partial run.** §3.
- **Approval as a `confirm()` modal** with no evidence link. §5.
- **Cost shown only in settings** — or worse, only in the vendor's billing console. §6.
- **Fake-precise agent stats** — `准确率 98.7%`, `节省 4.1× 时间` — on a page whose entire premise is auditability. This is `anti-cheap.md`'s fake-precise-number rule at its most damaging, because here the user *can* check.
- **Anthropomorphic filler in the stream.** `让我想想…` / `好的！我这就去办~` as step labels. A step label is a log line; personality belongs in the response text, if anywhere, and never in the audit trail.
- **The purple orb.** §10.
- **Infinite history with no anchor.** A stream that only scrolls, with no run boundaries, no timestamps, no jump-to-run. History is one of the three tenses; it needs an index.

---

## 12. Pre-flight *(in addition to the shared §8 and `product-ui.md` §10)*

- [ ] All three tenses (§1) visible or one tap away — **no tab hides the queue**.
- [ ] Every stream row: type icon (shape-distinct) + specific label + duration.
- [ ] A step expands to verbatim payload; failed steps expand **by default**.
- [ ] All nine run states (§3) render, including `partial` and `stopped`. Screenshot each.
- [ ] Stop is resident, ≥44px, outside any menu, and repaints within one frame (§4).
- [ ] `failed` offers **retry from this step**, not only retry-all.
- [ ] An approval card carries 要做什么 / 影响什么 / **凭什么 (linked)** / three actions incl. 改一下.
- [ ] Approval blocks the run, not the page. No modal.
- [ ] Per-run receipt line + a bounded budget meter with a stated 100% behaviour.
- [ ] Artifacts carry 复制 · 导出 · 回到生成它的那一步.
- [ ] Streaming text is skippable and does not reflow the composer.
- [ ] `--auto` vs `--needs` are distinguishable at a glance, and `--needs` is the louder one.
- [ ] Exactly one continuous animation on the page, and it stops when no run is active.
- [ ] Phone build: stop in the thumb bar, approval reflected in the pinned strip, auto-scroll off while the user is scrolling (§9).
- [ ] Nothing in the palette is the AI-violet default; the rejected default is named in the Design Read (SKILL.md §0.D).
