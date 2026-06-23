import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ExperienceSection from '../../components/ExperienceSection'
import { experienceRoles } from '../../content/timeline'

describe('ExperienceSection', () => {
  it('renders the experience section with correct id', () => {
    render(<ExperienceSection />)
    const section = document.getElementById('experience')
    expect(section).toBeInTheDocument()
  })

  it('renders the section heading', () => {
    render(<ExperienceSection />)
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('20 Years of Engineering Leadership')
  })

  it('renders timeline as an ordered list', () => {
    render(<ExperienceSection />)
    // Multiple lists exist (the main ol + ul highlights inside each li), use getAllByRole
    const lists = screen.getAllByRole('list')
    // The main ordered list is among them
    const orderedList = lists.find(l => l.tagName === 'OL')
    expect(orderedList).toBeInTheDocument()
  })

  it('renders 8 timeline items as list items', () => {
    render(<ExperienceSection />)
    // TimelineItem renders as motion.li elements
    const items = screen.getAllByRole('listitem')
    // Filter to timeline items (they have aria-label starting with "Role")
    const roleItems = items.filter(item =>
      item.getAttribute('aria-label')?.startsWith('Role')
    )
    expect(roleItems).toHaveLength(8)
  })

  it('first timeline item is Hiver', () => {
    render(<ExperienceSection />)
    const firstItem = screen.getByRole('listitem', { name: /role 1: vp of engineering at hiver/i })
    expect(firstItem).toBeInTheDocument()
  })

  it('last timeline item is Quark Media House', () => {
    render(<ExperienceSection />)
    const lastItem = screen.getByRole('listitem', { name: /role 8:.*quark media house/i })
    expect(lastItem).toBeInTheDocument()
  })

  it('renders all company names', () => {
    render(<ExperienceSection />)
    expect(screen.getByText('Hiver')).toBeInTheDocument()
    expect(screen.getByText('Quark Media House')).toBeInTheDocument()
  })

  it('timeline has correct number of roles in data', () => {
    expect(experienceRoles).toHaveLength(8)
    expect(experienceRoles[0].company).toBe('Hiver')
    expect(experienceRoles[experienceRoles.length - 1].company).toBe('Quark Media House')
  })
})
