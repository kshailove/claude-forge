import { useState } from 'react'
import { motion } from 'motion/react'
import { useLenis } from 'lenis/react'
import { navItems } from '../content/nav'

export default function NavigationBar() {
  const [visible, setVisible] = useState(false)
  const [activeSection, setActiveSection] = useState<string>('')

  const lenis = useLenis(({ scroll }) => {
    setVisible(scroll > window.innerHeight * 0.8)

    // Scroll-spy: find which section occupies the viewport center
    const sectionIds = ['hero', 'about', 'philosophy', 'experience', 'hiver', 'contact']
    const viewportMid = window.innerHeight / 2
    let matched = ''

    for (const id of sectionIds) {
      const el = document.getElementById(id)
      if (!el) continue
      const rect = el.getBoundingClientRect()
      if (rect.top <= viewportMid && rect.bottom >= viewportMid) {
        matched = id
        break
      }
    }

    setActiveSection(matched)
  })

  const handleNavClick = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    e.preventDefault()
    const sectionId = href.slice(1)
    if (sectionId === 'hero') {
      lenis?.scrollTo(0, { offset: 0 })
      return
    }
    const el = document.getElementById(sectionId)
    if (el && lenis) {
      lenis.scrollTo(el, { offset: -80 })
    } else if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <motion.nav
      aria-label="Main navigation"
      className="fixed top-0 left-0 right-0 z-40 bg-[var(--color-bg)]/90 backdrop-blur-sm border-b border-white/5"
      animate={{ opacity: visible ? 1 : 0, y: visible ? 0 : -100 }}
      transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      style={{ pointerEvents: visible ? 'auto' : 'none' }}
    >
      <div className="max-w-7xl mx-auto px-6 md:px-8 flex items-center justify-between h-16">
        <a
          href="#hero"
          className="font-serif text-lg text-[var(--color-text)] hover:text-[var(--color-accent)] transition-colors"
          onClick={(e) => {
            e.preventDefault()
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
        >
          KS
        </a>

        <ul className="hidden md:flex items-center gap-8 list-none m-0 p-0">
          {navItems.map((item) => {
            const sectionId = item.href.slice(1)
            const isActive = activeSection === sectionId
            return (
              <li key={item.href}>
                <a
                  href={item.href}
                  onClick={(e) => handleNavClick(e, item.href)}
                  className={`font-mono text-sm transition-colors ${
                    isActive
                      ? 'text-[var(--color-accent)]'
                      : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                  }`}
                >
                  {item.label}
                </a>
              </li>
            )
          })}
        </ul>

        {/* Mobile: compact scrollable nav */}
        <div className="md:hidden flex items-center gap-4 overflow-x-auto">
          {navItems.map((item) => {
            const sectionId = item.href.slice(1)
            const isActive = activeSection === sectionId
            return (
              <a
                key={item.href}
                href={item.href}
                onClick={(e) => handleNavClick(e, item.href)}
                className={`font-mono text-xs whitespace-nowrap transition-colors ${
                  isActive
                    ? 'text-[var(--color-accent)]'
                    : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                }`}
              >
                {item.label}
              </a>
            )
          })}
        </div>
      </div>
    </motion.nav>
  )
}
