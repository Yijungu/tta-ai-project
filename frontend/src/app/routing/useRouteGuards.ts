import { useEffect } from 'react'

import type { AuthStatus } from '../../auth'
import { navigate } from '../../navigation'
import { normalizePathname } from './normalizePathname'

const PROJECT_PATH_PATTERN = /^\/projects\/(.+)$/
const PROJECTS_ROOT_PATH = '/projects'
const LEGACY_DRIVE_PATH = '/drive'
const PROMPT_ADMIN_PATH = '/admin/prompts/feature-list'

function normalizePathname(pathname: string): string {
  if (!pathname) {
    return '/'
  }

  const [normalized] = pathname.split(/[?#]/)
  if (!normalized) {
    return '/'
  }

  return normalized.startsWith('/') ? normalized : `/${normalized}`
}

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
  const normalizedPathname = normalizePathname(pathname)

  useEffect(() => {
    if (!isKnownPathname(normalizedPathname)) {
      navigate('/', { replace: true })
    }
  }, [normalizedPathname])

  useEffect(() => {
    if (authStatus !== 'authenticated' && normalizedPathname !== '/') {
      navigate('/', { replace: true })
    }
  }, [authStatus, normalizedPathname])

  useEffect(() => {
    if (normalizedPathname === LEGACY_DRIVE_PATH) {
      navigate(PROJECTS_ROOT_PATH, { replace: true })
      return
    }

    if (authStatus === 'authenticated' && normalizedPathname === '/') {
      navigate(PROJECTS_ROOT_PATH, { replace: true })
    }
  }, [authStatus, normalizedPathname])
}
