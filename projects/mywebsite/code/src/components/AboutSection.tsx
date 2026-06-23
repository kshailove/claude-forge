import { useState } from 'react'
import { motion } from 'motion/react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import { aboutContent } from '../content/about'

export default function AboutSection() {
  const [imgError, setImgError] = useState(false)
  const anim = useScrollAnimation()

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 },
    },
  }

  const stepVariants = {
    hidden: { opacity: 0, x: -16 },
    show: {
      opacity: 1,
      x: 0,
      transition: { duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] as [number, number, number, number] },
    },
  }

  return (
    <motion.section
      id="about"
      className="py-24 md:py-32 px-6 md:px-12 max-w-7xl mx-auto"
      {...anim}
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-start">
        {/* Left: Photo + career arc */}
        <div className="flex flex-col gap-8">
          {/* Photo */}
          <div className="relative">
            {!imgError ? (
              <img
                src={aboutContent.photoSrc}
                alt={aboutContent.photoAlt}
                onError={() => setImgError(true)}
                className="w-48 h-48 md:w-64 md:h-64 rounded-2xl object-cover grayscale hover:grayscale-0 transition-all duration-500"
              />
            ) : (
              <div
                className="w-48 h-48 md:w-64 md:h-64 rounded-2xl bg-[var(--color-surface)] flex items-center justify-center border border-white/10"
                aria-label={`Placeholder for ${aboutContent.photoAlt}`}
              >
                <span className="font-serif text-5xl text-[var(--color-accent)]">
                  {aboutContent.photoPlaceholderInitials}
                </span>
              </div>
            )}

            {/* Decorative accent */}
            <div className="absolute -bottom-3 -right-3 w-24 h-24 rounded-2xl border-2 border-[var(--color-accent)]/30 -z-10" />
          </div>

          {/* Career arc steps */}
          <div>
            <h3 className="font-mono text-xs text-[var(--color-muted)] uppercase tracking-widest mb-6">
              20-Year Journey
            </h3>
            <motion.ol
              className="flex flex-col gap-3 list-none p-0 m-0"
              variants={containerVariants}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: '-100px' }}
            >
              {aboutContent.careerArc.map((step, i) => (
                <motion.li
                  key={i}
                  variants={stepVariants}
                  className="flex items-baseline gap-3"
                >
                  <span className="font-mono text-xs text-[var(--color-accent)] w-4 shrink-0">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <span className="font-serif text-base text-[var(--color-text)]">
                      {step.label}
                    </span>
                    <span className="font-mono text-xs text-[var(--color-muted)] ml-2">
                      — {step.description}
                    </span>
                  </div>
                </motion.li>
              ))}
            </motion.ol>
          </div>
        </div>

        {/* Right: Narrative prose */}
        <div className="flex flex-col gap-6">
          <div>
            <h2 className="font-serif text-4xl md:text-5xl text-[var(--color-text)] mb-8 leading-tight">
              The Making of an Engineering Executive
            </h2>
          </div>

          <p className="font-sans text-base md:text-lg text-[var(--color-muted)] leading-relaxed">
            {aboutContent.opening}
          </p>

          <p className="font-sans text-base md:text-lg text-[var(--color-muted)] leading-relaxed">
            {aboutContent.bodyParagraph}
          </p>

          <blockquote className="border-l-2 border-[var(--color-accent)] pl-6 py-2 my-4">
            <p className="font-serif italic text-xl md:text-2xl text-[var(--color-text)] leading-snug">
              "Engineering Leverage: the compounding return you earn when your engineering
              organization is designed, not just assembled."
            </p>
          </blockquote>

          <p className="font-sans text-base md:text-lg text-[var(--color-muted)] leading-relaxed">
            {aboutContent.closing}
          </p>
        </div>
      </div>
    </motion.section>
  )
}
