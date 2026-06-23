# Technical Specification — Kumar Shailove Personal Portfolio Website

**Version:** 1.0  
**Stage:** 4 — Technical Specification  
**Date:** 2026-06-23  
**Prepared by:** ClaudeForge Spec Agent (Stage 4)  
**Project:** `projects/mywebsite`  
**Inputs:** `docs/research.md`, `docs/plan.md`, `docs/prd.md` + resolved open questions OQ1–OQ5

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack Decisions](#2-tech-stack-decisions)
3. [Data Models](#3-data-models)
4. [Component Breakdown](#4-component-breakdown)
5. [Integration Details](#5-integration-details)
6. [Non-Functional Implementation](#6-non-functional-implementation)
7. [Implementation Order](#7-implementation-order)
8. [File Structure](#8-file-structure)
9. [Open Technical Questions](#9-open-technical-questions)

---

## 1. Architecture Overview

### 1.1 Runtime Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        BROWSER                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Vite SPA (React 19 + TS)                │   │
│  │                                                      │   │
│  │  App.tsx                                             │   │
│  │  └── ReactLenis (lenis/react, autoRaf=false)         │   │
│  │       └── Motion frame.update() drives Lenis RAF    │   │
│  │            ├── NavigationBar                         │   │
│  │            ├── HeroSection                           │   │
│  │            │    └── NetworkCanvas (hand-rolled RAF)  │   │
│  │            ├── AboutSection                          │   │
│  │            ├── PhilosophySection                     │   │
│  │            │    └── PhilosophyCard × 3               │   │
│  │            ├── ExperienceSection                     │   │
│  │            │    └── TimelineItem × 8                 │   │
│  │            ├── HiverSection                          │   │
│  │            │    └── TransformationCard × 7           │   │
│  │            ├── ContactSection                        │   │
│  │            └── ChatbotWidget (fixed, z-50)           │   │
│  │                 └── <iframe> ──────────────────────────────────────┐
│  └─────────────────────────────────────────────────────┘   │          │
└─────────────────────────────────────────────────────────────┘          │
                                                                          │
          ┌───────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────┐
│   HuggingFace Spaces (CPU Basic)    │
│                                     │
│   Gradio ChatInterface              │
│   └── app.py                        │
│        ├── knowledge_base.md        │
│        │   (system prompt context)  │
│        └── Anthropic Python SDK     │
│             └── claude-sonnet-4-6   │
│                  (Anthropic API)    │
└─────────────────────────────────────┘
```

### 1.2 Vercel Deploy Pipeline

```
Developer Machine
│
├── git push → GitHub repo (main branch)
│                    │
│                    ▼
│             Vercel Build Hook
│                    │
│                    ▼
│          Vercel Build Server
│          ├── npm install
│          ├── npm run build   (Vite)
│          │    └── dist/
│          │         ├── index.html
│          │         ├── assets/
│          │         │    ├── index-[hash].js
│          │         │    ├── index-[hash].css
│          │         │    └── [other chunks]
│          │         └── images/
│          └── vercel.json → injects headers
│                    │
│                    ▼
│          Vercel Edge Network (CDN)
│          └── *.vercel.app  (HTTPS, HTTP→HTTPS redirect auto)
│
└── HuggingFace Space (separate deploy)
     ├── Drag-and-drop OR git push to HF Space repo
     ├── app.py + requirements.txt + knowledge_base.md
     └── ANTHROPIC_API_KEY set via HF Secrets UI (never committed)
```

---

## 2. Tech Stack Decisions

### 2.1 Framework — React 19 + TypeScript + Vite

| Attribute | Detail |
|---|---|
| **Choice** | React 19 + TypeScript 5.x + Vite 6.x (via `npm create vite@latest -- --template react-ts`) |
| **Alternatives considered** | Next.js 15 (SSR/SSG), Astro 4 (islands architecture), plain HTML/CSS/JS |
| **Rationale** | This is a static personal site with no server-side data requirements. Next.js SSR complexity is unnecessary overhead. Astro would work but adds a framework learning curve for zero benefit — no islands hydration needed for this use case. React 19 + Vite gives: the Motion v12 and Lenis ecosystem (designed for React), TypeScript strict mode for correctness guarantees, Vite's incremental HMR (critical when iterating on canvas), and a single `npm run build` that produces a static `dist/` deployable to any CDN. React 19 concurrent features (transitions, deferred values) are not used in V1 but are available for V2 optimizations. |
| **Version pin** | `react@19`, `react-dom@19`, `@vitejs/plugin-react@4.x`, `vite@6.x`, `typescript@5.x` |

### 2.2 CSS — Tailwind CSS v4

| Attribute | Detail |
|---|---|
| **Choice** | `@tailwindcss/vite` plugin with CSS-first `@theme {}` configuration |
| **Alternatives considered** | Tailwind v3 + PostCSS, CSS Modules, styled-components, vanilla CSS custom properties only |
| **Rationale** | Tailwind v4's Vite plugin eliminates the PostCSS config overhead of v3. The `@theme {}` block co-locates design tokens with the CSS import — the five `oklch()` color tokens, font stacks, and spacing scale live in `src/index.css` with no separate config file. Auto source detection removes the `content: [...]` array maintenance. `@container` queries are built-in for responsive `PhilosophyCard` layout. The `oklch()` color space is the correct choice for the amber-gold accent (`--color-accent: oklch(0.75 0.15 60)`) — it produces perceptually uniform shades when hovered/lightened, which `rgb()` cannot do cleanly. |
| **Version pin** | `@tailwindcss/vite@4.x` |

### 2.3 Animation — Motion v12

| Attribute | Detail |
|---|---|
| **Choice** | `motion` npm package v12, imported from `motion/react` |
| **Alternatives considered** | GSAP 3 (ScrollTrigger), vanilla CSS transitions, Anime.js, previous `framer-motion` package |
| **Rationale** | Motion v12 is the direct successor to `framer-motion` with a clean `motion/react` import path and no API-level breaking changes for standard usage patterns. It introduces `ScrollTimeline` hardware acceleration that offloads scroll-progress calculations to the compositor thread — critical for the hero canvas parallax on 120Hz displays. GSAP ScrollTrigger would require a separate scroll system conflicting with Lenis. The hybrid WAAPI+JS engine in Motion ensures 60fps on mid-range hardware without manual `will-change` hints. The `whileInView` + `viewport: { once: true }` pattern is the most ergonomic API for the section-reveal requirements. |
| **Version pin** | `motion@12.x` |
| **Import path** | `import { motion, AnimatePresence, useScroll, useTransform, useSpring, useInView, useAnimationFrame, frame, cancelFrame } from 'motion/react'` |

### 2.4 Smooth Scroll — Lenis 1.3+

| Attribute | Detail |
|---|---|
| **Choice** | `lenis` npm package 1.3.x with `ReactLenis` from `lenis/react`, `autoRaf: false` |
| **Alternatives considered** | `@studio-freight/lenis` (deprecated predecessor), Locomotive Scroll v4, native CSS `scroll-behavior: smooth` |
| **Rationale** | The `lenis` package (maintained by darkroom.engineering) supersedes the deprecated `@studio-freight/lenis`. Locomotive Scroll v4 relies on transforms that conflict with Motion's transform pipeline. Native `scroll-behavior: smooth` provides no lerp/inertia and cannot be driven by a JS animation frame. Lenis's `autoRaf: false` mode is the correct choice here: it delegates RAF control to Motion's `frame.update()` so both libraries share a single animation loop — eliminating the stutter visible when two independent RAF loops produce scroll-position and spring-calculation updates at different sub-frame offsets. |
| **Version pin** | `lenis@1.3.x` |
| **Options** | `lerp: 0.08`, `duration: 1.2`, `syncTouch: true` |

### 2.5 Canvas — Hand-Rolled

| Attribute | Detail |
|---|---|
| **Choice** | Hand-rolled `NetworkCanvas` TypeScript component using the HTML Canvas 2D API |
| **Alternatives considered** | tsParticles (`@tsparticles/react`), Three.js (WebGL), particles.js (unmaintained) |
| **Rationale** | tsParticles adds ~50KB to the gzip bundle and forces colors and behavior into a JSON config API — losing precise control over the amber glow and mouse repulsion feel that defines the design. Three.js is excessive for a 2D particle network and would push the bundle past the 500KB budget. Hand-rolling the canvas is ~120 lines of TypeScript and provides zero-overhead control: exact node colors (`rgba(255, 200, 100, 0.7)`), per-edge alpha (`rgba(255, 200, 100, alpha)`), `shadowBlur` only on nodes, precise velocity damping, and trivial mobile optimization (halve particle count, skip `shadowBlur`). The canvas component is a side-effect-only React component — it touches no state, produces no re-renders, and is safe to memo-ize away from the React reconciler. |

### 2.6 Fonts — Instrument Serif + Geist Mono

| Attribute | Detail |
|---|---|
| **Choice** | Instrument Serif via Google Fonts CDN `<link>` tags; Geist Mono via `@fontsource-variable/geist-mono` npm package |
| **Rationale** | Instrument Serif is served from Google Fonts CDN — the browser cache benefit from the CDN outweighs the self-hosting complexity for a public-facing portfolio. Geist Mono is available as a variable font via Fontsource, which means a single file covers all weights (400–700) with sub-pixel hinting — superior rendering at the small caption sizes used for role labels. The variable font adds ~40KB to the bundle as a woff2 (inlined into the CSS by Vite/Fontsource), which is acceptable within the 500KB budget. |
| **Instrument Serif weights** | Regular (400) + Italic (400 italic) only — no bold variant exists; size provides visual weight |
| **Geist Mono weights** | Variable font via `@fontsource-variable/geist-mono` — all weights in one file |

### 2.7 Chatbot Backend — Gradio + Claude API

| Attribute | Detail |
|---|---|
| **Choice** | Gradio `ChatInterface` (Python, `gradio>=4.0`) + Anthropic Python SDK + `claude-sonnet-4-6`, deployed on HuggingFace Spaces CPU Basic tier |
| **Alternatives considered** | FastAPI + custom React chat UI, Vercel AI SDK + Edge Functions, OpenAI Assistants API |
| **Rationale** | Gradio `ChatInterface` provides a production-ready chat UI with message history management, examples, and accessibility out of the box — implementing an equivalent custom React chat component would take 2–3 days with no user-facing quality gain. HuggingFace Spaces CPU Basic is free, has a public HTTPS URL, and handles Python process management. `claude-sonnet-4-6` is specified by the brief as the required model — it delivers nuanced, contextually aware answers to executive career questions at $3/$15 per 1M tokens, which is appropriate for portfolio-scale traffic. The knowledge-base-in-system-prompt pattern (4,000 tokens curated from the Executive Narrative) is the simplest correct architecture for grounded responses without hallucination. |
| **Model** | `claude-sonnet-4-6` (exact string in `app.py`) |
| **Response cap** | `max_tokens=1024` in API call; system prompt instructs ≤ 200 words unless detailed breakdown requested |

### 2.8 Chatbot Embedding — iframe

| Attribute | Detail |
|---|---|
| **Choice** | HTML `<iframe>` with deferred `src` injection on first FAB click |
| **Alternatives considered** | `@gradio/client` JS SDK (direct API calls), `<gradio-app>` Web Component |
| **Rationale** | The iframe approach sidesteps CORS entirely — the browser loads the Gradio UI in its own browsing context with its own cookies and script execution environment. The `@gradio/client` SDK approach requires CORS headers on the Space and a full custom chat UI implementation. The `<gradio-app>` Web Component requires a type assertion (`as any`) in React and loads the Gradio JS bundle (~200KB) from an external CDN — violating the "no external scripts" CSP. Deferred `src` injection (setting `iframe.src` only on FAB click, not on initial render) avoids waking the sleeping HuggingFace Space until the user explicitly requests it, maximizing both cold-start UX and API cost efficiency. |

### 2.9 Deployment — Vercel

| Attribute | Detail |
|---|---|
| **Choice** | Vercel static site deployment, `*.vercel.app` domain, `vercel.json` for CSP headers |
| **Alternatives considered** | Netlify, GitHub Pages, Cloudflare Pages |
| **Rationale** | Vercel's `vercel.json` `headers` block is the most ergonomic way to inject the `Content-Security-Policy: frame-src https://*.hf.space` header required for the chatbot iframe. Vercel's global CDN edge network delivers sub-100ms TTFB for static assets from most global locations without configuration. The `@vercel/vite-plugin` is a first-party integration. GitHub Pages has no custom header injection. Netlify `_headers` file is equivalent but Vercel's GitHub integration (auto-deploy on push to `main`) is marginally simpler for a solo developer. |

---

## 3. Data Models

All content is static TypeScript. No database, no API calls for content. Every content module exports a typed constant consumed by its corresponding section component.

### 3.1 `HeroContent`

```typescript
// src/content/hero.ts
export interface HeroContent {
  name: string;                  // "Kumar Shailove"
  headline: string;              // "I build engineering organizations that compound business value."
  tagline: string;               // "Engineering Organizations. Engineering Leaders. Engineering the Future."
  ctaLabel: string;              // "Explore My Work"
  ctaHref: string;               // "#about"
}

export const heroContent: HeroContent = { ... }
```

### 3.2 `AboutContent`

```typescript
// src/content/about.ts
export interface AboutContent {
  paragraphs: string[];          // Min 2 elements. Each is a full prose paragraph.
  photoSrc: string;              // "/images/profile.jpg" — may 404; component handles gracefully
  photoAlt: string;              // "Kumar Shailove"
  photoPlaceholderInitials: string; // "KS" — shown if image 404s
}

export const aboutContent: AboutContent = { ... }
```

### 3.3 `PhilosophyPillar`

```typescript
// src/content/philosophy.ts
export interface PhilosophyPillar {
  id: string;                    // "leadership" | "technology" | "ai"
  title: string;                 // "Leadership" | "Technology" | "AI"
  body: string;                  // Descriptive paragraph (2–4 sentences)
  pullQuote: string;             // Short quote (1–2 sentences, styled distinctly)
}

export const philosophyPillars: PhilosophyPillar[] = [
  { id: 'leadership', title: 'Leadership', body: '...', pullQuote: '...' },
  { id: 'technology', title: 'Technology', body: '...', pullQuote: '...' },
  { id: 'ai',         title: 'AI',         body: '...', pullQuote: '...' },
]
```

### 3.4 `ExperienceRole`

```typescript
// src/content/timeline.ts
export interface ExperienceRole {
  id: string;                    // Slug, e.g. "hiver-cpo"
  company: string;               // "Hiver"
  title: string;                 // "Chief Product Officer"
  startYear: number;             // 2018
  endYear: number | 'Present';   // 2024 | 'Present'
  description: string;           // 1–2 sentences of context
  isHighlighted?: boolean;       // true for Hiver (links to Hiver section)
}

// Exactly 8 entries, ordered newest-first
export const experienceRoles: ExperienceRole[] = [ ... ]
```

### 3.5 `HiverTransformation`

```typescript
// src/content/hiver.ts
export interface HiverTransformation {
  id: string;                    // "t1" through "t7"
  title: string;                 // Short transformation title (3–6 words)
  detail: string;                // 1–3 sentences with at least one quantified metric for t1, t2, t3
}

// Exactly 7 entries
export const hiverTransformations: HiverTransformation[] = [ ... ]
```

### 3.6 `ContactContent`

```typescript
// src/content/contact.ts
export interface ContactContent {
  invitationText: string;        // "Let's build something together."
  email: string;                 // "kumar@example.com" — real address populated by Kumar
  emailLabel: string;            // Display label, e.g. "Email Kumar"
  linkedinUrl: string;           // "https://linkedin.com/in/kumar-shailove"
  linkedinLabel: string;         // "LinkedIn Profile"
}

export const contactContent: ContactContent = { ... }
```

### 3.7 `NavItem`

```typescript
// src/content/nav.ts
export interface NavItem {
  label: string;                 // "About" | "Philosophy" | "Experience" | "Hiver" | "Contact"
  href: string;                  // "#about" | "#philosophy" | "#experience" | "#hiver" | "#contact"
}

// Exactly 5 items — hero is implicit (logo/name scrolls to top)
export const navItems: NavItem[] = [
  { label: 'About',       href: '#about' },
  { label: 'Philosophy',  href: '#philosophy' },
  { label: 'Experience',  href: '#experience' },
  { label: 'Hiver',       href: '#hiver' },
  { label: 'Contact',     href: '#contact' },
]
```

---

## 4. Component Breakdown

### 4.1 `App.tsx` — Root Component

**Purpose:** Application root. Wires Lenis to Motion's RAF loop. Renders the `ReactLenis` provider wrapping all sections and the `ChatbotWidget`.

**Props:** None (root component, no props).

**Key logic:**
- Holds `lenisRef` of type `React.RefObject<LenisRef>` (from `lenis/react`)
- In `useEffect`, calls `frame.update(update, true)` where `update = (data: { timestamp: number }) => lenisRef.current?.lenis?.raf(data.timestamp)`. Returns `() => cancelFrame(update)` as cleanup.
- `ReactLenis` receives `ref={lenisRef}` and `autoRaf={false}`
- Renders sections in DOM order: `NavigationBar`, `HeroSection`, `AboutSection`, `PhilosophySection`, `ExperienceSection`, `HiverSection`, `ContactSection`, `ChatbotWidget`

```typescript
// Full signature
export default function App(): JSX.Element
```

**Dependencies:** `lenis/react` (`ReactLenis`, `LenisRef`), `motion/react` (`frame`, `cancelFrame`)

---

### 4.2 `NavigationBar`

**Purpose:** Fixed navigation bar. Hidden on hero load, fades in after `scrollY > window.innerHeight * 0.8`. Highlights the active section via scroll-spy. Renders 5 nav links.

**Props:**
```typescript
interface NavigationBarProps {
  // No external props — reads scroll position internally via useLenis
}
```

**Key logic:**
1. `const [visible, setVisible] = useState(false)` — controls opacity/transform
2. `const [activeSection, setActiveSection] = useState<string>('')` — tracks current section `id`
3. `useLenis(({ scroll }) => { ... })` subscription:
   - `setVisible(scroll > window.innerHeight * 0.8)`
   - Queries each section's `getBoundingClientRect()` to determine which section occupies the viewport center; sets `activeSection` to that section's `id`
4. `motion.nav` with `animate={{ opacity: visible ? 1 : 0, y: visible ? 0 : -100 }}` and `transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}`
5. Each `<a>` receives `className` containing `text-[var(--color-accent)]` when `activeSection === item.href.slice(1)`
6. Click handlers call `lenis.scrollTo(sectionEl, { offset: -80 })` for smooth nav scroll; falls back to `document.querySelector(href).scrollIntoView()` if lenis unavailable

**DOM output:**
```html
<nav aria-label="Main navigation" class="fixed top-0 left-0 right-0 z-40 ...">
  <a href="#about">About</a>
  <!-- 4 more items -->
</nav>
```

**Dependencies:** `useLenis` (custom hook), `motion/react`, `src/content/nav.ts`

---

### 4.3 `HeroSection`

**Purpose:** Full-viewport (`min-h-screen`) opening section. Renders `NetworkCanvas` as background. Animates name, headline, tagline, and CTA on mount with staggered delays.

**Props:**
```typescript
interface HeroSectionProps {
  // No external props — reads from heroContent directly
}
```

**Key logic:**
1. `const { scrollY } = useScroll()` from `motion/react`
2. `const canvasY = useTransform(scrollY, [0, 600], [0, -180])` — parallax at 0.3× scroll speed
3. `const prefersReducedMotion = useReducedMotion()` — from `motion/react`
4. If `prefersReducedMotion`, all motion elements initialize at final state (no `initial` prop set, or `initial` equals `animate`)
5. Stagger sequence for hero text (using `motion.div` with `initial={{ opacity: 0, y: 30 }}`, `animate={{ opacity: 1, y: 0 }}`):
   - Name: `transition={{ delay: 0 }}`
   - Headline: `transition={{ delay: 0.15 }}`
   - CTA: `transition={{ delay: 0.3 }}`
6. CTA `<a href="#about">` triggers Lenis smooth scroll via `useLenis` or direct `lenis.scrollTo('#about')`
7. `section` element has `id="hero"`

**Section element structure:**
```
<section id="hero" className="relative min-h-screen overflow-hidden bg-[var(--color-bg)]">
  <motion.div style={{ y: canvasY }} className="absolute inset-0">
    <NetworkCanvas />
  </motion.div>
  <div className="relative z-10 flex flex-col justify-center min-h-screen px-8 max-w-7xl mx-auto">
    <!-- name, headline, tagline, CTA -->
  </div>
</section>
```

**Dependencies:** `NetworkCanvas`, `motion/react`, `src/content/hero.ts`

---

### 4.4 `NetworkCanvas`

**Purpose:** HTML Canvas 2D particle network animation. Positioned `absolute inset-0` behind hero text. Hand-rolled RAF loop. Mouse repulsion. Mobile-adaptive particle count.

**Props:**
```typescript
interface NetworkCanvasProps {
  // No props — all configuration via module-level constants
}
```

**Module-level constants (at top of file, not in component body):**
```typescript
const PARTICLE_COUNT_DESKTOP = 70
const PARTICLE_COUNT_MOBILE = 35
const MAX_DISTANCE = 140
const NODE_COLOR = 'rgba(255, 200, 100, 0.7)'
const EDGE_COLOR_PREFIX = 'rgba(255, 200, 100, '   // alpha value appended: EDGE_COLOR_PREFIX + alpha + ')'
const GLOW_COLOR = 'rgba(255, 180, 80, 0.4)'
const GLOW_BLUR = 8                                 // shadowBlur value (desktop only)
const VELOCITY_BASE = 0.4                           // max starting speed component
const VELOCITY_DAMPING = 0.99                       // per-frame damping multiplier
const MOUSE_REPULSION_RADIUS = 100
const MOUSE_REPULSION_FORCE = 0.3
```

**Internal types:**
```typescript
interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
}
```

**Key logic:**
1. `const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches` — checked **before** `requestAnimationFrame`; if true, renders static dark background via `ctx.fillRect` and returns immediately (no RAF started)
2. `const isMobile = window.innerWidth < 768 || navigator.maxTouchPoints > 0`
3. `const count = isMobile ? PARTICLE_COUNT_MOBILE : PARTICLE_COUNT_DESKTOP`
4. `const disableShadow = isMobile`
5. `useRef<number>(0)` for `rafRef` — stores the RAF handle for cleanup
6. `useRef<{ x: number; y: number }>({ x: -9999, y: -9999 })` for `mouseRef`
7. `useEffect` cleanup: `cancelAnimationFrame(rafRef.current)` + `window.removeEventListener('resize', init)` + `canvas.removeEventListener('mousemove', onMouse)`
8. Canvas `pointer-events: none` via Tailwind class `pointer-events-none`

**Rendered element:**
```typescript
return (
  <canvas
    ref={canvasRef}
    className="absolute inset-0 w-full h-full pointer-events-none"
    aria-hidden="true"
  />
)
```

**Dependencies:** `react` (`useEffect`, `useRef`) — zero external dependencies.

---

### 4.5 `AboutSection`

**Purpose:** Renders career narrative prose and profile photo with graceful placeholder fallback.

**Props:**
```typescript
interface AboutSectionProps {
  // No external props — reads from aboutContent directly
}
```

**Key logic:**
1. `const [imgError, setImgError] = useState(false)` — tracks photo load failure
2. `<img onError={() => setImgError(true)} src={aboutContent.photoSrc} alt={aboutContent.photoAlt} />` — if `imgError`, renders a `<div>` with initials instead
3. `motion.section` with `id="about"`, `initial={{ opacity: 0, y: 40 }}`, `whileInView={{ opacity: 1, y: 0 }}`, `viewport={{ once: true, margin: '-100px' }}`, `transition={{ duration: 0.7, ease: [0.25, 0.46, 0.45, 0.94] }}`
4. Paragraphs rendered from `aboutContent.paragraphs.map((p, i) => <p key={i}>{p}</p>)`

**Dependencies:** `motion/react`, `src/content/about.ts`

---

### 4.6 `PhilosophySection`

**Purpose:** Section wrapper for the three philosophy pillars. Renders `PhilosophyCard` components with stagger animation.

**Props:**
```typescript
interface PhilosophySectionProps {
  // No external props
}
```

**Key logic:**
1. `motion.section` with `id="philosophy"`, section-level `whileInView` reveal (same transition as `AboutSection`)
2. `motion.div` container with `variants={containerVariants}` for stagger:
   ```typescript
   const containerVariants = {
     hidden: { opacity: 0 },
     show: {
       opacity: 1,
       transition: { staggerChildren: 0.12 },
     },
   }
   ```
3. `whileInView="show"`, `initial="hidden"`, `viewport={{ once: true, margin: '-100px' }}`

**Dependencies:** `PhilosophyCard`, `motion/react`, `src/content/philosophy.ts`

---

### 4.7 `PhilosophyCard`

**Purpose:** Renders a single philosophy pillar: title, body, pull-quote.

**Props:**
```typescript
interface PhilosophyCardProps {
  pillar: PhilosophyPillar       // { id, title, body, pullQuote }
}
```

**Key logic:**
1. `motion.div` child with `variants`:
   ```typescript
   const itemVariants = {
     hidden: { opacity: 0, y: 20 },
     show:   { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.25, 0.46, 0.45, 0.94] } },
   }
   ```
2. Pull-quote styled as: `font-serif italic text-2xl text-[var(--color-accent)] border-l-2 border-[var(--color-accent)] pl-4`
3. Card background: `bg-[var(--color-surface)] rounded-2xl p-8`

**Dependencies:** `motion/react`, `PhilosophyPillar` type from `src/content/philosophy.ts`

---

### 4.8 `ExperienceSection`

**Purpose:** Section wrapper for the 8-role career timeline. Renders `TimelineItem` components with stagger animation.

**Props:**
```typescript
interface ExperienceSectionProps {
  // No external props
}
```

**Key logic:**
1. `motion.section` with `id="experience"` and `whileInView` reveal
2. `motion.ol` container with `staggerChildren: 0.12`
3. Visual timeline line: `<div className="absolute left-4 top-0 bottom-0 w-px bg-[var(--color-muted)]/30" />`  — positioned alongside the list via `relative` parent

**Dependencies:** `TimelineItem`, `motion/react`, `src/content/timeline.ts`

---

### 4.9 `TimelineItem`

**Purpose:** Renders a single career role entry with company, title, date range, and description.

**Props:**
```typescript
interface TimelineItemProps {
  role: ExperienceRole           // { id, company, title, startYear, endYear, description, isHighlighted }
  index: number                  // Used for aria-label / key
}
```

**Key logic:**
1. `motion.li` with `variants` (same `itemVariants` pattern as `PhilosophyCard`)
2. Timeline dot: `<span className="absolute -left-1.5 top-2 w-3 h-3 rounded-full bg-[var(--color-accent)]" />`
3. Date range rendered as: `${role.startYear} – ${role.endYear === 'Present' ? 'Present' : role.endYear}`
4. If `role.isHighlighted`, wraps company name in an `<a href="#hiver">` internal link

**Dependencies:** `motion/react`, `ExperienceRole` type from `src/content/timeline.ts`

---

### 4.10 `HiverSection`

**Purpose:** Section wrapper for the 7 Hiver transformations. Section heading contains "Hiver" and "Case Study".

**Props:**
```typescript
interface HiverSectionProps {
  // No external props
}
```

**Key logic:**
1. `motion.section` with `id="hiver"` and `whileInView` reveal
2. `motion.div` grid container with `staggerChildren: 0.12`
3. Grid layout: `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6`

**Dependencies:** `TransformationCard`, `motion/react`, `src/content/hiver.ts`

---

### 4.11 `TransformationCard`

**Purpose:** Renders a single Hiver transformation item.

**Props:**
```typescript
interface TransformationCardProps {
  transformation: HiverTransformation   // { id, title, detail }
  index: number                         // 1-based index for visual numbering
}
```

**Key logic:**
1. `motion.div` child with `variants` (same `itemVariants` as above)
2. Index displayed as: `<span className="font-mono text-[var(--color-accent)] text-sm">0{index}</span>`
3. Card background: `bg-[var(--color-surface)] rounded-2xl p-6 border border-white/5`
4. Title in `font-serif text-xl`; detail in `text-[var(--color-muted)] text-sm leading-relaxed`

**Dependencies:** `motion/react`, `HiverTransformation` type from `src/content/hiver.ts`

---

### 4.12 `ContactSection`

**Purpose:** Final section with invitation text, `mailto:` link, and LinkedIn external link.

**Props:**
```typescript
interface ContactSectionProps {
  // No external props
}
```

**Key logic:**
1. `motion.section` with `id="contact"` and `whileInView` reveal
2. `mailto:` link: `<a href={`mailto:${contactContent.email}`}>{contactContent.emailLabel}</a>`
3. LinkedIn link: `<a href={contactContent.linkedinUrl} target="_blank" rel="noopener noreferrer">{contactContent.linkedinLabel}</a>`
4. No `<form>` element anywhere in this section

**Dependencies:** `motion/react`, `src/content/contact.ts`

---

### 4.13 `ChatbotWidget`

**Purpose:** Fixed-position FAB in bottom-right corner. Opens/closes an animated panel containing the HuggingFace Space iframe. Defers iframe `src` injection until first open. Shows loading skeleton until iframe reports load.

**Props:**
```typescript
interface ChatbotWidgetProps {
  spaceUrl: string               // "https://kumarshailove-portfolio-chat.hf.space"
}
```

**Key logic:**
1. `const [open, setOpen] = useState(false)`
2. `const [iframeSrc, setIframeSrc] = useState<string | null>(null)` — deferred src
3. `const [iframeLoaded, setIframeLoaded] = useState(false)`
4. `const [isExpanded, setIsExpanded] = useState(false)` — `aria-expanded` state
5. When `open` transitions from `false` to `true` for the first time: `setIframeSrc(spaceUrl)` (only fires once — guarded by `iframeSrc === null` check)
6. `<AnimatePresence>` wraps the panel `motion.div`
7. Panel animation: `initial={{ opacity: 0, scale: 0.9, y: 20 }}`, `animate={{ opacity: 1, scale: 1, y: 0 }}`, `exit={{ opacity: 0, scale: 0.9, y: 20 }}`, `transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}`
8. Loading skeleton: shown when `open && !iframeLoaded`. Contains "Waking up AI assistant (~15s)…" text and an animated `motion.div` placeholder bar.
9. `<iframe>` receives `onLoad={() => setIframeLoaded(true)}`. Dimensions: `width="400" height="520"` (desktop); on viewport `< 640px`: `width="calc(100vw - 48px)" height="480"`.
10. FAB button: `aria-label="Open chat"`, `aria-expanded={isExpanded}`, toggled on click
11. FAB accessible via keyboard: it is a `<button>` (natively focusable, activatable with Enter/Space)

**Panel header:**
```html
<div class="flex items-center justify-between px-4 py-3 bg-[var(--color-surface)] border-b border-white/10">
  <span class="font-mono text-sm text-[var(--color-text)]">Ask about Kumar</span>
  <button aria-label="Close chat" onClick={...}>✕</button>
</div>
```

**Dependencies:** `motion/react` (`AnimatePresence`, `motion`), React `useState`

---

### 4.14 `useLenis` Hook

**Purpose:** Subscribe to Lenis scroll events. Returns the current Lenis instance and calls `callback` on every scroll tick.

**Signature:**
```typescript
import { useLenis as useLenisBase, type LenisOptions } from 'lenis/react'

// Re-export the official useLenis hook directly — do not hand-roll.
// The official hook from lenis/react is the correct implementation.
export { useLenis } from 'lenis/react'
```

**Usage pattern in `NavigationBar`:**
```typescript
import { useLenis } from 'lenis/react'

// Inside component:
useLenis(({ scroll, progress, velocity }) => {
  setVisible(scroll > window.innerHeight * 0.8)
  // scroll-spy logic here
})
```

**Note:** `useLenis` from `lenis/react` is the official hook. No custom implementation is needed. This spec documents it explicitly to confirm the import path and usage pattern for the implementer.

---

### 4.15 `useScrollAnimation` Hook

**Purpose:** Encapsulates the common `whileInView` reveal animation pattern into a reusable hook that also respects `prefers-reduced-motion`.

**Signature:**
```typescript
// src/hooks/useScrollAnimation.ts
import { useReducedMotion } from 'motion/react'

interface ScrollAnimationOptions {
  delay?: number          // default: 0
  duration?: number       // default: 0.7
  y?: number              // initial y offset, default: 40
}

interface ScrollAnimationResult {
  initial: { opacity: number; y: number }
  whileInView: { opacity: number; y: number }
  viewport: { once: boolean; margin: string }
  transition: { duration: number; delay: number; ease: number[] }
}

export function useScrollAnimation(options?: ScrollAnimationOptions): ScrollAnimationResult {
  const prefersReducedMotion = useReducedMotion()
  const { delay = 0, duration = 0.7, y = 40 } = options ?? {}

  if (prefersReducedMotion) {
    return {
      initial:     { opacity: 1, y: 0 },
      whileInView: { opacity: 1, y: 0 },
      viewport:    { once: true, margin: '-100px' },
      transition:  { duration: 0, delay: 0, ease: [0, 0, 1, 1] },
    }
  }

  return {
    initial:     { opacity: 0, y },
    whileInView: { opacity: 1, y: 0 },
    viewport:    { once: true, margin: '-100px' },
    transition:  { duration, delay, ease: [0.25, 0.46, 0.45, 0.94] },
  }
}
```

**Usage in any section component:**
```typescript
const anim = useScrollAnimation()
return <motion.section {...anim}>...</motion.section>
```

---

## 5. Integration Details

### 5.1 HuggingFace Spaces

**Space URL format:**
```
https://<hf-username>-<space-slug>.hf.space
```
Example: `https://kumarshailove-portfolio-chat.hf.space`

The HF username and space slug are chosen by Kumar when creating the Space. The resulting URL is then hardcoded as the `spaceUrl` prop passed to `ChatbotWidget` in `App.tsx`.

**ANTHROPIC_API_KEY setup:**
1. Create the HuggingFace Space (SDK: Gradio, visibility: Public)
2. Navigate to Space Settings → Secrets
3. Add secret: Name = `ANTHROPIC_API_KEY`, Value = the Anthropic API key
4. The key is accessed in `app.py` via `os.environ["ANTHROPIC_API_KEY"]`
5. The key **must never appear** in `app.py`, `requirements.txt`, or any committed file

**Space file structure:**
```
projects/mywebsite/chatbot/
├── app.py                 # Gradio ChatInterface + Anthropic SDK
├── requirements.txt       # gradio>=4.0, anthropic>=0.40.0
└── knowledge_base.md      # ~4,000 token curated knowledge base
```

### 5.2 Gradio `ChatInterface` Configuration

```python
# app.py — exact configuration
demo = gr.ChatInterface(
    fn=chat,
    title="Ask about Kumar",
    description="I'm Kumar's AI assistant. Ask me anything about his background, philosophy, or experience.",
    theme=gr.themes.Soft(),
    type="messages",          # REQUIRED: use OpenAI-style message dicts, not deprecated tuples
    examples=[
        "What did Kumar accomplish at Hiver?",
        "What is Kumar's leadership philosophy?",
        "Tell me about Kumar's 20-year career.",
    ],
    cache_examples=False,     # Do not cache — each run hits the API
)
```

**`type="messages"` is mandatory.** The deprecated `tuples` format (default in Gradio <4.x) passes history as `list[tuple[str, str]]`; the `messages` format passes `list[dict]` matching the Anthropic SDK's expected structure directly.

**`knowledge_base.md` scope (~4,000 tokens):** The file contains these curated sections from the Executive Narrative:
1. Hero statement (the one-paragraph "who I am" summary)
2. Career arc narrative (paragraph form, 2004–present)
3. Three philosophy pillars (each ~150 words)
4. Seven Hiver transformations (each ~100 words with metrics)
5. Eight-role timeline (company, title, years, one-liner each)
6. "Why hire Kumar" closing summary (~200 words)

Total approximate token count: 3,800–4,200 tokens. This fits within a Claude context with room for a multi-turn conversation.

**System prompt pattern in `app.py`:**
```python
SYSTEM_PROMPT = f"""You are Kumar Shailove's personal AI assistant embedded on his portfolio website.
Answer questions about Kumar's career, philosophy, achievements, and experience.
Be professional, confident, and concise. Speak about Kumar in third person (e.g., "Kumar led...").
Do not make up information not present in the knowledge base.
Keep responses to 200 words or fewer unless the visitor explicitly requests a detailed breakdown.

KNOWLEDGE BASE:
{KNOWLEDGE_BASE}
"""
```

### 5.3 Vercel Deployment Configuration

**`vercel.json`** (placed at `projects/mywebsite/code/vercel.json`):
```json
{
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "Content-Security-Policy",
          "value": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; frame-src https://*.hf.space; img-src 'self' data:; connect-src 'self'"
        },
        {
          "key": "X-Frame-Options",
          "value": "SAMEORIGIN"
        },
        {
          "key": "X-Content-Type-Options",
          "value": "nosniff"
        }
      ]
    }
  ]
}
```

**`frame-src https://*.hf.space`** is the critical directive that allows the HuggingFace iframe to load. Without it the browser's CSP will block the iframe and the chatbot will silently fail.

**Build output directory:** Vite defaults to `dist/`. Vercel auto-detects Vite projects and uses `dist/` without configuration. No `"buildCommand"` or `"outputDirectory"` override is needed in `vercel.json`.

### 5.4 Google Fonts — Instrument Serif

Place these tags in `projects/mywebsite/code/index.html` inside the `<head>`, **before** any stylesheet:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
```

The `ital@0;1` parameter loads both the regular (0) and italic (1) cuts in a single request. `display=swap` prevents invisible text during font load — content renders in the fallback serif until Instrument Serif resolves.

### 5.5 Geist Mono — npm

```bash
npm install @fontsource-variable/geist-mono
```

In `projects/mywebsite/code/src/main.tsx`:
```typescript
import '@fontsource-variable/geist-mono'
```

This single import loads the variable font file (all weights 400–700 in one woff2). Vite inlines it as a hashed asset in the build.

In `src/index.css` `@theme {}` block:
```css
@theme {
  --font-mono: "Geist Mono Variable", ui-monospace, "Courier New", monospace;
}
```

Note: `@fontsource-variable` packages register the font under the name `"Geist Mono Variable"` (with "Variable" suffix). Use this exact string.

---

## 6. Non-Functional Implementation

### 6.1 Lenis + Motion RAF Coordination — Full Code

This is the most critical wiring in the application. It must be implemented in `App.tsx` exactly as follows:

```typescript
// src/App.tsx
import { useEffect, useRef } from 'react'
import { ReactLenis, type LenisRef } from 'lenis/react'
import { frame, cancelFrame } from 'motion/react'

export default function App() {
  const lenisRef = useRef<LenisRef>(null)

  useEffect(() => {
    function update(data: { timestamp: number }) {
      lenisRef.current?.lenis?.raf(data.timestamp)
    }

    // frame.update(callback, keepAlive)
    // keepAlive=true means Motion will keep calling this even when
    // no animations are running — necessary for Lenis to remain active
    frame.update(update, true)

    return () => cancelFrame(update)
  }, [])

  return (
    <ReactLenis
      ref={lenisRef}
      root
      autoRaf={false}              // MUST be false — prevents Lenis from starting its own RAF
      options={{
        lerp: 0.08,
        duration: 1.2,
        syncTouch: true,           // Apply lerp on touch devices too
      }}
    >
      {/* app content */}
    </ReactLenis>
  )
}
```

**Why this matters:** If `autoRaf` is not set to `false`, Lenis starts its own `requestAnimationFrame` loop. Motion also runs its own RAF. On a 60fps display, both loops run ~16.7ms apart. Scroll position updates from Lenis and spring calculations from Motion land on different frames, producing visible micro-stuttering on scroll-linked animations (canvas parallax, sticky nav opacity). The `frame.update()` pattern ensures both systems advance on the same frame.

**React Strict Mode note:** In development, React 18/19 Strict Mode double-invokes effects. The `ReactLenis` package handles this correctly internally. The `frame.update()` / `cancelFrame()` pattern is idempotent — `cancelFrame` accepts the same function reference and removes it cleanly on the first cleanup, so the second invocation starts fresh without a dangling subscription.

### 6.2 `prefers-reduced-motion` — Detection Pattern and Fallback

**In React components (Motion-managed animations):**
```typescript
import { useReducedMotion } from 'motion/react'

// Inside any component:
const prefersReducedMotion = useReducedMotion()
```

`useReducedMotion()` returns `true` when `prefers-reduced-motion: reduce` matches. Use it in `useScrollAnimation` (Section 4.15) to return `initial: { opacity: 1, y: 0 }` — elements render at their final state with no animation.

**In `NetworkCanvas` (vanilla JS, outside React render):**
```typescript
// Inside useEffect, BEFORE starting the RAF loop:
const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
if (motionQuery.matches) {
  // Render static background — single fillRect, then return
  ctx.fillStyle = 'oklch(0.08 0 0)'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  return  // Do NOT call requestAnimationFrame
}
// ... rest of animation setup
```

**Lenis reduced-motion fallback:**
```typescript
// In App.tsx, modify the ReactLenis options:
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

<ReactLenis
  ref={lenisRef}
  root
  autoRaf={false}
  options={{
    lerp: prefersReducedMotion ? 1 : 0.08,    // lerp=1 = instant, native-feeling scroll
    duration: prefersReducedMotion ? 0 : 1.2,
    syncTouch: true,
  }}
>
```

With `lerp: 1`, Lenis passes scroll events through at native speed with no inertia — effectively disabling smooth scrolling while keeping the Lenis infrastructure in place (so `useLenis` subscriptions still work).

### 6.3 Canvas HMR Cleanup

Vite's Hot Module Replacement re-runs `useEffect` on every save. Without cleanup, each hot reload:
1. Starts a new `requestAnimationFrame` loop
2. Attaches a new `mousemove` listener
3. Attaches a new `resize` listener

After 5 saves, there are 5 concurrent RAF loops and 5 `mousemove` listeners — visible as erratic particle movement and degraded performance.

The cleanup function in `useEffect` **must** do all three:
```typescript
return () => {
  cancelAnimationFrame(rafRef.current)           // Stop RAF loop
  window.removeEventListener('resize', init)     // Remove resize handler
  canvas.removeEventListener('mousemove', onMouse) // Remove mouse handler
}
```

`rafRef.current` is set to the return value of every `requestAnimationFrame(loop)` call within `loop` itself:
```typescript
const loop = () => {
  update()
  draw()
  rafRef.current = requestAnimationFrame(loop)  // Update handle on every frame
}
rafRef.current = requestAnimationFrame(loop)    // Set initial handle
```

This ensures the most recent RAF handle is always available for cancellation.

### 6.4 Mobile Canvas Adaptation

```typescript
// Inside NetworkCanvas useEffect, before init():
const isMobile = window.innerWidth < 768 || navigator.maxTouchPoints > 0
const PARTICLE_COUNT = isMobile ? PARTICLE_COUNT_MOBILE : PARTICLE_COUNT_DESKTOP
// PARTICLE_COUNT_DESKTOP = 70, PARTICLE_COUNT_MOBILE = 35

// In the draw() function, wrap shadowBlur in a condition:
if (!isMobile) {
  ctx.shadowBlur = GLOW_BLUR
  ctx.shadowColor = GLOW_COLOR
}
ctx.fill()
if (!isMobile) {
  ctx.shadowBlur = 0
}
```

`shadowBlur` is computed on the CPU by many mobile GPU drivers (not hardware-accelerated). At 70 particles × 60fps, that is 4,200 blurred circles per second — enough to cause sustained jank on mid-range Android. Disabling it on mobile reduces draw call cost by ~60% and is visually indistinguishable at the small particle sizes used.

The `isMobile` detection is computed once at `useEffect` init time, not per-frame. If the user rotates their device, the canvas `resize` handler calls `init()` which recomputes particle count — but `isMobile` is captured in closure from the initial detection. This is acceptable for V1 (a user mid-session is unlikely to switch from desktop to mobile). V2 can add a `ResizeObserver` to re-run the full init on breakpoint change.

### 6.5 Chatbot Deferred iframe `src` Injection

The pattern prevents the HuggingFace Space from waking (and billing API time) until the user explicitly opens the widget:

```typescript
// ChatbotWidget.tsx
const [iframeSrc, setIframeSrc] = useState<string | null>(null)
const [iframeLoaded, setIframeLoaded] = useState(false)

const handleOpen = () => {
  setOpen(true)
  setIsExpanded(true)
  // Only inject src the FIRST time the widget opens
  if (iframeSrc === null) {
    setIframeSrc(props.spaceUrl)
  }
}

// In JSX:
<iframe
  src={iframeSrc ?? undefined}    // undefined src = no HTTP request made
  onLoad={() => setIframeLoaded(true)}
  title="Chat with Kumar's AI assistant"
  width="400"
  height="520"
  className={iframeLoaded ? 'opacity-100' : 'opacity-0'}
  style={{ border: 'none' }}
/>

{/* Loading skeleton — shown while !iframeLoaded */}
{open && !iframeLoaded && (
  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[var(--color-surface)]">
    <motion.div
      className="w-8 h-8 rounded-full border-2 border-[var(--color-accent)] border-t-transparent"
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
    />
    <p className="font-mono text-sm text-[var(--color-muted)] text-center px-4">
      Waking up AI assistant<br />(~15s on first load)
    </p>
  </div>
)}
```

The `opacity-0` / `opacity-100` CSS class toggle on the iframe hides the Gradio loading screen while the custom skeleton is shown — preventing a flash of the Gradio "Loading..." state before the skeleton appears.

---

## 7. Implementation Order

### Milestone 1 — Foundation + Hero (M1)

**Goal:** Running Vite dev server with correct tooling wired, hero section visible, canvas animating, smooth scroll working.

1. **M1-S1: Project scaffold + tooling**
   - `npm create vite@latest code -- --template react-ts`
   - Install: `motion`, `lenis`, `@tailwindcss/vite`, `@fontsource-variable/geist-mono`
   - Configure `vite.config.ts` with `react()` and `tailwindcss()` plugins
   - Set up `src/index.css` with `@import "tailwindcss"` and full `@theme {}` block (all 5 color tokens + font stacks)
   - Add Google Fonts `<link>` tags to `index.html`
   - Add Geist Mono import to `main.tsx`
   - Verify: `npm run dev` starts without errors; Tailwind classes apply; fonts render

2. **M1-S2: Lenis + Motion RAF wiring** ← _do this before any animation code_
   - Implement `App.tsx` with `lenisRef`, `frame.update()`, `cancelFrame()` pattern (full code in Section 6.1)
   - Verify: no console errors; scroll produces inertia; no double-RAF log warnings

3. **M1-S3: Content modules**
   - Create `src/content/hero.ts`, `src/content/nav.ts` with placeholder strings
   - Create remaining content files with `TODO` stubs: `about.ts`, `philosophy.ts`, `timeline.ts`, `hiver.ts`, `contact.ts`

4. **M1-S4: `NetworkCanvas` component**
   - Implement with full RAF cleanup, mouse repulsion, mobile adaptation, `prefers-reduced-motion` guard
   - Verify: canvas animates in HeroSection; no memory leak on HMR; mobile particle count correct at 375px viewport

5. **M1-S5: `HeroSection`**
   - Implement stagger entry animation (name → headline → CTA with 0s, 0.15s, 0.3s delays)
   - Implement canvas parallax (`useTransform(scrollY, [0, 600], [0, -180])`)
   - Verify: hero renders at 100vh; CTA scrolls to `#about`; canvas is behind text

6. **M1-S6: `NavigationBar`**
   - Implement scroll-spy and fade-in-after-hero-scroll behavior
   - Verify: nav hidden at page load; appears after scrolling 80% of hero height; active link highlights on scroll

---

### Milestone 2 — Content Sections (M2)

**Goal:** All 6 content sections rendered with real content, `whileInView` animations working.

7. **M2-S1: `useScrollAnimation` hook** — implement once, use everywhere
8. **M2-S2: `AboutSection`** — prose + photo placeholder
9. **M2-S3: `PhilosophySection` + `PhilosophyCard`** — 3-column grid on desktop, stagger
10. **M2-S4: `ExperienceSection` + `TimelineItem`** — 8 roles, timeline connector line, stagger
11. **M2-S5: `HiverSection` + `TransformationCard`** — 7 items, numbered, grid layout
12. **M2-S6: `ContactSection`** — mailto + LinkedIn links, keyboard accessible
13. **M2-S7: Populate all content modules** — extract text from Executive Narrative PDF into TypeScript constants and `knowledge_base.md`
14. **M2-S8: Responsive pass** — verify all breakpoints (375px, 768px, 1024px, 1440px) with no horizontal overflow

---

### Milestone 3 — Chatbot Integration (M3)

**Goal:** HuggingFace Space live and embeddable; ChatbotWidget functional end-to-end.

15. **M3-S1: Write `knowledge_base.md`** — curated ~4,000 token knowledge base from Executive Narrative
16. **M3-S2: Write `app.py` + `requirements.txt`** — exact Gradio `ChatInterface` configuration (Section 5.2)
17. **M3-S3: Create HuggingFace Space** — create Space, upload files, set `ANTHROPIC_API_KEY` Secret
18. **M3-S4: Verify chatbot standalone** — open `*.hf.space` URL directly; test all 3 example questions; verify no hallucination on out-of-scope question
19. **M3-S5: Implement `ChatbotWidget`** — FAB, `AnimatePresence` panel, deferred `src` injection, loading skeleton
20. **M3-S6: End-to-end test** — open widget in portfolio dev server; verify loading skeleton appears; verify Gradio loads after cold start; verify panel closes on FAB click

---

### Milestone 4 — Deployment + Polish (M4)

**Goal:** Site deployed to Vercel, Lighthouse ≥ 90, zero console errors.

21. **M4-S1: `vercel.json`** — write CSP headers config (Section 5.3)
22. **M4-S2: Deploy to Vercel** — connect GitHub repo; trigger build; verify `*.vercel.app` URL resolves
23. **M4-S3: CSP verification** — open deployed site; open DevTools Console; verify no CSP violations; verify chatbot iframe loads
24. **M4-S4: Lighthouse audit** — run PageSpeed Insights on deployed URL; address any score below 90 (likely: image format, font preload, unused JS)
25. **M4-S5: Cross-browser QA** — Chrome, Safari, Firefox on desktop; iOS Safari on mobile; verify no broken layouts or console errors
26. **M4-S6: Reduced-motion QA** — enable "Reduce Motion" in OS settings; verify static canvas, no animation, full readability
27. **M4-S7: Accessibility spot-check** — keyboard navigation through all interactive elements; verify `aria-label` attributes; verify heading hierarchy

---

## 8. File Structure

### `projects/mywebsite/code/` — Vite React Application

```
code/
├── index.html                        # Vite entry; Google Fonts <link> tags here
├── vite.config.ts                    # react() + tailwindcss() plugins
├── tsconfig.json                     # TypeScript strict mode
├── tsconfig.node.json
├── package.json
├── vercel.json                       # CSP headers for Vercel deployment
├── .gitignore
├── public/
│   └── images/
│       └── profile.jpg               # Kumar's photo (added by Kumar; graceful 404 handling)
└── src/
    ├── main.tsx                      # React DOM root; @fontsource-variable/geist-mono import
    ├── App.tsx                       # Root: ReactLenis + frame.update() wiring; section layout
    ├── index.css                     # @import "tailwindcss"; @theme {} color + font tokens
    ├── vite-env.d.ts                 # Vite type declarations
    ├── content/                      # All site copy — zero strings in JSX
    │   ├── hero.ts                   # HeroContent constant
    │   ├── about.ts                  # AboutContent constant
    │   ├── philosophy.ts             # PhilosophyPillar[] array
    │   ├── timeline.ts               # ExperienceRole[] array (8 entries)
    │   ├── hiver.ts                  # HiverTransformation[] array (7 entries)
    │   ├── contact.ts                # ContactContent constant
    │   └── nav.ts                    # NavItem[] array (5 entries)
    ├── components/
    │   ├── NavigationBar.tsx
    │   ├── HeroSection.tsx
    │   ├── NetworkCanvas.tsx
    │   ├── AboutSection.tsx
    │   ├── PhilosophySection.tsx
    │   ├── PhilosophyCard.tsx
    │   ├── ExperienceSection.tsx
    │   ├── TimelineItem.tsx
    │   ├── HiverSection.tsx
    │   ├── TransformationCard.tsx
    │   ├── ContactSection.tsx
    │   └── ChatbotWidget.tsx
    └── hooks/
        └── useScrollAnimation.ts     # useScrollAnimation hook (Section 4.15)
```

### `projects/mywebsite/chatbot/` — HuggingFace Space

```
chatbot/
├── app.py                            # Gradio ChatInterface + Anthropic SDK
├── requirements.txt                  # gradio>=4.0, anthropic>=0.40.0
└── knowledge_base.md                 # ~4,000 token curated knowledge base (system prompt context)
```

**Note:** `chatbot/` is deployed by uploading these 3 files to the HuggingFace Space directly (via the HF UI drag-and-drop or `git push` to the HF Space repo). It is **not** part of the Vercel build. The `ANTHROPIC_API_KEY` is set in the HF Secrets UI — it does not appear in any file here.

### `projects/mywebsite/docs/` — Pipeline Artifacts

```
docs/
├── research.md                       # Stage 1 output
├── plan.md                           # Stage 2 output
├── prd.md                            # Stage 3 output
└── tech-spec.md                      # Stage 4 output (this document)
```

---

## 9. Open Technical Questions

After resolving OQ1–OQ5, only the following genuine unknowns remain for V1:

### OTQ1 — Exact Content Values

The TypeScript content modules (`hero.ts`, `about.ts`, `philosophy.ts`, `timeline.ts`, `hiver.ts`, `contact.ts`) and `knowledge_base.md` require the actual text from the Executive Narrative PDF. The implementer must read `projects/mywebsite/The Executive Narrative of Kumar Shailove.pdf` and populate all string constants before Stage 5 begins.

**Blocking?** Yes — no UI component can be correctly verified without real content. The implementation agent must do this extraction as Step M2-S7.

### OTQ2 — HuggingFace Username and Space Slug

The `spaceUrl` prop passed to `ChatbotWidget` depends on Kumar's HuggingFace account username and the chosen Space name. This is a human decision (Kumar's username) and an availability check (Space slug must not be taken).

**Blocking?** Only for M3. During M1 and M2, the `spaceUrl` prop can be a placeholder `https://placeholder.hf.space`. The `ChatbotWidget` will render the loading skeleton indefinitely — which is visually correct for testing the widget UI without a live Space.

### OTQ3 — Profile Photo

Kumar must provide `public/images/profile.jpg` (or `profile.webp`). The `AboutSection` implements graceful fallback (initials placeholder) so this does not block development or deployment, but the site should not be considered "done" without a real photo.

**Blocking?** No — placeholder renders correctly per the PRD acceptance criteria.

---

*Tech spec complete. Artifact: `docs/tech-spec.md`*
