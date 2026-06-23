import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import NavigationBar from '../../components/NavigationBar'
import { navItems } from '../../content/nav'

describe('NavigationBar', () => {
  it('renders the nav element with correct aria-label', () => {
    render(<NavigationBar />)
    const nav = screen.getByRole('navigation', { name: /main navigation/i })
    expect(nav).toBeInTheDocument()
  })

  it('renders the KS logo link', () => {
    render(<NavigationBar />)
    const logoLink = screen.getAllByRole('link').find(a => a.textContent === 'KS')
    expect(logoLink).toBeDefined()
    expect(logoLink).toHaveAttribute('href', '#hero')
  })

  it('renders all nav items as links', () => {
    render(<NavigationBar />)
    // Each nav item appears twice (desktop ul + mobile div), so we check unique hrefs
    for (const item of navItems) {
      const links = screen.getAllByRole('link', { name: item.label })
      expect(links.length).toBeGreaterThan(0)
    }
  })

  it('nav has 6 navigation items', () => {
    render(<NavigationBar />)
    // navItems has 6 items, each rendered twice (desktop + mobile)
    // Check by counting unique hrefs from nav items
    expect(navItems).toHaveLength(6)
    for (const item of navItems) {
      const links = screen.getAllByRole('link', { name: item.label })
      expect(links.length).toBeGreaterThanOrEqual(1)
    }
  })

  it('first nav item links to #hero', () => {
    render(<NavigationBar />)
    const homeLinks = screen.getAllByRole('link', { name: 'Home' })
    expect(homeLinks[0]).toHaveAttribute('href', '#hero')
  })

  it('nav starts with pointer-events none (not visible until scroll)', () => {
    render(<NavigationBar />)
    const nav = screen.getByRole('navigation', { name: /main navigation/i })
    // Navigation starts hidden (visible=false), so pointerEvents should be 'none'
    expect(nav).toHaveStyle({ pointerEvents: 'none' })
  })
})
