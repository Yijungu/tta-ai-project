import { useEffect, useMemo, useState } from 'react'

import { DRIVE_AUTH_STORAGE_KEY, getBackendUrl } from '../config'
import { DriveActionButton } from '../components/drive/DriveActionButton'
import { DriveAccountBadge } from '../components/drive/DriveAccountBadge'
import { DriveCard } from '../components/drive/DriveCard'
import { DriveEmptyState } from '../components/drive/DriveEmptyState'
import { DriveProjectsList } from '../components/drive/DriveProjectsList'
import { PageHeader } from '../components/layout/PageHeader'
import { PageLayout } from '../components/layout/PageLayout'
import { ProjectCreationModal } from '../components/ProjectCreationModal'
import type { DriveProject, DriveSetupResponse } from '../types/drive'
import { storeDriveRootFolderId } from '../drive'

type ViewState = 'loading' | 'ready' | 'error'

export function DriveSetupPage() {
  const backendUrl = useMemo(() => getBackendUrl(), [])
  const [viewState, setViewState] = useState<ViewState>('loading')
  const [errorMessage, setErrorMessage] = useState('')
  const [result, setResult] = useState<DriveSetupResponse | null>(null)
  const [reloadIndex, setReloadIndex] = useState(0)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [failureMessage, setFailureMessage] = useState<string | null>(null)
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null)

  useEffect(() => {
    try {
      sessionStorage.removeItem(DRIVE_AUTH_STORAGE_KEY)
    } catch (error) {
      console.error('failed to clear auth message', error)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let isMounted = true

    async function ensureFolder() {
      setViewState('loading')
      setErrorMessage('')

      try {
        const response = await fetch(`${backendUrl}/drive/gs/setup`, {
          method: 'POST',
          signal: controller.signal,
        })

        if (!response.ok) {
          let detail = 'Google Drive 상태를 확인하는 중 오류가 발생했습니다.'
          try {
            const payload = await response.json()
            if (payload && typeof payload.detail === 'string') {
              detail = payload.detail
            }
          } catch {
            const text = await response.text()
            if (text) {
              detail = text
            }
          }
          throw new Error(detail)
        }

        const data = (await response.json()) as DriveSetupResponse
        if (!isMounted) {
          return
        }
        setResult(data)
        storeDriveRootFolderId(data.folderId)
        setViewState('ready')
      } catch (error) {
        if (!isMounted || controller.signal.aborted) {
          return
        }

        const fallback =
          error instanceof Error
            ? error.message
            : '알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'
        setErrorMessage(fallback)
        setViewState('error')
      }
    }

    ensureFolder()

    return () => {
      isMounted = false
      controller.abort()
    }
  }, [backendUrl, reloadIndex])

  const handleRetry = () => {
    setReloadIndex((index) => index + 1)
  }

  const handleOpenModal = () => {
    setSuccessMessage(null)
    setFailureMessage(null)
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const handleProjectCreated = () => {
    setSuccessMessage('새 프로젝트 폴더를 생성했습니다.')
    setFailureMessage(null)
    setReloadIndex((index) => index + 1)
  }

  const handleProjectDeleted = async (project: DriveProject) => {
    if (deletingProjectId) {
      return
    }

    const confirmed = window.confirm(
      `정말로 '${project.name}' 프로젝트를 삭제하시겠습니까? 삭제 후에는 복구할 수 없습니다.`,
    )

    if (!confirmed) {
      return
    }

    setSuccessMessage(null)
    setFailureMessage(null)
    setDeletingProjectId(project.id)

    try {
      const response = await fetch(`${backendUrl}/drive/projects/${project.id}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        let detail = `'${project.name}' 프로젝트를 삭제하는 중 오류가 발생했습니다.`
        try {
          const payload = await response.json()
          if (payload && typeof payload.detail === 'string') {
            detail = payload.detail
          }
        } catch {
          const text = await response.text()
          if (text) {
            detail = text
          }
        }
        throw new Error(detail)
      }

      setSuccessMessage(`'${project.name}' 프로젝트를 삭제했습니다.`)
      setReloadIndex((index) => index + 1)
    } catch (error) {
      const fallback =
        error instanceof Error
          ? error.message
          : '프로젝트 삭제 중 알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'
      setFailureMessage(fallback)
    } finally {
      setDeletingProjectId(null)
    }
  }

  const projects = result?.projects ?? []
  const folderName = result?.folderName ?? 'gs'

  const banner = (() => {
    if (failureMessage) {
      return { message: failureMessage, variant: 'error' as const }
    }
    if (result?.folderCreated) {
      return {
        message: `'${result.folderName}' 폴더를 Google Drive에 새로 만들었습니다.`,
        variant: 'success' as const,
      }
    }
    if (successMessage) {
      return { message: successMessage, variant: 'success' as const }
    }
    return null
  })()

  return (
    <PageLayout>
      <div className="drive-page">
        <PageHeader eyebrow="Google Drive 프로젝트" title="프로젝트" />

        {result?.account && (
          <DriveAccountBadge
            displayName={result.account.displayName}
            email={result.account.email}
          />
        )}

        {viewState === 'loading' && (
          <DriveCard variant="loading" ariaBusy>
            <div className="drive-card__spinner" aria-hidden="true" />
            <p className="drive-card__loading-text">Google Drive에서 폴더 상태를 확인하는 중입니다…</p>
          </DriveCard>
        )}

        {viewState === 'error' && (
          <DriveCard variant="error" role="alert">
            <h2 className="drive-card__title">Drive 상태를 불러오지 못했습니다</h2>
            <p className="drive-card__description">{errorMessage}</p>
            <DriveActionButton onClick={handleRetry}>다시 시도</DriveActionButton>
          </DriveCard>
        )}

        {viewState === 'ready' && result && (
          <DriveCard banner={banner?.message ?? null} bannerVariant={banner?.variant}>
            <h2 className="drive-card__title">프로젝트 선택</h2>
            <p className="drive-card__description">
              {projects.length > 0
                ? '사용할 프로젝트를 선택하거나 새 프로젝트를 생성해 주세요.'
                : `현재 '${folderName}' 폴더 안에 프로젝트가 없습니다.`}
            </p>

            {projects.length > 0 ? (
              <>
                <DriveProjectsList
                  projects={projects}
                  onDeleteProject={handleProjectDeleted}
                  deletingProjectId={deletingProjectId}
                />
                <DriveActionButton variant="compact" onClick={handleOpenModal}>
                  새 프로젝트 만들기
                </DriveActionButton>
              </>
            ) : (
              <DriveEmptyState onCreateClick={handleOpenModal} />
            )}

            <div className="drive-page__actions" aria-hidden="true" />
          </DriveCard>
        )}
      </div>

      <ProjectCreationModal
        open={isModalOpen}
        onClose={handleCloseModal}
        onSuccess={handleProjectCreated}
        folderId={result?.folderId}
        backendUrl={backendUrl}
      />
    </PageLayout>
  )
}
