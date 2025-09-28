import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import { getBackendUrl } from '../config'
import { Modal } from './Modal'
import { FileUploader, FILE_TYPE_OPTIONS, ALL_FILE_TYPES } from './FileUploader'
import type { FileType } from './FileUploader'

interface ProjectCreationModalProps {
  open: boolean
  folderId?: string
  onClose: () => void
  onSuccess?: () => void
  backendUrl?: string
}

const PDF_ONLY: FileType[] = ['pdf']

export function ProjectCreationModal({
  open,
  folderId,
  onClose,
  onSuccess,
  backendUrl,
}: ProjectCreationModalProps) {
  const [files, setFiles] = useState<File[]>([])
  const [formError, setFormError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [allowedTypes, setAllowedTypes] = useState<FileType[]>(PDF_ONLY)

  const resolvedBackendUrl = useMemo(() => backendUrl ?? getBackendUrl(), [backendUrl])

  useEffect(() => {
    if (!open) {
      setFiles([])
      setFormError(null)
      setSubmitError(null)
      setIsSubmitting(false)
      setAllowedTypes(PDF_ONLY)
    }
  }, [open])

  useEffect(() => {
    setFiles((currentFiles) => {
      const filtered = currentFiles.filter((file) => {
        const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
        return allowedTypes.some((type) => {
          const info = FILE_TYPE_OPTIONS[type]
          return info.extensions.includes(extension) || info.accept.includes(file.type)
        })
      })
      if (filtered.length !== currentFiles.length) {
        setFormError(null)
        setSubmitError(null)
      }
      return filtered
    })
  }, [allowedTypes])

  const toggleAllowedType = (type: FileType) => (checked: boolean) => {
    setAllowedTypes((current) => {
      if (checked) {
        if (current.includes(type)) {
          return current
        }
        return [...current, type]
      }

      if (current.length === 1) {
        return current
      }

      return current.filter((value) => value !== type)
    })
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormError(null)
    setSubmitError(null)

    if (files.length === 0) {
      setFormError('최소 한 개의 파일을 업로드해주세요.')
      return
    }

    const formData = new FormData()
    if (folderId) {
      formData.append('folder_id', folderId)
    }
    allowedTypes.forEach((type) => {
      formData.append('allowed_types', type)
    })
    files.forEach((file) => {
      formData.append('files', file)
    })

    setIsSubmitting(true)
    try {
      const response = await fetch(`${resolvedBackendUrl}/drive/projects`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        let detail = '프로젝트 생성에 실패했습니다. 잠시 후 다시 시도해주세요.'
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

      onClose()
      onSuccess?.()
    } catch (error) {
      const fallback =
        error instanceof Error
          ? error.message
          : '프로젝트 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'
      setSubmitError(fallback)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      busy={isSubmitting}
      title="새 프로젝트 생성"
      description="업로드된 파일로 'GS-X-X-XXXX' 프로젝트 폴더와 필수 하위 폴더가 자동으로 생성됩니다."
    >
      <form className="modal__form" onSubmit={handleSubmit}>
        <div className="modal__body">
          <p className="modal__helper-text">
            업로드한 파일은 생성되는 프로젝트의 ‘0. 사전 자료’ 폴더에 저장되며, 선택한 형식만 허용됩니다.
          </p>

          <fieldset className="modal__fieldset">
            <legend className="modal__label">허용할 파일 형식</legend>
            <p className="modal__helper-text">
              최소 한 가지 형식을 선택하면 업로드 컴포넌트의 허용 범위가 즉시 반영됩니다.
            </p>
            <div className="modal__checkboxes">
              {ALL_FILE_TYPES.map((type) => {
                const option = FILE_TYPE_OPTIONS[type]
                const checked = allowedTypes.includes(type)
                return (
                  <label key={type} className="modal__checkbox">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => toggleAllowedType(type)(event.target.checked)}
                      disabled={isSubmitting}
                    />
                    {option.label}
                  </label>
                )
              })}
            </div>
          </fieldset>

          <FileUploader allowedTypes={allowedTypes} files={files} onChange={setFiles} disabled={isSubmitting} />

          {formError && (
            <p className="modal__error" role="alert">
              {formError}
            </p>
          )}
          {submitError && (
            <p className="modal__error" role="alert">
              {submitError}
            </p>
          )}
        </div>

        <footer className="modal__footer">
          <button type="button" className="modal__button" onClick={onClose} disabled={isSubmitting}>
            취소
          </button>
          <button type="submit" className="modal__button modal__button--primary" disabled={isSubmitting}>
            {isSubmitting ? '생성 중…' : '생성'}
          </button>
        </footer>
      </form>
      {isSubmitting && (
        <div className="modal__loading" role="status" aria-live="polite">
          <div className="modal__spinner" aria-hidden="true" />
          <p className="modal__loading-text">프로젝트를 생성하는 중입니다…</p>
        </div>
      )}
    </Modal>
  )
}
