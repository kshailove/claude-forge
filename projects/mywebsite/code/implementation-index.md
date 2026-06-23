# Implementation Index

Stage 5 complete — all files produced by ClaudeForge Implementation Agent.

## React App (`code/`)

### Configuration (6 files)
| File | Purpose |
|------|---------|
| `package.json` | Dependencies: React 19, Motion 12, Lenis 1.3, Tailwind v4, TypeScript 5 |
| `vite.config.ts` | Vite 6 with react() and tailwindcss() plugins |
| `tsconfig.json` | TypeScript composite project root |
| `tsconfig.app.json` | App TypeScript config (strict mode) |
| `tsconfig.node.json` | Node/Vite TypeScript config |
| `.gitignore` | Standard Vite gitignore |

### Entry Points (3 files)
| File | Purpose |
|------|---------|
| `index.html` | Vite entry; Instrument Serif Google Fonts links |
| `src/main.tsx` | React root mount; imports Geist Mono font |
| `src/vite-env.d.ts` | Vite client type declarations |

### Styling (1 file)
| File | Purpose |
|------|---------|
| `src/index.css` | Tailwind v4 `@import` + `@theme {}` with 5 color tokens + 3 font stacks |

### Root Component (1 file)
| File | Purpose |
|------|---------|
| `src/App.tsx` | ReactLenis + frame.update() RAF wiring; all section layout |

### Content Modules (7 files, zero strings in JSX)
| File | Purpose |
|------|---------|
| `src/content/hero.ts` | HeroContent: name, role, headline, tagline, CTA |
| `src/content/about.ts` | AboutContent: opening, career arc (6 steps), body, closing, photo |
| `src/content/philosophy.ts` | PhilosophyPillar[]: 3 pillars with title, pullQuote, body |
| `src/content/timeline.ts` | ExperienceRole[]: 8 roles (newest-first) |
| `src/content/hiver.ts` | HiverTransformation[]: 7 transformations + intro |
| `src/content/contact.ts` | ContactContent: email, LinkedIn, Topmate |
| `src/content/nav.ts` | NavItem[]: 5 navigation anchors |

### Components (12 files)
| File | Purpose |
|------|---------|
| `src/components/NetworkCanvas.tsx` | Hand-rolled particle network; mouse repulsion; mobile adapt; RAF cleanup |
| `src/components/NavigationBar.tsx` | Scroll-spy nav; hidden until 80% hero scroll |
| `src/components/HeroSection.tsx` | Full-viewport hero; canvas parallax; staggered entry |
| `src/components/AboutSection.tsx` | Career narrative; career arc steps; photo with placeholder |
| `src/components/PhilosophySection.tsx` | 3-column philosophy grid with stagger |
| `src/components/PhilosophyCard.tsx` | Single pillar: title, pullQuote, body |
| `src/components/ExperienceSection.tsx` | Timeline container with connector line |
| `src/components/TimelineItem.tsx` | Single role entry with dot indicator |
| `src/components/HiverSection.tsx` | 7 transformations grid with stagger |
| `src/components/TransformationCard.tsx` | Single transformation: number, title, detail |
| `src/components/ContactSection.tsx` | Email, LinkedIn, Topmate links |
| `src/components/ChatbotWidget.tsx` | FAB; AnimatePresence panel; deferred iframe; loading skeleton |

### Hooks (1 file)
| File | Purpose |
|------|---------|
| `src/hooks/useScrollAnimation.ts` | Reusable whileInView reveal; respects prefers-reduced-motion |

### Deployment (2 files)
| File | Purpose |
|------|---------|
| `vercel.json` | CSP headers including frame-src https://*.hf.space |
| `public/favicon.svg` | Dark rounded-rect with gold "K" |

### Documentation (2 files)
| File | Purpose |
|------|---------|
| `README.md` | Install, dev, build, deploy, chatbot setup instructions |
| `implementation-index.md` | This file |

**Total React app files: 38**

---

## Chatbot (`chatbot/`)

| File | Purpose |
|------|---------|
| `app.py` | Gradio ChatInterface + Anthropic SDK; claude-sonnet-4-6; type="messages" |
| `requirements.txt` | gradio>=4.0, anthropic>=0.40.0 |
| `knowledge_base.md` | ~4,000 token curated knowledge base for system prompt |

**Total chatbot files: 3**

---

**Grand total: 41 files**

## Critical Implementation Notes

1. **Lenis + Motion RAF**: `autoRaf={false}` + `frame.update(update, true)` in `App.tsx` — both systems share one animation loop
2. **Canvas cleanup**: `cancelAnimationFrame` + both `removeEventListener` calls in `useEffect` return
3. **Deferred chatbot**: `iframeSrc` starts `null`; only set to `spaceUrl` on first FAB open
4. **Mobile canvas**: `isMobile` check → 35 particles, no `shadowBlur`
5. **Tailwind v4**: No `tailwind.config.js` — `@import "tailwindcss"` + `@theme {}` in `index.css`
6. **All imports**: `motion/react` not `framer-motion`
7. **No TypeScript `any`**: All component props are explicitly typed interfaces
