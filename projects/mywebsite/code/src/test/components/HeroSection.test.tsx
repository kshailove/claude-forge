import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import HeroSection from '../../components/HeroSection'
import { heroContent } from '../../content/hero'

describe('HeroSection', () => {
  it('renders the hero section with correct id', () => {
    render(<HeroSection />)
    const section = document.getElementById('hero')
    expect(section).toBeInTheDocument()
  })

  it('renders the name as h1', () => {
    render(<HeroSection />)
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent(heroContent.name)
  })

  it('renders the primary CTA link pointing to #about', () => {
    render(<HeroSection />)
    const ctaLinks = screen.getAllByRole('link').filter(
      a => a.getAttribute('href') === '#about'
    )
    expect(ctaLinks.length).toBeGreaterThan(0)
  })

  it('renders the secondary CTA link pointing to #contact', () => {
    render(<HeroSection />)
    const secondaryLinks = screen.getAllByRole('link').filter(
      a => a.getAttribute('href') === '#contact'
    )
    expect(secondaryLinks.length).toBeGreaterThan(0)
  })

  it('renders the CTA labels', () => {
    render(<HeroSection />)
    expect(screen.getByText(heroContent.ctaLabel)).toBeInTheDocument()
    expect(screen.getByText(heroContent.ctaSecondaryLabel)).toBeInTheDocument()
  })

  it('renders the headline text', () => {
    render(<HeroSection />)
    expect(screen.getByText(heroContent.headline)).toBeInTheDocument()
  })

  it('renders the role text', () => {
    render(<HeroSection />)
    expect(screen.getByText(heroContent.role)).toBeInTheDocument()
  })
})
