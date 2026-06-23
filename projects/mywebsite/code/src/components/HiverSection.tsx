import { motion } from 'motion/react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import TransformationCard from './TransformationCard'
import { hiverTransformations, hiverIntro } from '../content/hiver'

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
}

export default function HiverSection() {
  const anim = useScrollAnimation()

  return (
    <motion.section
      id="hiver"
      className="py-24 md:py-32 px-6 md:px-12 bg-[var(--color-bg)]"
      {...anim}
    >
      <div className="max-w-7xl mx-auto">
        <div className="mb-16">
          <p className="font-mono text-xs text-[var(--color-accent)] uppercase tracking-widest mb-4">
            Hiver Case Study
          </p>
          <h2 className="font-serif text-4xl md:text-5xl text-[var(--color-text)] max-w-3xl leading-tight mb-8">
            Seven Transformations at Hiver
          </h2>
          <p className="font-sans text-base md:text-lg text-[var(--color-muted)] max-w-3xl leading-relaxed">
            {hiverIntro}
          </p>
        </div>

        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
          variants={containerVariants}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-100px' }}
        >
          {hiverTransformations.map((t, i) => (
            <TransformationCard key={t.id} transformation={t} index={i + 1} />
          ))}
        </motion.div>

        {/* Hiver company link */}
        <div className="mt-12 pt-8 border-t border-white/10">
          <p className="font-mono text-sm text-[var(--color-muted)]">
            Learn more about Hiver at{' '}
            <a
              href="https://hiverhq.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--color-accent)] hover:underline"
            >
              hiverhq.com
            </a>
          </p>
        </div>
      </div>
    </motion.section>
  )
}
