import { useCallback, useEffect, useMemo, useState } from 'react'

import { getBackendUrl } from '../config'

const MENU_ID = 'feature-list'

interface PromptPayload {
  system: string
  instruction: string
}

type FetchState = 'idle' | 'loading' | 'saving'

export function PromptAdminPage() {
  const [systemPrompt, setSystemPrompt] = useState('')
  const [instructionPrompt, setInstructionPrompt] = useState('')
  const [initialPrompt, setInitialPrompt] = useState<PromptPayload | null>(null)
  const [fetchState, setFetchState] = useState<FetchState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)

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

  const loadPrompt = useCallback(async () => {
    setFetchState('loading')
    setError(null)
    try {
      const response = await fetch(`${backendUrl}/admin/prompts/${MENU_ID}`)
      if (!response.ok) {
        throw new Error('프롬프트 정보를 불러오지 못했습니다.')
      }
      const data = (await response.json()) as { system: string; instruction: string }
      setSystemPrompt(data.system ?? '')
      setInstructionPrompt(data.instruction ?? '')
      setInitialPrompt({
        system: data.system ?? '',
        instruction: data.instruction ?? '',
      })
      setLastSavedAt(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.')
    } finally {
      setFetchState('idle')
    }
  }, [backendUrl])

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

        const data = (await response.json()) as PromptPayload
        setInitialPrompt(data)
        setSystemPrompt(data.system)
        setInstructionPrompt(data.instruction)
        setLastSavedAt(new Date())
      } catch (err) {
        setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.')
      } finally {
        setFetchState('idle')
      }
    },
    [backendUrl, instructionPrompt, isDirty, systemPrompt],
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
