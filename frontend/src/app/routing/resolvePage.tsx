import type { ReactNode } from 'react'

import type { AuthStatus } from '../../auth'
import { DriveSetupPage } from '../../pages/DriveSetupPage'
import { LoginPage } from '../../pages/LoginPage'
import { ProjectManagementPage } from '../../pages/ProjectManagementPage'
import { PromptAdminPage } from '../../pages/PromptAdminPage'
import { normalizePathname } from './normalizePathname'

const PROJECT_PATH_PATTERN = /^\/projects\/([^/]+)$/
const PROJECTS_ROOT_PATH = '/projects'
const LEGACY_DRIVE_PATH = '/drive'
const PROMPT_ADMIN_PATH = '/admin/prompts/feature-list'

interface ResolvePageOptions {
  pathname: string
  authStatus: AuthStatus
}

export function resolvePage({ pathname, authStatus }: ResolvePageOptions): ReactNode {
  const normalizedPathname = normalizePathname(pathname)

  if (authStatus !== 'authenticated') {
    return <LoginPage />
  }

  if (normalizedPathname === PROJECTS_ROOT_PATH || normalizedPathname === LEGACY_DRIVE_PATH) {
    return <DriveSetupPage />
  }

  if (normalizedPathname === PROMPT_ADMIN_PATH) {
    return <PromptAdminPage />
  }

  const projectMatch = normalizedPathname.match(PROJECT_PATH_PATTERN)
  if (projectMatch) {
    return <ProjectManagementPage projectId={decodeURIComponent(projectMatch[1])} />
  }

  return <LoginPage />
}
