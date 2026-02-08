import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'PDA - Product Discoverability Auditor',
  description: 'Audit PDF brochures and product pages for LLM-readiness',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
