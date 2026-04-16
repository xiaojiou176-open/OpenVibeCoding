# OpenVibeCoding Design System

## Purpose

This file is the canonical design system for OpenVibeCoding's public front door,
dashboard, and desktop control-plane surfaces.

Read this as the design constitution for one specific product:

- **Product identity**: an L0 AI engineering command tower
- **Primary emotion**: calm authority under pressure
- **Secondary emotion**: precise forward motion
- **Never become**: a generic admin panel, a neon AI demo, or a marketing-only landing page

If a page-specific override exists under `design-system/pages/`, that override
may tighten or specialize the rules below, but it may not contradict the core
product identity.

## Donor Source Trace

This design system is repo-owned, but it is not donor-free.

OpenVibeCoding's current design absorption stack is:

- **Primary donor**: `Linear`
- **Secondary donors**: `IBM`, `Vercel`
- **Reference mirror root**: `${HOME}/.codex/design/awesome-design-md`

Repo-local source-trace anchors:

- `Linear`: `${HOME}/.codex/design/awesome-design-md/design-md/linear.app/DESIGN.md`
- `IBM`: `${HOME}/.codex/design/awesome-design-md/design-md/ibm/DESIGN.md`
- `Vercel`: `${HOME}/.codex/design/awesome-design-md/design-md/vercel/DESIGN.md`

Absorption intent:

- `Linear` owns interaction rhythm, first-screen compression, and the sense
  that every surface is part of one product loop rather than a loose route wall.
- `IBM` sharpens information architecture, enterprise-grade readability, and
  the calm structure behind dense product surfaces.
- `Vercel` informs motion restraint, front-door confidence, and the polish of
  premium developer-facing public entrypoints.

These donors inform layout and language discipline. They do **not** authorize
copying product claims, brand identity, or page structure verbatim.

## Atmosphere

OpenVibeCoding should feel like an architecture studio crossed with a mission
control room.

- **Density**: medium-high on control surfaces, medium on the public front door
- **Variance**: asymmetric but disciplined
- **Motion**: restrained, purposeful, low-noise
- **Mood words**: deliberate, governed, exact, premium, anti-generic

Interpretation:

- The public front door should feel like a command deck briefing, not a SaaS
  hero with filler marketing sections.
- The dashboard and desktop should feel like a cockpit: clear hierarchy, fast
  scanning, immediate understanding of what is happening now.

## Typography

- **Display / section headers**: `Space Grotesk`
- **Body / operational text**: `Manrope`
- **Code / IDs / timestamps / status tokens**: `JetBrains Mono`

Rules:

- Never use `Inter` for OpenVibeCoding hero or cockpit surfaces.
- Headings should signal confidence through weight and spacing, not giant scale.
- Monospace belongs to machine facts only: run IDs, queue IDs, lane names,
  file refs, timestamps, contract artifacts.
- Long prose blocks should stay narrow and readable; control-plane pages should
  bias toward short labels and dense lists.

## Color System

Use a dark-neutral command palette with one restrained action accent.

| Role | Token | Value | Usage |
| --- | --- | --- | --- |
| Canvas | `--cp-bg` | `#0B1220` | app shell, dashboard canvas, desktop shell |
| Surface | `--cp-surface` | `#111A2E` | cards, drawers, panels |
| Surface Raised | `--cp-surface-raised` | `#17233B` | hover state, active cards, layered panels |
| Ink | `--cp-ink` | `#E8EEF8` | primary text |
| Muted | `--cp-muted` | `#9FB0C8` | descriptions, supporting labels |
| Border | `--cp-border` | `rgba(159,176,200,0.16)` | separators, card outlines |
| Accent | `--cp-accent` | `#1FB981` | primary CTA, healthy motion, selected action |
| Warning | `--cp-warn` | `#E59A2F` | caution, queued attention |
| Danger | `--cp-danger` | `#D95C5C` | failure, broken flow, hard alerts |

Rules:

- Keep one accent color only.
- No purple glow, no neon blue gradients, no generic AI chroma.
- Avoid pure black and pure white. OpenVibeCoding should feel calibrated, not harsh.
- Healthy status can use green, but do not let the whole UI become “green dashboard”.

## Layout Principles

- No generic three-equal-feature-card rows as the default answer.
- Prefer a **briefing layout**:
  - headline and pain hook
  - one concise operator loop
  - one proof-oriented explanation
  - one adoption router
- On control surfaces, favor:
  - top summary rail
  - primary action strip
  - left-to-right operational scan
  - explicit “what is blocked / what is next / where truth lives”
- Group pages by operator intent, not by raw data type.
- Use spacing via `gap-*`, not `space-*`.
- Use semantic color tokens, not raw Tailwind color literals.

## Component Rules

### Buttons

- Primary buttons should feel decisive, not loud.
- Hover can slightly lift or brighten; avoid scale-jump hover behavior.
- No emoji icons. Use purposeful SVG icons only.

### Cards

- Cards exist to communicate hierarchy, not because every dashboard needs cards.
- High-density surfaces may use stacked bands, bordered sections, or inset
  panels instead of card farms.

### Tables and Lists

- Lists should optimize scan speed.
- Important state should be visible in the first two rows/columns or the top summary band.
- Dense surfaces must still preserve whitespace around critical actions.

### Empty / degraded states

- Never use cute filler copy.
- Always answer:
  - what is missing
  - why it matters
  - what the next operator action is

## Motion

- Motion exists to reinforce operational state, not to entertain.
- Default transitions: 150-250ms.
- Use opacity / transform only.
- Good motion examples:
  - live refresh resumed/paused feedback
  - lane state shift
  - drawer reveal
  - compare/proof section emphasis
- Bad motion examples:
  - bouncing arrows
  - endless decorative shimmer
  - giant pulse effects around CTAs

## Page Hierarchy Rules

The product must visually teach this loop:

1. **Plan**
2. **Delegate**
3. **Track**
4. **Resume**
5. **Prove**

That means:

- PM entry should feel like the start of the loop.
- Command Tower should feel like the active cockpit.
- Workflow Cases should feel like the durable operating record.
- Run Detail / Compare should feel like the truth and replay room.
- Policies / Agents / Contracts should feel like inspection and governance surfaces.

## Copy Style

- Prefer exact, operator-grade language over brand fluff.
- Strong hooks are allowed, but must stay truthful.
- Good:
  - `Stop babysitting AI coding work.`
  - `The command tower for AI engineering.`
  - `Proof before trust.`
- Bad:
  - `Scroll to explore`
  - `Experience the future`
  - fake KPIs / fake SLAs / fake uptime banners

## Anti-Patterns

Never ship these into OpenVibeCoding:

- emoji icons
- neon purple/blue AI gradients
- generic glassmorphism for everything
- fake metrics, fake percentages, fake activity charts
- placeholder enterprise testimonial sections
- “3 equal cards and a CTA” as the default dashboard/home layout
- filler marketing verbs without operational meaning
- dashboard chrome that hides Workflow Cases / Agents / Contracts as an afterthought

## Implementation Notes

- If `shadcn` patterns are used, prefer composition from existing primitives.
- Use semantic colors and `gap-*`.
- Keep overlay and z-index behavior minimal and inherited.
- The dashboard and desktop should share a stable visual language, even if
  density differs.
