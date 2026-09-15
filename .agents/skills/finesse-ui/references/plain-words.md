# Plain Words — Saying finesse's Vocabulary Out Loud

finesse reasons in `register` / `SPECTACLE` / `grain` / `scrim` / `eyebrow`. **The user does not.** Every one of those words is load-bearing internally and opaque externally, and the places they leak out — the Design Read, the audit report, the memory-lock notice — are exactly the places where the user is supposed to make a decision.

A user who has to ask "what's an eyebrow?" before he can judge your finding is a user who will say "looks fine, go ahead." That is not agreement; it is a dead confirmation gate.

> **When to load:** any time you are writing text the *user* reads — §0.B Design Read, `audit.md` findings, the `PRODUCT.md` / `design-model.yaml` lock notice, or a reply explaining why something is a tell. Not needed while reasoning internally or writing code comments.

---

## The rule

**First time a term appears in user-facing output, follow it with a short parenthetical in observable terms. After that, use it bare.**

- Describe what the user would **see**, not what the term means. "Eyebrow (标题上方那行全大写小字)" beats "eyebrow (a kicker label)" — the second is a synonym, not an explanation.
- **One clause.** If it needs two sentences, the term wasn't worth using; say the plain thing instead.
- **Don't gloss twice in one reply.** Repetition reads as talking down.
- **Match the conversation's language.** Two columns below; pick one, never emit both.
- **Never gloss a term the user introduced themselves.** If they said "grain", they know.
- If a term isn't in this table and you can't gloss it in one clause, **don't use it** — write the plain description instead.

---

## Direction & routing — appears in the §0.B Design Read

| Term | Plain (EN) | 人话（中文） |
|---|---|---|
| `register` | which kind of page this is, which changes every later decision | 这是哪一类页面，后面所有判断都跟着它走 |
| `brand` register | the design *is* the product — a page meant to impress | 设计本身就是产品，目标是让人记住 |
| `product` register | the design *serves* the product — a page meant to be used daily | 设计是为了好用，目标是天天用不累 |
| `commerce` register | a page whose job is to sell one thing or help compare many | 卖东西的页面：卖单品，或者帮人比价挑选 |
| `SOUL` | how distinctive the style is — 1 is anonymous, 10 is unmistakable | 风格有多突出：1 是没个性，10 是一眼认出是你 |
| `SPECTACLE` | how much real motion/3D the page carries — 1 is fully still, 10 is a live engine | 视觉上有多"动"：1 是完全静止，10 是实时渲染的动态背景 |
| `DENSITY` | how much fits on one screen — 1 is airy, 10 is data-packed | 一屏塞多少内容：1 是很空，10 是塞满数据 |
| `soul` / `persona` | the page's personality, stated in two or three words | 这一页的调性，两三个词说清 |
| `substrate` | the thin invisible layer that makes a page feel expensive rather than flat | 那层几乎看不见的底子，决定页面像"做得贵"还是像"随便拼的" |
| `hero` | the first screen, before any scrolling | 首屏，还没往下滚的时候看到的那块 |
| `hero engine` | the one real animation that carries the first screen | 撑起首屏的那一个真动效 |
| `rotation` | deliberately not reusing the look of your recent pages | 刻意避开最近几次做过的样子 |

## Visual detail — appears in audit findings

