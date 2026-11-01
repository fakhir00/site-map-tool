# Design System: GapCrawl

## 1. Visual Theme & Atmosphere
**GapCrawl** is a high-precision SEO architecture and content-gap intelligence engine. 
The visual atmosphere is **Tactical Engineering Cockpit** meets **Swiss Information Design**:
- **Density:** 8/10 (Cockpit Dense). High information density, tight metric groupings, visual hierarchy driven by weight and contrast rather than bloated padding.
- **Variance:** 7/10 (Offset Asymmetric). Split workbench layouts, asymmetric tree-and-inspector panes, offset data tables rather than repetitive equal-width cards.
- **Motion:** 5/10 (Fluid Responsive). Snappy spring physics for expanding tree clusters, subtle live-status pulse indicators, and zero gratuitous floating animations.
- **Surface Feel:** Matte dark slate and obsidian canvas with razor-sharp 1px structural borders (`rgba(255, 255, 255, 0.08)`). No neon glow slop, no generic frosted glass abuse.

---

## 2. Color Palette & Functional Roles
- **Obsidian Canvas** (`#09090B`) — Primary background surface across dark workspaces.
- **Cockpit Panel** (`#121215`) — Secondary container surfaces, sidebars, and sticky header bars.
- **Surface Elevation** (`#18181B`) — Active nodes, inspect panels, and modal backdrops.
- **Crisp Primary Text** (`#F4F4F5`) — Zinc-100 high-legibility typographic display for labels and values.
- **Muted Steel** (`#71717A`) — Zinc-500 secondary metrics, crawl timestamps, and URL paths.
- **Whisper Border** (`#27272A` / `rgba(255, 255, 255, 0.08)`) — 1px structural dividing lines.
- **Signal Mint** (`#10B981`) — Single primary accent for primary CTAs, active crawl progress, and high-opportunity content gap scores (Saturation capped under 75%).
- **Semantic Tier Indicators (Muted, non-neon):**
  - Merge Tier: Subdued Sky (`#0284C7`)
  - Subheading Group Tier: Iris Steel (`#6366F1`)
  - Related Spoke Tier: Forest Mint (`#059669`)
  - Outlier / Low-Priority: Slate Neutral (`#64748B`)

*(Mandatory Constraint: The AI purple-neon and oversaturated cyan glows are strictly banned).*

---

## 3. Typography Rules
- **Display / Headlines:** `Geist` or `Cabinet Grotesk` — Track-tight (`letter-spacing: -0.025em`), controlled scale, hierarchy communicated through font-weight (`600` / `700`) and neutral contrast rather than bloated sizing.
- **Body & Controls:** `Geist` or `Satoshi` — Relaxed leading (`line-height: 1.5`), max 65 characters per line for content recommendations.
- **Data & Metrics (Mono):** `Geist Mono` or `JetBrains Mono` — Mandatory for all numerical statistics (Keyword Volume, CPC, SERP Rank, Silo Depth, Crawl Status codes, and URLs).
- **Explicit Font Bans:** `Inter` is banned. Generic system fonts (`Arial`, `Times New Roman`, `Georgia`) are banned. Serif fonts are strictly banned in all dashboard interfaces.

---

## 4. Component Stylings & Interaction

### Hub & Spoke Tree Clusters
- Radial or hierarchical tree graphs with 1px border connectors (`#27272A`).
- Nodes: Compact pills or rounded square tiles with mono badges indicating spoke count (`+14 spokes`) and tier status dots.
- Selection State: 1px border shift to Signal Mint (`#10B981`) with a subtle 2px offset ring, zero blurry outer shadow glows.

### Buttons & Controls
- Flat geometry with subtle 1px border contrast.
- Tactile feedback: `-1px` vertical translation (`transform: translateY(1px)`) on active/press.
- Primary CTA: Signal Mint fill with Obsidian text.
- Secondary Actions: Charcoal fill (`#18181B`) with 1px Whisper Border. No full-saturation color spam.

### Metrics & Data Tables
- Sticky column headers with muted uppercase mono tags (`font-size: 11px`, tracking `+0.05em`).
- Inline tool intent tags: Compact badge indicators (`TOOL` in amber, `INFO` in slate) with minimal padding (`py-0.5 px-1.5`).
- No heavy outer shadows on table cards; structure demarcated by border dividers.

### Loaders & Empty States
- **Crawl Progress:** Skeletal sweep shimmer matching exact table rows or graph node positions. No spinning circle loaders.
- **Empty States:** Structured wireframe blueprints showing a ghost sitemap tree with an actionable prompt to start the crawl.

---

## 5. Layout Principles & Workspace Geometry
- **Dual-Pane Workbench:** Left 65% interactive cluster map / sitemap tree; Right 35% sticky node inspector showing gap analysis, merged keywords, and H2/H3 recommendations.
- **Containment:** Main container capped at `1600px` for ultra-wide monitors, with high-density viewports defaulting to full-bleed edge-to-edge gutters (`px-4 sm:px-6`).
- **Responsive Collapse (< 768px):** Multi-column workbench stacks into tabbed navigation (`[ Tree View ] [ Gap Inspector ] [ Export ]`). Zero horizontal overflow.
- **Viewport Height:** Always use `min-h-[100dvh]` rather than `h-screen` to prevent mobile Safari navigation bar jumps.

---

## 6. Motion Philosophy
- **Physics Engine:** Spring physics (`stiffness: 120, damping: 22`) for expanding spoke groups and drawer toggles.
- **Perpetual Micro-Interactions:** Subtle crawling pulse on the active crawl radar indicator (`opacity: 0.8` to `1.0` gentle breathing cycle).
- **GPU Acceleration:** All layout transitions animate exclusively on `transform` and `opacity`. Never animate `top`, `left`, `width`, or `height`.

---

## 7. Anti-Patterns (Banned AI Tells)
- **NO** emojis anywhere in the interface or navigation.
- **NO** generic AI purple/violet gradient text or buttons.
- **NO** pure black (`#000000`) surfaces.
- **NO** neon drop shadows or fuzzy blur halos around cards.
- **NO** generic 3-equal-width card grids for feature presentations.
- **NO** filler copywriting clichés ("Elevate your SEO", "Unleash the power of AI", "Seamless sitemaps").
- **NO** fake round numbers (`99.9%`, `100k+`).
- **NO** circular progress spinner overlays.

---

## 8. Product Architecture & Navigation Taxonomy
When prompting Google Stitch for screens, always use the canonical **GapCrawl** product nomenclature:
- **Projects** (`/`): The workspace cockpit tracking active crawl jobs, sitemap health, and gap volume summaries.
- **Seed Finder** (`/gold-hunter`): Precision URL auditor that discovers high-value seed keywords and topic cores.
- **Gap Scan** (`/scan`): The competitor sitemap comparison engine that extracts missing search gaps.
- **Hub Spoke** (`/hub-spoke`): Visual topical authority map organizing hubs, silos, and tiered spoke clusters.
- **Build Page** (`/gap-page-prompts`): Single-page architectural blueprint generator for programmatic and custom gap pages.
- **Blog Writer** (`/write-blog`): Long-form editorial studio for generating targeted articles from keyword clusters.
- **Keyword Bank** (`/saved-keywords`): High-density repository of curated keyword opportunities ready for execution.

