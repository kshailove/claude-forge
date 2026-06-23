import { motion, useScroll, useTransform, useReducedMotion } from 'motion/react'
import NetworkCanvas from './NetworkCanvas'
import { heroContent } from '../content/hero'

export default function HeroSection() {
  const { scrollY } = useScroll()
  const prefersReducedMotion = useReducedMotion()

  // Canvas parallax: 0.3× scroll speed
  const canvasY = useTransform(scrollY, [0, 600], [0, prefersReducedMotion ? 0 : -180])

  const makeEntryProps = (delay: number) => {
    if (prefersReducedMotion) {
      return {
        initial: { opacity: 1, y: 0 },
        animate: { opacity: 1, y: 0 },
      }
    }
    return {
      initial: { opacity: 0, y: 30 },
      animate: { opacity: 1, y: 0 },
      transition: {
        duration: 0.7,
        delay,
        ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number],
      },
    }
  }

  return (
    <section
      id="hero"
      className="relative min-h-screen overflow-hidden bg-[var(--color-bg)]"
    >
      {/* Canvas background with parallax */}
      <motion.div style={{ y: canvasY }} className="absolute inset-0">
        <NetworkCanvas />
      </motion.div>

      {/* Gradient overlay for text legibility */}
      <div className="absolute inset-0 bg-gradient-to-b from-[var(--color-bg)]/20 via-transparent to-[var(--color-bg)]/60 pointer-events-none" />

      {/* Content */}
      <div className="relative z-10 flex flex-col justify-center min-h-screen px-6 md:px-12 max-w-7xl mx-auto">
        <div className="max-w-4xl">
          {/* Name */}
          <motion.div {...makeEntryProps(0)}>
            <h1 className="font-serif text-6xl md:text-7xl lg:text-8xl text-[var(--color-text)] leading-tight mb-4">
              {heroContent.name}
            </h1>
          </motion.div>

          {/* Role */}
          <motion.div {...makeEntryProps(0.08)}>
            <p className="font-mono text-sm md:text-base text-[var(--color-accent)] mb-8 tracking-wide">
              {heroContent.role}
            </p>
          </motion.div>

          {/* Headline */}
          <motion.div {...makeEntryProps(0.15)}>
            <p className="font-serif text-2xl md:text-3xl lg:text-4xl text-[var(--color-text)] leading-snug mb-6 max-w-3xl">
              {heroContent.headline}
            </p>
          </motion.div>

          {/* Tagline */}
          <motion.div {...makeEntryProps(0.22)}>
            <p className="font-mono text-sm md:text-base text-[var(--color-muted)] mb-12 tracking-wide">
              {heroContent.tagline}
            </p>
          </motion.div>

          {/* CTA */}
          <motion.div {...makeEntryProps(0.3)}>
            <a
              href={heroContent.ctaHref}
              className="inline-flex items-center gap-2 px-8 py-4 bg-[var(--color-accent)] text-[var(--color-bg)] font-mono text-sm font-medium rounded-full hover:opacity-90 transition-opacity focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
            >
              {heroContent.ctaLabel}
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 8H13M13 8L9 4M13 8L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </a>
            <a
              href="#about"
              onClick={(e) => {
                e.preventDefault()
                document.getElementById('about')?.scrollIntoView({ behavior: 'smooth' })
              }}
              className="inline-flex items-center gap-2 ml-4 px-8 py-4 border border-white/20 text-[var(--color-text)] font-mono text-sm rounded-full hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
            >
              Explore My Work
            </a>
          </motion.div>
        </div>

        {/* Scroll indicator */}
        <motion.div
          className="absolute bottom-8 left-1/2 -translate-x-1/2"
          {...(prefersReducedMotion
            ? {}
            : {
                animate: { y: [0, 10, 0] },
                transition: { duration: 2, repeat: Infinity, ease: 'easeInOut' },
              })}
        >
          <svg
            width="24"
            height="40"
            viewBox="0 0 24 40"
            fill="none"
            aria-hidden="true"
            className="text-[var(--color-muted)]"
          >
            <rect x="1" y="1" width="22" height="38" rx="11" stroke="currentColor" strokeWidth="1.5" />
            <rect
              x="11"
              y="8"
              width="2"
              height="8"
              rx="1"
              fill="currentColor"
              className="opacity-60"
            />
          </svg>
        </motion.div>
      </div>
    </section>
  )
}
