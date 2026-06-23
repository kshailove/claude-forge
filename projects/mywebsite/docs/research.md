# Stage 1 Research Report — Kumar Shailove Personal Portfolio Website

**Date:** 2026-06-23  
**Prepared by:** ClaudeForge Research Agent (Stage 1)  
**Project:** `projects/mywebsite`  
**Brief source:** `projects/mywebsite/brief.md`

---

## Table of Contents

1. [Problem Space](#1-problem-space)
2. [Design Inspiration Analysis — searchpankaj.com](#2-design-inspiration-analysis)
3. [Technology Landscape](#3-technology-landscape)
4. [Canvas Network Background Implementation](#4-canvas-network-background)
5. [Gradio / HuggingFace Integration](#5-gradio--huggingface-integration)
6. [Risks & Unknowns](#6-risks--unknowns)
7. [Recommended Direction](#7-recommended-direction)

---

## 1. Problem Space

Kumar Shailove is a senior executive (CEO/CPO/CRO experience spanning 2004–present, most recently at Hiver) who needs a personal portfolio website that conveys gravitas, technical sophistication, and strategic leadership — not a typical developer portfolio.

**Core requirements extracted from brief.md:**

- Six-section single-page layout: Hero, About/Narrative, Philosophy, Experience Timeline, Hiver Case Study, Contact + Chatbot
- Design inspiration: searchpankaj.com (React + TypeScript + Vite, Motion library, Lenis smooth scroll, HTML canvas/SVG for network background, Instrument Serif + Geist Mono fonts, Tailwind CSS)
- Content source: "The Executive Narrative of Kumar Shailove.pdf" (on disk at `projects/mywebsite/`)
- Photograph placeholder (images folder, TBD by user)
- Recommendations from topmate.io/kumar_shailove and LinkedIn
- Expandable chatbot widget (bottom-right) backed by a Gradio app on HuggingFace Spaces, itself backed by Claude API (`claude-sonnet-4-6`)

**Design brief tension:** The reference site (searchpankaj.com) is an SRE/DevOps engineer's portfolio — technical and minimal. Kumar's site needs to carry executive presence: editorial typography, confident whitespace, understated luxury. The *technique* (canvas, smooth scroll, motion) should be borrowed; the *tone* should be elevated.

---

## 2. Design Inspiration Analysis

### 2.1 What is searchpankaj.com?

searchpankaj.com is a portfolio for Pankaj Kumar, a Platform / DevOps / SRE Engineer. The site is publicly accessible. Due to JavaScript-rendered content and a minimal initial HTML payload, automated full-page scraping extracts only the `<title>` element. The analysis below is therefore based on:

- The tech stack confirmed in Kumar's brief (first-hand knowledge of the reference)
- Community research into the specific libraries named
- Visual patterns typical of this class of portfolio (Motion + Lenis + Canvas + dark theme)

### 2.2 Inferred Design Characteristics

**Color palette (dark editorial portfolio archetype):**
- Background: near-black (`#0a0a0a` or `#080808`)
- Text primary: off-white (`#f5f5f5` or `#e8e8e8`)
- Text secondary: mid-grey (`#888`, `#999`)
- Accent: likely a single warm tone (amber/gold) or cool tone (electric blue/cyan) for hover states and node glow
- Canvas background: dark with translucent particle nodes and connecting edges drawn with low-opacity lines

**Typography:**
- **Instrument Serif** — condensed old-style serif, designed for Instrument agency by Rodrigo Fuenzalida. Best at large sizes: hero headings, section titles. Carries editorial, brand-forward character. Pairs with mono for contrast. Free via Google Fonts (SIL OFL).
- **Geist Mono** — monospaced typeface by Vercel, designed for code editors/terminals. Used for secondary labels, captions, role titles, metadata. Available via `@fontsource/geist-mono` npm or `@fontsource-variable/geist-mono` for variable font support.

**Layout / structure (inferred from brief + archetype):**
- Full-viewport sections, scroll-snapping or smooth sequential reveal
- Sticky or hidden-on-scroll navigation bar
- Hero: large serif headline, subtitle in mono, canvas particle network occupying full background
- Content sections: alternating text-heavy and visual layouts
- No heavy imagery beyond profile photo — relies on typography and motion for visual interest

**Animation patterns (confirmed from brief + Motion library research):**
- Scroll-triggered fade-ins and slide-ups using `whileInView` / `initial` → `animate` patterns
- Stagger children reveals (list items, timeline entries appearing sequentially)
- Parallax depth using `useScroll` + `useTransform`
- Canvas animation runs independently via `requestAnimationFrame` loop
- Lenis smooth scroll provides inertia/easing that makes all scroll-linked animations feel "liquid"

**What makes it visually distinctive:**
1. The canvas particle network creates a living, ambient background that reacts to mouse position
2. Instrument Serif at large scale creates unexpected editorial gravitas for a technical portfolio
3. Lenis smooth scroll gives every interaction a premium tactile quality
4. Motion's hybrid engine (Web Animations API + JS fallback) ensures 120fps on modern devices
5. Mono font used for technical metadata creates designer-developer credibility signal

---

## 3. Technology Landscape

### 3.1 Scaffolding — Vite + React + TypeScript

**Command (2026):**
```bash
npm create vite@latest my-portfolio -- --template react-ts
cd my-portfolio
npm install
```

**Output structure:**
```
src/
  main.tsx          # Entry point
  App.tsx           # Root component
  index.css         # Global styles (Tailwind import here)
  assets/
vite.config.ts
tsconfig.json
tsconfig.node.json
```

**Key gotchas:**
- The `react-ts` template ships with React 19 as of 2026
- TypeScript strict mode is on by default — good
- No PostCSS needed with Tailwind v4 Vite plugin
- HMR works out of the box; canvas `useEffect` hooks need explicit cleanup to avoid HMR leaks

---

### 3.2 Tailwind CSS v4

**Installation:**
```bash
npm install @tailwindcss/vite
```

**`vite.config.ts`:**
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
})
```

**`src/index.css`** (replaces all `@tailwind` directives):
```css
@import "tailwindcss";

@theme {
  --font-serif: "Instrument Serif", Georgia, serif;
  --font-mono: "Geist Mono", "Courier New", monospace;
  --color-bg: oklch(0.08 0 0);
  --color-surface: oklch(0.12 0 0);
  --color-text: oklch(0.95 0 0);
  --color-muted: oklch(0.55 0 0);
  --color-accent: oklch(0.75 0.15 60);   /* amber-gold */
}
```

**Key v4 changes from v3:**
| v3 | v4 |
|----|-----|
| `tailwind.config.js` | `@theme {}` block in CSS |
| `@tailwind base; @tailwind components; @tailwind utilities;` | `@import "tailwindcss";` |
| Manual `content: [...]` array | Automatic source detection |
| PostCSS required | `@tailwindcss/vite` plugin (no PostCSS needed) |
| `bg-gradient-*` | `bg-linear-*` |
| Colors in rgb | Colors in oklch (wider gamut) |
| Container queries via plugin | Built-in `@container` support |

**Build performance:** Incremental builds ~180x faster than v3, which matters for canvas component hot-reloading.

---

### 3.3 Motion (formerly Framer Motion)

**Current package:** `motion` (npm) — successor to `framer-motion` as of 2025  
**Current version:** v12 (March 2026)  
**Import path change:** `from 'motion/react'` (not `from 'framer-motion'`)

**Installation:**
```bash
npm install motion
```

**Core imports:**
```typescript
import { motion, AnimatePresence } from 'motion/react'
import {
  useScroll,
  useTransform,
  useSpring,
  useInView,
  useMotionValue,
  useMotionTemplate,
  useAnimationFrame,
} from 'motion/react'
```

**Key patterns for this project:**

**1. Scroll-triggered section reveal (whileInView):**
```typescript
<motion.section
  initial={{ opacity: 0, y: 40 }}
  whileInView={{ opacity: 1, y: 0 }}
  viewport={{ once: true, margin: '-100px' }}
  transition={{ duration: 0.7, ease: [0.25, 0.46, 0.45, 0.94] }}
>
  {/* section content */}
</motion.section>
```

**2. Stagger children (timeline, philosophy pillars):**
```typescript
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.15 },
  },
}
const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
}

<motion.ul variants={container} initial="hidden" whileInView="show">
  {roles.map(role => (
    <motion.li key={role.id} variants={item}>{...}</motion.li>
  ))}
</motion.ul>
```

**3. Scroll-linked parallax (hero background depth):**
```typescript
const { scrollY } = useScroll()
const heroY = useTransform(scrollY, [0, 500], [0, -150])

<motion.div style={{ y: heroY }} className="absolute inset-0">
  {/* canvas background */}
</motion.div>
```

**4. Hardware-accelerated scroll progress:**
```typescript
const { scrollYProgress } = useScroll({ target: sectionRef, offset: ['start end', 'end start'] })
const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30 })
```

**v12 notable features:**
- `ScrollTimeline` native hardware acceleration (no JS overhead for scroll progress)
- `oklch`, `oklab`, `lch`, `color-mix()` values can now be animated directly
- CSS `ViewTimeline` can drive `scroll()`-based animations

**Migration note:** If any existing `framer-motion` code exists, upgrade is a package rename + import path change. No API-level breaking changes for standard usage.

---

### 3.4 Lenis Smooth Scroll

**Package:** `lenis` (NOT `@studio-freight/lenis` — deprecated)  
**Current version:** 1.3.23+  
**Maintainer:** darkroom.engineering (formerly Studio Freight)

**Installation:**
```bash
npm install lenis
```

**React setup (root-level):**
```typescript
// main.tsx or App.tsx
import { ReactLenis } from 'lenis/react'
import 'lenis/dist/lenis.css'

