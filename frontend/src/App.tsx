import './App.css'
import { useCallback, useEffect, useMemo } from 'react'

import { AppShell } from './app/components/AppShell'
import { useAuthStatus } from './app/hooks/useAuthStatus'
import { usePathname } from './app/hooks/usePathname'
import { resolvePage } from './app/routing/resolvePage'
import { useRouteGuards } from './app/routing/useRouteGuards'
import { clearAuthentication } from './auth'
import { openGoogleDriveWorkspace } from './drive'
import { navigate } from './navigation'
import { LAST_PROJECT_PATH_STORAGE_KEY } from './pages/adminPromptsStorage'

function App() {
  const authStatus = useAuthStatus()
  const pathname = usePathname()

  useRouteGuards(pathname, authStatus)

  const pageContent = useMemo(() => resolvePage({ pathname, authStatus }), [pathname, authStatus])

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    if (pathname.startsWith('/projects')) {
      try {
        window.sessionStorage.setItem(LAST_PROJECT_PATH_STORAGE_KEY, pathname)
      } catch (storageError) {
        console.error('프로젝트 경로를 저장하지 못했습니다.', storageError)
      }
    }
  }, [pathname])

  const handleLogout = useCallback(() => {
    clearAuthentication()
    navigate('/', { replace: true })
  }, [])

  const handleOpenDrive = useCallback(() => {
    openGoogleDriveWorkspace()
  }, [])

  const handleOpenAdmin = useCallback(() => {
    navigate('/admin/prompts')
  }, [])

  return (
    <AppShell
      isAuthenticated={authStatus === 'authenticated'}
      currentPath={pathname}
      onLogout={handleLogout}
      onOpenDrive={handleOpenDrive}
      onNavigateAdmin={handleOpenAdmin}
    >
      {pageContent}
    </AppShell>
  )
}

export default App
