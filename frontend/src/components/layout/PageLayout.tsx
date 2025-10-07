import type { PropsWithChildren } from 'react'

interface PageLayoutProps {
  variant?: 'default' | 'wide'
  className?: string
}

export function PageLayout({ children, variant = 'default', className }: PropsWithChildren<PageLayoutProps>) {
  const classes = ['page', variant === 'wide' ? 'page--wide' : '', className].filter(Boolean).join(' ')

  return <div className={classes}>{children}</div>
}