function App() {
  return (
    <ReactLenis root options={{ lerp: 0.08, duration: 1.2, syncTouch: true }}>
      {/* entire app */}
    </ReactLenis>
  )
}
```

**Critical integration — Lenis + Motion (avoid animation frame conflict):**

The most common bug when combining Lenis and Motion is conflicting `requestAnimationFrame` loops. Motion runs its own RAF loop; Lenis also runs RAF by default. The fix:

```typescript
import { ReactLenis, useLenis } from 'lenis/react'
import { frame, cancelFrame } from 'motion/react'

// In a wrapper component:
const lenisRef = useRef<LenisRef>(null)

useEffect(() => {
  function update(data: { timestamp: number }) {
    lenisRef.current?.lenis?.raf(data.timestamp)
  }
  // Use Motion's frame loop to drive Lenis
  frame.update(update, true)
  return () => cancelFrame(update)
}, [])

// In ReactLenis component:
<ReactLenis ref={lenisRef} autoRaf={false} options={{ lerp: 0.08 }}>
```

**`useLenis` hook (scroll event subscription):**
```typescript
const lenis = useLenis(({ scroll, progress }) => {
  // called on every scroll event
  // use for updating non-Motion UI elements
})
```

**Lenis options:**
- `lerp` (0.0–1.0): interpolation amount — lower = smoother/slower (0.08 recommended for premium feel)
- `duration`: animation duration in seconds (alternative to lerp)
- `syncTouch`: mirrors lerp behavior on touch devices
- `easing`: custom easing function
- `orientation`: `'vertical'` (default) or `'horizontal'`

---

### 3.5 Font Loading

**Instrument Serif (Google Fonts)**

Load via `<link>` in `index.html` (recommended for Google Fonts — browser cache, CDN):
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
```

