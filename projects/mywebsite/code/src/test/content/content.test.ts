import { describe, it, expect } from 'vitest'
import { heroContent } from '../../content/hero'
import { navItems } from '../../content/nav'
import { experienceRoles } from '../../content/timeline'
import { hiverTransformations } from '../../content/hiver'
import { philosophyPillars } from '../../content/philosophy'
import { aboutContent } from '../../content/about'

describe('content module', () => {
  it('heroContent.ctaHref is #about', () => {
    expect(heroContent.ctaHref).toBe('#about')
  })

  it('heroContent.ctaSecondaryHref is #contact', () => {
    expect(heroContent.ctaSecondaryHref).toBe('#contact')
  })

  it('navItems has 6 items', () => {
    expect(navItems).toHaveLength(6)
  })

  it('navItems[0].href is #hero', () => {
    expect(navItems[0].href).toBe('#hero')
  })

  it('timeline has 8 roles', () => {
    expect(experienceRoles).toHaveLength(8)
  })

  it('hiverTransformations has 7 items', () => {
    expect(hiverTransformations).toHaveLength(7)
  })

  it('philosophyPillars has 3 items', () => {
    expect(philosophyPillars).toHaveLength(3)
  })

  it('aboutContent.pullQuote is a non-empty string', () => {
    expect(typeof aboutContent.pullQuote).toBe('string')
    expect(aboutContent.pullQuote.length).toBeGreaterThan(0)
  })
})
