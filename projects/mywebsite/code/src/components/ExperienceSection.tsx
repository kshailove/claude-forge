import { motion } from 'motion/react'
import { useScrollAnimation } from '../hooks/useScrollAnimation'
import TimelineItem from './TimelineItem'
import { experienceRoles } from '../content/timeline'

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
}

export default function ExperienceSection() {
  const anim = useScrollAnimation()

  return (
    <motion.section
      id="experience"
      className="py-24 md:py-32 px-6 md:px-12 bg-[var(--color-surface)]"
      {...anim}
    >
      <div className="max-w-7xl mx-auto">
        <div className="mb-16">
          <p className="font-mono text-xs text-[var(--color-accent)] uppercase tracking-widest mb-4">
            Experience
          </p>
          <h2 className="font-serif text-4xl md:text-5xl text-[var(--color-text)] max-w-2xl leading-tight">
            20 Years of Engineering Leadership
          </h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div>
            <p className="font-sans text-base text-[var(--color-muted)] leading-relaxed mb-12">
              From writing code at Quark in 2004 to leading engineering organizations at Hiver
              today — a career built on compounding technical depth into strategic business impact.
            </p>
          </div>
        </div>

        {/* Timeline */}
        <div className="relative">
          {/* Vertical connector line */}
          <div className="absolute left-1.5 top-0 bottom-0 w-px bg-[var(--color-muted)]/20" />

          <motion.ol
            className="flex flex-col list-none p-0 m-0"
            variants={containerVariants}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: '-100px' }}
          >
            {experienceRoles.map((role, index) => (
              <TimelineItem key={role.id} role={role} index={index} />
            ))}
          </motion.ol>
        </div>
      </div>
    </motion.section>
  )
}
