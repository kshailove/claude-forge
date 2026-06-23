export interface ExperienceRole {
  id: string
  company: string
  title: string
  period: string
  location: string
  startYear: number
  endYear: number | 'Present'
  description: string
  highlights: string[]
  isHighlighted?: boolean
}

export const experienceRoles: ExperienceRole[] = [
  {
    id: 'hiver-vpe',
    company: 'Hiver',
    title: 'VP of Engineering',
    period: 'Mar 2021 – Present',
    location: 'Bangalore, India',
    startYear: 2021,
    endYear: 'Present',
    description:
      'Building the next-generation AI-powered, high-scale omnichannel helpdesk platform. Transformed engineering from reactive execution to a predictable, principles-driven organization delivering continuous business value.',
    highlights: [
      'Built platform engineering and security capabilities from scratch',
      'Established AI-native engineering workflows',
      'Grew and coached engineering leaders across the org',
    ],
    isHighlighted: true,
  },
  {
    id: 'coach-self',
    company: 'Kumar Shailove (Self-employed)',
    title: 'Leadership, Career & Life Coach',
    period: 'Mar 2024 – Present',
    location: 'Remote',
    startYear: 2024,
    endYear: 'Present',
    description:
      'Pro bono coaching and mentoring of aspiring and emerging leaders. Certified Coach from Grow More Avenues.',
    highlights: [
      'Coaching on leadership, career growth, and life decisions',
      'Free sessions via topmate.io/kumar_shailove',
    ],
  },
  {
    id: 'inmobi-dir',
    company: 'InMobi',
    title: 'Director of Engineering — DSP',
    period: 'May 2016 – Mar 2021',
    location: 'Bangalore, India',
    startYear: 2016,
    endYear: 2021,
    description:
      'Set up the Demand Side Platform engineering team from scratch. Grew from 1 to 1 million ad requests per second, few KBs to 10+ terabytes of data per day, supporting $50M ARR.',
    highlights: [
      'Built 25-person DSP engineering team from 0',
      'Led migration from data centre to Microsoft Azure Cloud',
      'Delivered 1M RPS at scale on Azure Cloud Native',
    ],
  },
  {
    id: 'digital-guardian-em',
    company: 'Digital Guardian (via Armor5 Acquisition)',
    title: 'Engineering Manager',
    period: 'Oct 2014 – Apr 2016',
    location: 'Greater Delhi Area, India',
    startYear: 2014,
    endYear: 2016,
    description: 'Continued engineering leadership post-acquisition of Armor5 by Digital Guardian.',
    highlights: [],
  },
  {
    id: 'armor5-em',
    company: 'Armor5 (acquired by Digital Guardian)',
    title: 'Engineering Manager / India Engineering Head',
    period: 'Sep 2013 – Apr 2016',
    location: 'New Delhi, India',
    startYear: 2013,
    endYear: 2016,
    description:
      'Managed end-to-end delivery of server components, cloud infrastructure, and product features. Responsible from ideation through implementation — project management, technical leadership, people management.',
    highlights: [
      'Led software developers, SDETs, and QA engineers',
      'Set up E2E test automation from scratch',
    ],
  },
  {
    id: 'expedia-mgr',
    company: 'Expedia',
    title: 'Manager, Package Discovery Services',
    period: 'Nov 2012 – Sep 2013',
    location: 'Gurugram, India',
    startYear: 2012,
    endYear: 2013,
    description:
      "Built and managed the Package Discovery Services engineering team. Owned development, testing, and operational management of web services backing Expedia's Packages business.",
    highlights: ['Built team from scratch', 'Managed key web services in the PDS family'],
  },
  {
    id: 'adobe-lead',
    company: 'Adobe Systems',
    title: 'Sr. Engineering Lead / Manager',
    period: 'Apr 2006 – Nov 2012',
    location: 'Bangalore / Noida, India',
    startYear: 2006,
    endYear: 2012,
    description:
      "Led engineering for Adobe's License Management Server — RESTful web services enabling licensing features across Adobe desktop applications. Led a team of six engineers.",
    highlights: [
      'LM Server: online serial validation, activation, subscriptions',
      'Cross-platform C/C++ and Perl/Python technologies',
    ],
  },
  {
    id: 'quark-swe',
    company: 'Quark Media House',
    title: 'Software Engineer',
    period: 'Jan 2004 – Apr 2006',
    location: 'Mohali, India',
    startYear: 2004,
    endYear: 2006,
    description:
      'Development and testing of AppleScript feature in QuarkXPress. Single-handedly coded the recovery system for automation tool Eggplant using AppleScript.',
    highlights: [
      'Multiple performance awards: Quark Pro, Quark Pro+',
      'Technologies: C/C++, AppleScript',
    ],
  },
]