| Term | Plain (EN) | 人话（中文） |
|---|---|---|
| `grain` | a nearly invisible speckle over flat color, so it doesn't read as plastic | 一层几乎看不见的噪点，让大色块不显得"塑料" |
| `vignette` | the edges of the screen darkened slightly, pulling the eye to the middle | 四周稍微压暗，把视线拉到中间 |
| `scrim` | a translucent dark layer over a photo so text on top stays readable | 图片上压的一层半透明暗色，让上面的字看得清 |
| `hairline` | a divider thinner and lighter than the usual grey 1px line | 比常见的 1px 灰线更细更轻的分隔线 |
| `eyebrow` | the small all-caps line above a headline (`ABOUT`, `OUR PROCESS`) | 标题上方那行全大写小字（`关于我们`、`我们的流程`） |
| `marquee` | a strip of text sliding sideways, forever | 一条一直横向滚动的文字带 |
| `glassmorphism` | frosted translucent cards you can see the background through | 磨砂半透明的卡片，能透出后面的背景 |
| `gradient text` | headline letters filled with a color fade instead of one color | 标题字的颜色是渐变的，不是单色 |
| `side-stripe border` | a colored bar down one edge of a card | 卡片一侧那条竖着的彩色条 |
| `accent` | the one color that owns the whole page | 整页只用这一个主色 |
| `color lock` | the accent never changes between sections | 主色从头到尾不换 |
| `token` | a color/font saved once by name, so it can't drift halfway down the file | 颜色和字体只在一处定义，防止写到后面越写越歪 |
| `tracking` | the gap between letters | 字与字之间的间距 |
| `line-height` | the gap between lines of a paragraph or headline | 行与行之间的间距 |
| `layout family` | one arrangement pattern (three cards / split image+text / full-width quote) | 一种排版方式（三栏卡片 / 左图右字 / 整行大字） |
| `bento` | a grid of unequal tiles, like a bento box | 大小不一的格子拼在一起，像便当盒 |
| `KPI tile` | the small card at the top showing one key number | 顶部那种只显示一个关键数字的小卡片 |
| `shell` | the frame around a dashboard — sidebar, top bar, content area | 后台页面的外框：侧边栏、顶栏、内容区 |

## Quality & health — appears in audit findings and the pre-flight report

| Term | Plain (EN) | 人话（中文） |
|---|---|---|
| `AI tell` | a detail that makes visitors assume the page was auto-generated | 一眼让访客觉得"这是 AI/模板做的"的细节 |
| `contrast ratio` | whether text is dark enough against its background to read comfortably | 文字和背景的深浅差够不够，够了才看得舒服 |
| `AA` | the accessibility bar most of the web is held to | 网页普遍要达到的无障碍及格线 |
| `touch target` | the tappable area of a button — too small and thumbs miss it | 按钮实际能点到的范围，太小手指会点不中 |
| `focus state` | the visible outline showing where you are when navigating by keyboard | 用键盘操作时，显示"现在选中哪里"的那圈描边 |
| `reduced motion` | the system setting for people who get dizzy from animation | 系统里那个"减少动态效果"的开关，给看动画会晕的人用 |
| `progressive enhancement` | the page still works with the fancy parts stripped out | 把炫的部分全去掉，页面照样能看能用 |
| `breakpoint` | a screen width where the layout has to rearrange | 屏幕宽到/窄到某个值时，排版要重新摆 |
| `overflow` | content wider than the screen, causing a sideways scrollbar | 内容比屏幕宽，导致能左右拖动 |
| `CLS` | things jumping around while the page is still loading | 页面还在加载时，内容跳来跳去 |
| `lazy-load` | heavy parts load only when they're about to be seen | 重的东西等快要看到了才加载 |
| `P0 / P1 / P2` | ships broken / clearly cheap / polish | 现在上线会出问题 / 一眼看出是 AI 做的 / 打磨项 |

---

## Terms to never say to a user

Internal bookkeeping. They belong in `.finesse/log.json` and the CSS stamp, not in a sentence aimed at a person:

- **five-axis coordinates** (`A=mono+acid-lime · B=900/300 · C=pinned-h-track`) — say *"避开了最近三次的方向"* instead (`divergence.md` §4.4).
- **axis letters** (`differs on E + C + A (3/5 ✓)`) — the user cannot verify this and cannot object to it.
- **file names of the memory layer** (`log.json`, `design-model.yaml`) — say *what is locked*, not where it's stored (`init.md`).
- **reference file names** (`anti-cheap.md`, `page-crafting.md`) — cite the finding, not your source.
- **`argmax` / `attractor` / `two-altitude`** — method vocabulary from `divergence.md`. Describe the result, never the machinery.
