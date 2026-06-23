import { motion } from 'motion/react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import PhilosophyCard from './PhilosophyCard'
import { philosophyPillars } from '../content/philosophy'

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.12 },
  },
}

export default function PhilosophySection() {
  const anim = useScrollAnimation()

  return (
    <motion.section
      id="philosophy"
      className="py-24 md:py-32 px-6 md:px-12 bg-[var(--color-bg)]"
      {...anim}
    >
      <div className="max-w-7xl mx-auto">
        <div className="mb-16">
          <p className="font-mono text-xs text-[var(--color-accent)] uppercase tracking-widest mb-4">
            Philosophy
          </p>
          <h2 className="font-serif text-4xl md:text-5xl text-[var(--color-text)] max-w-2xl leading-tight">
            How I Think About Leadership, Technology, and AI
          </h2>
        </div>

        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
          variants={containerVariants}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-100px' }}
        >
          {philosophyPillars.map((pillar) => (
            <PhilosophyCard key={pillar.id} pillar={pillar} />
          ))}
        </motion.div>
      </div>
    </motion.section>
  )
}
