import { useCallback, useEffect, useMemo, useState } from 'react'

import { getBackendUrl } from '../config'

const MENU_ID = 'feature-list'

interface PromptAttachmentResponse {
  name: string
  label: string
  role: string
  builtin: boolean
  size_bytes?: number | null
  content_type?: string | null
}

interface PromptPreviewResponse {
  user_prompt: string
  descriptor_lines?: string[] | null
  closing_note?: string | null
}

interface PromptAttachment {
  name: string
  label: string
  role: string
  builtin: boolean
  sizeBytes: number | null
  contentType: string | null
}

interface PromptPreview {
  userPrompt: string
  descriptorLines: string[]
  closingNote: string | null
}

interface PromptPayload {
  system: string
  instruction: string
  attachments: PromptAttachment[]
  preview: PromptPreview
}

type FetchState = 'idle' | 'loading' | 'saving'

export function PromptAdminPage() {
  const [systemPrompt, setSystemPrompt] = useState('')
  const [instructionPrompt, setInstructionPrompt] = useState('')
  const [initialPrompt, setInitialPrompt] = useState<PromptPayload | null>(null)
  const [fetchState, setFetchState] = useState<FetchState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)
  const [attachments, setAttachments] = useState<PromptAttachment[]>([])
  const [preview, setPreview] = useState<PromptPreview | null>(null)

  const backendUrl = useMemo(() => getBackendUrl(), [])

  const isLoading = fetchState === 'loading'
  const isSaving = fetchState === 'saving'

  const isDirty = useMemo(() => {
    if (!initialPrompt) {
      return false
    }
    return (
      systemPrompt !== initialPrompt.system ||
      instructionPrompt !== initialPrompt.instruction
    )
  }, [initialPrompt, systemPrompt, instructionPrompt])

  const normalizeAttachments = useCallback(
    (raw?: PromptAttachmentResponse[] | null): PromptAttachment[] => {
      if (!raw || raw.length === 0) {
        return []
      }
      return raw.map((attachment) => ({
        name: attachment.name,
        label: attachment.label ?? attachment.name,
        role: attachment.role ?? 'additional',
        builtin: Boolean(attachment.builtin),
        sizeBytes: typeof attachment.size_bytes === 'number' ? attachment.size_bytes : null,
        contentType: attachment.content_type ?? null,
      }))
    },
    [],
  )

  const normalizePreview = useCallback(
    (raw?: PromptPreviewResponse | null): PromptPreview => ({
      userPrompt: raw?.user_prompt ?? '',
      descriptorLines: raw?.descriptor_lines?.filter((line) => line.trim().length > 0) ?? [],
      closingNote: raw?.closing_note ?? null,
    }),
    [],
  )

  const formatFileSize = useCallback((size: number | null) => {
    if (!size || size <= 0) {
      return null
    }
    const units = ['B', 'KB', 'MB', 'GB']
    let value = size
    let unitIndex = 0
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024
      unitIndex += 1
    }
    const formatted = value >= 10 || unitIndex === 0 ? value.toFixed(0) : value.toFixed(1)
    return `${formatted}${units[unitIndex]}`
  }, [])

  const loadPrompt = useCallback(async () => {
    setFetchState('loading')
    setError(null)
    try {
      const response = await fetch(`${backendUrl}/admin/prompts/${MENU_ID}`)
      if (!response.ok) {
        throw new Error('프롬프트 정보를 불러오지 못했습니다.')
      }
      const data = (await response.json()) as {
        system: string
        instruction: string
        attachments?: PromptAttachmentResponse[]
        preview?: PromptPreviewResponse
      }
      const normalized: PromptPayload = {
        system: data.system ?? '',
        instruction: data.instruction ?? '',
        attachments: normalizeAttachments(data.attachments),
        preview: normalizePreview(data.preview),
      }
      setSystemPrompt(normalized.system)
      setInstructionPrompt(normalized.instruction)
      setAttachments(normalized.attachments)
      setPreview(normalized.preview)
      setInitialPrompt(normalized)
      setLastSavedAt(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setFetchState('idle')
    }
  }, [backendUrl, normalizeAttachments, normalizePreview])

  useEffect(() => {
    void loadPrompt()
  }, [loadPrompt])

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!isDirty) {
        return
      }

      setFetchState('saving')
      setError(null)
      try {
        const response = await fetch(`${backendUrl}/admin/prompts/${MENU_ID}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            system: systemPrompt,
            instruction: instructionPrompt,
          }),
        })

        if (!response.ok) {
          throw new Error('프롬프트 저장에 실패했습니다.')
        }

        const data = (await response.json()) as {
          system: string
          instruction: string
          attachments?: PromptAttachmentResponse[]
          preview?: PromptPreviewResponse
        }
        const normalized: PromptPayload = {
          system: data.system,
          instruction: data.instruction,
          attachments: normalizeAttachments(data.attachments),
          preview: normalizePreview(data.preview),
        }
        setInitialPrompt(normalized)
        setSystemPrompt(normalized.system)
        setInstructionPrompt(normalized.instruction)
        setAttachments(normalized.attachments)
        setPreview(normalized.preview)
        setLastSavedAt(new Date())
      } catch (err) {
        setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.')
      } finally {
        setFetchState('idle')
      }
    },
    [
      backendUrl,
      instructionPrompt,
      isDirty,
      normalizeAttachments,
      normalizePreview,
      systemPrompt,
    ],
  )

  return (
    <section className="prompt-admin">
      <header className="prompt-admin__header">
        <h1 className="prompt-admin__title">기능 리스트 생성 프롬프트 관리</h1>
        <p className="prompt-admin__description">
          기능 리스트 생성 메뉴에서 사용되는 시스템 및 사용자 지침 프롬프트를 확인하고 수정할 수 있습니다.
        </p>
      </header>

      <form className="prompt-admin__form" onSubmit={handleSubmit}>
        <div className="prompt-admin__field">
          <label className="prompt-admin__label" htmlFor="systemPrompt">
            시스템 프롬프트
          </label>
          <textarea
            id="systemPrompt"
            className="prompt-admin__textarea"
            value={systemPrompt}
            onChange={(event) => setSystemPrompt(event.target.value)}
            rows={6}
            disabled={isLoading}
            placeholder="모델이 따라야 할 역할과 문맥을 입력하세요."
            required
          />
        </div>

        <div className="prompt-admin__field">
          <label className="prompt-admin__label" htmlFor="instructionPrompt">
            사용자 지침 프롬프트
          </label>
          <textarea
            id="instructionPrompt"
            className="prompt-admin__textarea"
            value={instructionPrompt}
            onChange={(event) => setInstructionPrompt(event.target.value)}
            rows={8}
            disabled={isLoading}
            placeholder="모델에 전달할 사용자 지침을 입력하세요."
            required
          />
        </div>

        <div className="prompt-admin__actions">
          <button
            type="button"
            className="prompt-admin__button prompt-admin__button--secondary"
            onClick={() => void loadPrompt()}
            disabled={isLoading || isSaving}
          >
            다시 불러오기
          </button>

          <button
            type="submit"
            className="prompt-admin__button prompt-admin__button--primary"
            disabled={isLoading || isSaving || !isDirty}
          >
            {isSaving ? '저장 중...' : '변경 사항 저장'}
          </button>
        </div>
      </form>

      <section
        className="prompt-admin__prompt-preview"
        aria-labelledby="prompt-preview-heading"
      >
        <div className="prompt-admin__prompt-preview-header">
          <div className="prompt-admin__prompt-preview-copy">
            <span className="prompt-admin__attachments-eyebrow">프롬프트 미리보기</span>
            <h2 id="prompt-preview-heading" className="prompt-admin__prompt-preview-title">
              모델에 전달되는 사용자 메시지와 첨부 설명
            </h2>
            <p className="prompt-admin__prompt-preview-description">
              저장된 프롬프트와 자동 첨부 정보를 바탕으로 실제 생성 요청에 포함되는 메시지 본문과 첨부 설명을 확인할 수 있습니다.
            </p>
          </div>
        </div>

        <div className="prompt-admin__prompt-preview-content">
          <article className="prompt-admin__prompt-preview-card">
            <header className="prompt-admin__prompt-preview-card-header">
              <span>사용자 메시지 예시</span>
            </header>
            <pre className="prompt-admin__prompt-preview-code">
              {preview?.userPrompt
                ? preview.userPrompt
                : isLoading
                ? '프롬프트를 불러오는 중입니다...'
                : '사용자 메시지 본문이 비어 있습니다.'}
            </pre>
          </article>

          <article className="prompt-admin__prompt-preview-card prompt-admin__prompt-preview-card--list">
            <header className="prompt-admin__prompt-preview-card-header">
              <span>첨부 파일 목록</span>
            </header>
            {preview && preview.descriptorLines.length > 0 ? (
              <ol className="prompt-admin__prompt-preview-descriptors">
                {preview.descriptorLines.map((line, index) => (
                  <li key={`${line}-${index}`}>{line}</li>
                ))}
              </ol>
            ) : (
              <p className="prompt-admin__prompt-preview-empty">표시할 첨부 설명이 없습니다.</p>
            )}
            {preview?.closingNote && (
              <p className="prompt-admin__prompt-preview-closing">{preview.closingNote}</p>
            )}
          </article>
        </div>
      </section>

      <section className="prompt-admin__attachments" aria-labelledby="prompt-attachments-heading">
        <div className="prompt-admin__attachments-header">
          <div className="prompt-admin__attachments-copy">
            <span className="prompt-admin__attachments-eyebrow">자동 업로드 미리보기</span>
            <h2 id="prompt-attachments-heading" className="prompt-admin__attachments-title">
              기능리스트 생성 시 함께 전달되는 자료
            </h2>
            <p className="prompt-admin__attachments-description">
              이 메뉴에서 생성 요청을 보내면 아래 파일이 자동으로 업로드되어 모델의 컨텍스트로 전달됩니다.
            </p>
          </div>
          <div className="prompt-admin__upload-visual" aria-hidden="true">
            <div className="prompt-admin__upload-visual-glow" />
            <div className="prompt-admin__upload-visual-card">
              <div className="prompt-admin__upload-visual-page" />
              <div className="prompt-admin__upload-visual-page prompt-admin__upload-visual-page--offset" />
              <div className="prompt-admin__upload-visual-arrow" />
            </div>
            <div className="prompt-admin__upload-visual-trail">
              <span />
              <span />
              <span />
            </div>
          </div>
        </div>

        {attachments.length > 0 ? (
          <ul className="prompt-admin__attachments-list">
            {attachments.map((attachment) => {
              const sizeLabel = formatFileSize(attachment.sizeBytes)
              const roleLabel = attachment.role === 'required' ? '필수 첨부' : '참고 첨부'
              const detailSegments = [roleLabel]
              if (attachment.contentType) {
                detailSegments.push(attachment.contentType.toUpperCase())
              }
              if (sizeLabel) {
                detailSegments.push(sizeLabel)
              }

              return (
                <li key={`${attachment.name}-${attachment.role}`} className="prompt-admin__attachment-card">
                  <div className="prompt-admin__attachment-main">
                    <div className="prompt-admin__attachment-icon" aria-hidden="true">
                      <span className="prompt-admin__attachment-icon-fold" />
                      <span className="prompt-admin__attachment-icon-line" />
                    </div>
                    <div className="prompt-admin__attachment-content">
                      <span className="prompt-admin__attachment-label">{attachment.label}</span>
                      <span className="prompt-admin__attachment-name">{attachment.name}</span>
                      <span className="prompt-admin__attachment-details">{detailSegments.join(' · ')}</span>
                    </div>
                  </div>
                  <span className="prompt-admin__attachment-chip">
                    {attachment.builtin ? '시스템 자동 업로드' : '사용자 업로드'}
                  </span>
                </li>
              )
            })}
          </ul>
        ) : (
          <div className="prompt-admin__attachments-empty">
            <p>현재 자동으로 업로드되는 파일이 없습니다.</p>
          </div>
        )}
      </section>

      <footer className="prompt-admin__footer">
        {error && <p className="prompt-admin__status prompt-admin__status--error">{error}</p>}
        {!error && isLoading && (
          <p className="prompt-admin__status">프롬프트를 불러오는 중입니다...</p>
        )}
        {!error && !isLoading && lastSavedAt && (
          <p className="prompt-admin__status prompt-admin__status--success">
            {`저장 완료: ${lastSavedAt.toLocaleString()}`}
          </p>
        )}
        {!error && !isLoading && !lastSavedAt && !isDirty && initialPrompt && (
          <p className="prompt-admin__status">프롬프트가 최신 상태입니다.</p>
        )}
      </footer>
    </section>
  )
}