Or via Fontsource npm (self-hosted, no external request):
```bash
npm install @fontsource/instrument-serif
```
```typescript
// main.tsx
import '@fontsource/instrument-serif'
import '@fontsource/instrument-serif/400-italic.css'
```

**Geist Mono (npm — Vercel's font)**

```bash
npm install @fontsource/geist-mono
# or variable font version:
npm install @fontsource-variable/geist-mono
```
```typescript
// main.tsx
import '@fontsource/geist-mono/400.css'
import '@fontsource/geist-mono/500.css'
// or for variable:
import '@fontsource-variable/geist-mono'
```

**CSS registration (in `@theme` block):**
```css
@theme {
  --font-serif: "Instrument Serif", Georgia, serif;
  --font-mono: "Geist Mono", ui-monospace, monospace;
}
```

**Tailwind usage:**
```tsx
<h1 className="font-serif text-7xl italic">Kumar Shailove</h1>
<span className="font-mono text-sm tracking-wider uppercase">CEO · CPO · CRO</span>
```

---

## 4. Canvas Network Background

### 4.1 What it looks like

The canvas network background (common in dark-theme technical portfolios) consists of:
- A `<canvas>` element filling the viewport, positioned `absolute inset-0` behind content
- 60–100 nodes (small circles, 2–4px radius) distributed randomly
- Each node drifts slowly in a random direction, bouncing off edges
- Edges (lines) drawn between nodes within a threshold distance (~150px)
- Edge opacity fades proportionally with distance (closer = more opaque)
- Nodes and edges glow faintly — achieved via canvas `shadowBlur` or low-opacity fill
- Optional: mouse cursor acts as a repulsion or attraction point (nodes flee/approach)
- Optional: nodes near the mouse get brighter, connected edges become more visible

### 4.2 Library vs. Hand-Rolled Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **tsParticles** (`@tsparticles/react`) | Config-driven, feature-rich, actively maintained | Bundle size ~50KB, opinionated API, less control |
| **particles.js** | Very widely used, many examples | Unmaintained, jQuery-era code, no TypeScript |
| **Hand-rolled canvas** | Zero dependency, full control, tiny, exact match to design | ~80–120 lines of code required, manual |
| **nodes.js** | Explicit network/graph aesthetic | Small community, limited docs |

**Recommendation:** Hand-rolled canvas component. The network background is ~100 lines of vanilla TypeScript + `useEffect` + `useRef`. Libraries add bundle weight and force the aesthetic into their config API. For a portfolio, full control over colors, glow, mouse interaction, and performance matters.

### 4.3 React Implementation Pattern

```typescript
// src/components/NetworkCanvas.tsx
import { useEffect, useRef } from 'react'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
}

const PARTICLE_COUNT = 70
const MAX_DISTANCE = 140
const NODE_COLOR = 'rgba(255, 200, 100, 0.7)'   // warm amber
const EDGE_COLOR = 'rgba(255, 200, 100, '         // prefix — alpha appended
const GLOW_COLOR = 'rgba(255, 180, 80, 0.4)'

export function NetworkCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mouseRef = useRef({ x: -9999, y: -9999 })
  const rafRef = useRef<number>(0)

  useEffect(() => {
    const canvas = canvasRef.current!
    const ctx = canvas.getContext('2d')!
    let particles: Particle[] = []

    const resize = () => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }

    const init = () => {
      resize()
      particles = Array.from({ length: PARTICLE_COUNT }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        radius: Math.random() * 2 + 1.5,
      }))
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // Draw edges
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < MAX_DISTANCE) {
            const alpha = (1 - dist / MAX_DISTANCE) * 0.4
            ctx.beginPath()
            ctx.strokeStyle = EDGE_COLOR + alpha + ')'
            ctx.lineWidth = 0.8
            ctx.moveTo(particles[i].x, particles[i].y)
            ctx.lineTo(particles[j].x, particles[j].y)
            ctx.stroke()
          }
        }
      }

      // Draw nodes
      particles.forEach(p => {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
        ctx.fillStyle = NODE_COLOR
        ctx.shadowBlur = 8
        ctx.shadowColor = GLOW_COLOR
        ctx.fill()
        ctx.shadowBlur = 0
      })
    }

    const update = () => {
      particles.forEach(p => {
        // Mouse repulsion
        const mdx = p.x - mouseRef.current.x
        const mdy = p.y - mouseRef.current.y
        const mdist = Math.sqrt(mdx * mdx + mdy * mdy)
        if (mdist < 100) {
          p.vx += (mdx / mdist) * 0.3
          p.vy += (mdy / mdist) * 0.3
        }
        // Velocity damping
        p.vx *= 0.99
        p.vy *= 0.99
        p.x += p.vx
        p.y += p.vy
        // Bounce
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1
      })
    }

    const loop = () => {
      update()
      draw()
      rafRef.current = requestAnimationFrame(loop)
    }

    const onMouse = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect()
      mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    }

    init()
    loop()
    window.addEventListener('resize', init)
    canvas.addEventListener('mousemove', onMouse)

    return () => {
      cancelAnimationFrame(rafRef.current)
      window.removeEventListener('resize', init)
      canvas.removeEventListener('mousemove', onMouse)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden="true"
    />
  )
}
```

**Usage in Hero section:**
```typescript
<section className="relative min-h-screen overflow-hidden bg-[var(--color-bg)]">
  <NetworkCanvas />
  <div className="relative z-10 flex flex-col justify-center min-h-screen px-8 max-w-7xl mx-auto">
    <h1 className="font-serif text-8xl italic text-[var(--color-text)]">Kumar Shailove</h1>
    {/* ... */}
  </div>
</section>
```

### 4.4 Performance Considerations

- Keep particle count at 60–100; above 150 causes frame drops on mid-range devices
- Use `pointer-events: none` on the canvas so it doesn't block scrolling or clicks
- `shadowBlur` is expensive — use sparingly (only on nodes, not edges)
- Resize handler should debounce or throttle on mobile
- Respect `prefers-reduced-motion`: check via `window.matchMedia('(prefers-reduced-motion: reduce)')` and skip the animation entirely if true, showing a static gradient instead

---

## 5. Gradio / HuggingFace Integration

### 5.1 Architecture Overview

```
Portfolio Website (Vite/React)
  └── Chatbot widget component
        └── <iframe> or <gradio-app> Web Component
              └── HuggingFace Space (public)
                    └── Gradio ChatInterface (Python)
                          └── Anthropic Python SDK
                                └── claude-sonnet-4-6
```

### 5.2 HuggingFace Space Setup

**Requirements:**
- HuggingFace account (free tier sufficient for portfolio use)
- Space must be **public** (or "protected" — source private but embed URL works)
- Runtime: CPU Basic (free) — note cold start latency (see Risks section)

**Space URL format:**
```
https://<username>-<space-name>.hf.space
```
Example: `https://kumarshailove-portfolio-chat.hf.space`

**Space files:**
- `app.py` — Gradio application code
- `requirements.txt` — `gradio`, `anthropic`
- `knowledge_base.md` — Kumar's background, achievements, FAQ (injected into system prompt)
- `.env` — `ANTHROPIC_API_KEY` (set as HuggingFace Space Secret in UI, not committed)

### 5.3 Gradio ChatInterface + Claude API

**`app.py` (recommended pattern):**
```python
import gradio as gr
import anthropic
import os

# Load knowledge base from file for easy updates
with open("knowledge_base.md", "r") as f:
    KNOWLEDGE_BASE = f.read()

SYSTEM_PROMPT = f"""You are Kumar Shailove's personal AI assistant on his portfolio website.
Your role is to answer questions about Kumar's career, philosophy, achievements, and expertise.
Be professional, confident, and concise. Speak in first person when asked about Kumar's work
(e.g., "Kumar led..." or "At Hiver, Kumar..."). Do not make up information.

Here is Kumar's background:
{KNOWLEDGE_BASE}

Guidelines:
- Answer questions about Kumar's career history, leadership philosophy, and achievements
- For contact/collaboration inquiries, direct visitors to the contact section
- If asked something not covered in the knowledge base, say so honestly
- Keep responses under 200 words unless a detailed answer is clearly needed
"""

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def chat(message: str, history: list[dict]) -> str:
    """
    history: list of {"role": "user"|"assistant", "content": str}
    """
    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history
        if msg["role"] in ("user", "assistant")
    ]
    messages.append({"role": "user", "content": message})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return response.content[0].text

demo = gr.ChatInterface(
    fn=chat,
    title="Ask about Kumar",
    description="Ask me about Kumar's career, leadership approach, or work at Hiver.",
    theme=gr.themes.Soft(),
    examples=[
        "What did Kumar accomplish at Hiver?",
        "What is Kumar's leadership philosophy?",
        "Tell me about Kumar's career journey.",
    ],
    type="messages",  # use OpenAI-style message dicts
)

if __name__ == "__main__":
    demo.launch()
```

**`requirements.txt`:**
```
gradio>=4.0
anthropic>=0.40.0
```

**Note on model:** The brief specifies `claude-sonnet-4-6`. This is valid — current pricing is $3.00/$15.00 per 1M tokens (input/output). For a chatbot on a portfolio, this is appropriate: capable enough for nuanced questions, cost-effective for the expected low volume.

### 5.4 Embedding in the Portfolio

**Option A — iframe (simpler, always works):**
```tsx
// src/components/ChatWidget.tsx
import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'

const SPACE_URL = 'https://kumarshailove-portfolio-chat.hf.space'

export function ChatWidget() {
  const [open, setOpen] = useState(false)

  return (
    <div className="fixed bottom-6 right-6 z-50">
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="mb-4 rounded-2xl overflow-hidden shadow-2xl border border-white/10"
          >
            <iframe
              src={SPACE_URL}
              width="400"
              height="520"
              frameBorder="0"
              title="Chat with Kumar's AI assistant"
            />
          </motion.div>
        )}
      </AnimatePresence>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-14 h-14 rounded-full bg-amber-500 text-black flex items-center justify-center shadow-lg hover:scale-105 transition-transform"
        aria-label="Open chat"
      >
        {/* icon */}
      </button>
    </div>
  )
}
```

**Option B — Gradio Web Components (faster initial load, auto-sizing):**
```html
<!-- index.html -->
<script type="module" src="https://gradio.s3-us-west-2.amazonaws.com/4.x.x/gradio.js"></script>
```
```tsx
// In React component — use dangerouslySetInnerHTML or a ref
<gradio-app src="https://kumarshailove-portfolio-chat.hf.space" />
```
Note: Web Components in React require type assertion (`as any`) or a custom declaration. The iframe approach is more React-idiomatic.

### 5.5 CORS / CSP Considerations

- **iframes bypass CORS** — the browser loads the iframe in its own context; no CORS headers needed on the HuggingFace Space
- **CSP on the portfolio site** — if the portfolio itself sets a `Content-Security-Policy` header (e.g., via Vercel/Netlify config), it must include `frame-src https://*.hf.space` to allow the iframe
- **Gradio JS client (`@gradio/client`)** — an alternative to iframe that communicates with the Space API directly. Requires CORS to be open on the Space; the default HuggingFace Space configuration does allow this, but it adds a custom TypeScript integration layer. Not recommended for this use case — iframe is simpler.
- **HuggingFace Spaces CORS:** The default Space deployment sets permissive CORS headers for the embed URL, but API calls directly to the Space backend from a different origin may hit issues. The iframe approach sidesteps this entirely.

---

## 6. Risks & Unknowns

### Risk 1: searchpankaj.com Animation Replicability (Medium)

**Issue:** The exact animations on searchpankaj.com could not be scraped due to JavaScript rendering. The brief says to take inspiration from the "tech stack and design" — the specific animation choreography is unknown.

**Mitigation:** The tech stack is confirmed (Motion + Lenis + canvas). Standard patterns for this stack — `whileInView` reveals, stagger children, scroll parallax — are well-documented and will produce a comparable result. The canvas network background is hand-rolled based on the confirmed description. Risk is low to medium: we can replicate the *feel* without the *exact* implementation.

**Unknowns:** Whether searchpankaj.com uses horizontal scroll, scroll-snap, or any unusual viewport geometry. These would require deviation from standard vertical single-page layout.

---

### Risk 2: Lenis + Motion Frame Loop Conflict (Medium, Mitigated)

**Issue:** Lenis defaults to its own `requestAnimationFrame` loop. Motion (v12) also manages its own RAF loop. Running both independently causes jank — scroll position updates on a different frame than Motion's spring calculations, producing visible stuttering.

**Mitigation (confirmed pattern):** Set `autoRaf: false` on `ReactLenis` and drive Lenis manually via `frame.update()` from Motion's loop (code shown in Section 3.4). This is a known, documented pattern. **Must be implemented from the start** — retrofitting it after noticing jank is painful.

**Additional known issue:** React Strict Mode (development mode) causes `useEffect` to run twice. Lenis initialized inside `useEffect` will create two instances; the second overwrites the first, but the first's RAF may still be running. Use cleanup functions religiously. The `ReactLenis` component from the official package handles this correctly — do not hand-roll the Lenis initialization.

---

### Risk 3: HuggingFace Spaces Free Tier Cold Starts (High, UX Impact)

**Issue:** Free CPU Spaces automatically sleep after ~15 minutes of inactivity. The first visitor after inactivity faces a 10–30 second cold start before the Gradio app responds. For a portfolio chatbot this is a significant UX failure — visitors trying the chatbot immediately get a "loading" state or timeout.

**Mitigation options:**
1. **Show a clear loading state** in the iframe widget — "Waking up Kumar's AI assistant... this takes ~20 seconds" — sets expectations
2. **Upgrade to paid hardware** ($0.05/hour CPU Upgrade tier) — keeps Space warm but adds ongoing cost
3. **Ping the Space proactively** — a small cron job or serverless function that hits the Space URL every 10 minutes to prevent sleep. Simple but violates HuggingFace ToS if done aggressively
4. **Warm-up on widget open** — when the chat widget is opened (button click), immediately load the iframe. Most visitors will expand the widget, see the loading state, and wait ~15s while reading the rest of the page. This is the lowest-friction free solution.

**Recommendation:** Implement the widget with a skeleton loading state. Defer the iframe `src` injection until the widget is opened. Show a "Loading assistant..." message. Accept 10–20s cold start as acceptable for a personal portfolio.

---

### Risk 4: Canvas Performance on Mobile (Low-Medium)

**Issue:** `requestAnimationFrame` with 70 particles + edge drawing + `shadowBlur` is comfortable on desktop (60–120fps) but may drop below 30fps on low-end mobile devices. `shadowBlur` is particularly expensive on mobile GPUs.

**Mitigation:**
- Detect mobile via `window.innerWidth < 768` or `navigator.maxTouchPoints > 0`
- Reduce particle count to 30–40 on mobile
- Disable `shadowBlur` on mobile
- Or replace canvas with a CSS `radial-gradient` animated background on mobile using `@media (hover: none)`

---

### Risk 5: Instrument Serif Italic / Weight Availability (Low)

**Issue:** Instrument Serif is available from Google Fonts but only in Regular (400) and Italic (400 italic). There is no bold weight. If the design requires bold serif headings, a fallback must be chosen.

**Mitigation:** Design all serif headings at large size (5xl+) in regular or italic weight. The large size provides visual weight without a bold variant. This is actually the intended use case per the type designers. Not a blocker.

---

### Risk 6: Claude API Key in HuggingFace Space (Low, Manageable)

**Issue:** The ANTHROPIC_API_KEY must be stored in the HuggingFace Space. If the Space is public, only the API is public — the Secrets (environment variables) are not exposed. However, the Gradio API endpoint is public, meaning anyone could call it programmatically and exhaust API credits.

**Mitigation:**
- Set spending limits on the Anthropic API key
- Add rate limiting in the Gradio app (maintain a request counter, return a polite message if limit exceeded)
- Consider a simple token/referrer check (the chatbot is embedded on a specific domain; reject requests without a matching header — though iframes make this imperfect)

---

## 7. Recommended Direction

**Build a Vite + React + TypeScript single-page portfolio using Motion v12 (`motion/react`) for scroll animations, Lenis 1.3+ (`lenis/react`) with `autoRaf: false` and Motion frame loop coordination for smooth scroll, a hand-rolled `<NetworkCanvas>` component (~100 lines) for the hero background, Tailwind CSS v4 with the `@tailwindcss/vite` plugin and CSS-first `@theme` configuration, Instrument Serif via Google Fonts for editorial headings and Geist Mono via `@fontsource-variable/geist-mono` for technical labels, and a HuggingFace Spaces Gradio chatbot backed by `claude-sonnet-4-6` with Kumar's executive narrative injected as system prompt context — embedded as a bottom-right expandable iframe widget that defers loading until the user opens it to mitigate cold-start UX.**

---

*Research complete. Artifact: docs/research.md*
