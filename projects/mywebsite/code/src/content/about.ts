export interface CareerStep {
  label: string
  description: string
}

export interface AboutContent {
  opening: string
  careerArc: CareerStep[]
  bodyParagraph: string
  pullQuote: string
  closing: string
  photoSrc: string
  photoAlt: string
  photoPlaceholderInitials: string
}

export const aboutContent: AboutContent = {
  opening:
    'I did not start my career with the intention of becoming an engineering executive. I started it as an engineer — writing code, debugging systems, learning the craft. Over two decades, I evolved through every layer of the engineering stack: individual contributor, technical lead, engineering manager, director, and ultimately VP Engineering.',

  careerArc: [
    { label: 'Engineer', description: 'Learning to build' },
    { label: 'Architect', description: 'Learning to design systems' },
    { label: 'Engineering Leader', description: 'Learning to grow people' },
    { label: 'Organizational Designer', description: 'Learning to build teams that build' },
    { label: 'Technology Executive', description: 'Learning to connect engineering to business outcomes' },
    { label: 'AI Transformation Leader', description: 'Learning to reimagine engineering in the age of AI' },
  ],

  bodyParagraph:
    'What I discovered along the way is that the most important system an engineering leader builds is not a product. It is an engineering organization — the human system that decides how work flows, how decisions get made, how people grow, and how technology creates durable business leverage.',

  pullQuote:
    'Engineering Leverage: the compounding return you earn when your engineering organization is designed, not just assembled.',

  closing:
    'Today, I partner with founders, CEOs, and boards to build engineering organizations that don\'t just ship features — they compound value. If you are building something ambitious and need an engineering leader who has done this before, I\'d love to talk.',

  photoSrc: '/images/Kumar.jpeg',
  photoAlt: 'Kumar Shailove',
  photoPlaceholderInitials: 'KS',
}
