import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import HiverSection from '../../components/HiverSection'
import { hiverTransformations } from '../../content/hiver'

describe('HiverSection', () => {
  it('renders the hiver section with correct id', () => {
    render(<HiverSection />)
    const section = document.getElementById('hiver')
    expect(section).toBeInTheDocument()
  })

  it('renders the section heading', () => {
    render(<HiverSection />)
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Seven Transformations at Hiver')
  })

  it('renders 7 transformation cards', () => {
    render(<HiverSection />)
    // TransformationCard renders as motion.div with aria-label="Transformation N: title"
    const cards = screen.getAllByRole('generic').filter(el =>
      el.getAttribute('aria-label')?.startsWith('Transformation')
    )
    expect(cards).toHaveLength(7)
  })

  it('first transformation contains "Predictable Execution"', () => {
    render(<HiverSection />)
    const firstCard = screen.getByRole('generic', { name: /transformation 1:.*predictable execution/i })
    expect(firstCard).toBeInTheDocument()
  })

  it('last transformation contains "Building Leaders"', () => {
    render(<HiverSection />)
    const lastCard = screen.getByRole('generic', { name: /transformation 7:.*building leaders/i })
    expect(lastCard).toBeInTheDocument()
  })

  it('renders a link to hiverhq.com', () => {
    render(<HiverSection />)
    const hiverLink = screen.getByRole('link', { name: /hiverhq\.com/i })
    expect(hiverLink).toHaveAttribute('href', 'https://hiverhq.com')
  })

  it('hiverTransformations data has 7 items', () => {
    expect(hiverTransformations).toHaveLength(7)
  })

  it('first transformation title contains "Predictable Execution"', () => {
    expect(hiverTransformations[0].title).toContain('Predictable Execution')
  })

  it('last transformation title contains "Building Leaders"', () => {
    expect(hiverTransformations[hiverTransformations.length - 1].title).toContain('Building Leaders')
  })
})
