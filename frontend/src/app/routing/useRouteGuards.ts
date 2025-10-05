import { useEffect } from 'react'

import type { AuthStatus } from '../../auth'
import { navigate } from '../../navigation'

const PROJECT_PATH_PATTERN = /^\/projects\/(.+)$/
const PROJECTS_ROOT_PATH = '/projects'
const LEGACY_DRIVE_PATH = '/drive'
const PROMPT_ADMIN_PATH = '/admin/prompts/feature-list'

function isKnownPathname(pathname: string): boolean {
  if (
    pathname === '/' ||
    pathname === PROJECTS_ROOT_PATH ||
    pathname === LEGACY_DRIVE_PATH ||
    pathname === PROMPT_ADMIN_PATH
  ) {
    return true
  }
  return PROJECT_PATH_PATTERN.test(pathname)
}

export function useRouteGuards(pathname: string, authStatus: AuthStatus) {
  useEffect(() => {
    if (!isKnownPathname(pathname)) {
      navigate('/', { replace: true })
    }
  }, [pathname])

  useEffect(() => {
    if (authStatus !== 'authenticated' && pathname !== '/') {
      navigate('/', { replace: true })
    }
  }, [authStatus, pathname])

  useEffect(() => {
    if (pathname === LEGACY_DRIVE_PATH) {
      navigate(PROJECTS_ROOT_PATH, { replace: true })
      return
    }

    if (authStatus === 'authenticated' && pathname === '/') {
      navigate(PROJECTS_ROOT_PATH, { replace: true })
    }
  }, [authStatus, pathname])
}
