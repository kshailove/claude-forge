import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ContactSection from '../../components/ContactSection'
import { contactContent } from '../../content/contact'

describe('ContactSection', () => {
  it('renders the contact section with correct id', () => {
    render(<ContactSection />)
    const section = document.getElementById('contact')
    expect(section).toBeInTheDocument()
  })

  it('renders the heading', () => {
    render(<ContactSection />)
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(contactContent.heading)
  })

  it('renders an email link for kumar@grexit.com', () => {
    render(<ContactSection />)
    const emailLink = screen.getByRole('link', { name: /kumar@grexit\.com/i })
    expect(emailLink).toHaveAttribute('href', `mailto:${contactContent.email}`)
  })

  it('renders the LinkedIn link', () => {
    render(<ContactSection />)
    const linkedinLink = screen.getByRole('link', { name: /linkedin profile/i })
    expect(linkedinLink).toHaveAttribute('href', contactContent.linkedinUrl)
  })

  it('renders the Topmate link', () => {
    render(<ContactSection />)
    const topmateLink = screen.getByRole('link', { name: /book a free coaching session/i })
    expect(topmateLink).toHaveAttribute('href', contactContent.topmateUrl)
  })

  it('renders the copyright notice with 2026', () => {
    render(<ContactSection />)
    expect(screen.getByText(/© 2026 Kumar Shailove/)).toBeInTheDocument()
  })
})
