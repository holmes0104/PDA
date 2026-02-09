import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'PDA - LLM-Ready Product Content Generator | Vaisala',
  description: 'Generate LLM-ready product content packs from PDF brochures and datasheets. Designed for Vaisala by Thanh Nguyen (Holmes).',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  )
}
