import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

interface GoogleCodeResponse {
  code: string
}

interface TokenExchangeResponse {
  accessToken: string
  refreshToken?: string
  expiresAt: string
  scope: string
}

type CodeClient = {
  requestCode: () => void
}

declare global {
  interface Window {
    google?: {
      accounts: {
        oauth2?: {
          initCodeClient: (config: {
            client_id: string
            scope: string
            callback: (response: GoogleCodeResponse) => void
            ux_mode?: 'popup' | 'redirect'
            access_type?: 'online' | 'offline'
            prompt?: string
            state?: string
            redirect_uri?: string
          }) => CodeClient
        }
      }
    }
  }
}

const GOOGLE_SCRIPT_ID = 'google-identity-services'

export function GoogleLoginCard() {
  const [isReady, setIsReady] = useState(false)
  const [isRequesting, setIsRequesting] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tokenResponse, setTokenResponse] = useState<TokenExchangeResponse | null>(null)
  const codeClientRef = useRef<CodeClient | null>(null)

  const apiBaseUrl = useMemo(() => {
    return import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8000'
  }, [])

  const exchangeAuthorizationCode = useCallback(
    async (code: string) => {
      setIsRequesting(true)
      setError(null)
      setStatusMessage('백엔드에서 Drive 토큰을 교환하는 중입니다…')
      setTokenResponse(null)

      try {
        const response = await fetch(`${apiBaseUrl}/auth/google/exchange`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ code }),
        })

        if (!response.ok) {
          const errorPayload = await response.json().catch(() => null)
          const message =
            (errorPayload && (errorPayload.detail || errorPayload.error)) ||
            '서버에서 토큰을 발급받는 중 오류가 발생했습니다.'
          throw new Error(message)
        }

        const payload = (await response.json()) as TokenExchangeResponse
        setTokenResponse(payload)
        setStatusMessage('Drive 권한이 연결되었어요. 아래에서 발급된 토큰 정보를 확인할 수 있습니다.')
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : '알 수 없는 오류가 발생했습니다. 다시 시도해 주세요.',
        )
        setStatusMessage(null)
      } finally {
        setIsRequesting(false)
      }
    },
    [apiBaseUrl],
  )

  useEffect(() => {
    let isCancelled = false
    let scriptElement: HTMLScriptElement | null = document.getElementById(
      GOOGLE_SCRIPT_ID,
    ) as HTMLScriptElement | null

    const initializeGoogleClient = () => {
      if (isCancelled) {
        return
      }

      const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
      if (!clientId) {
        setError(
          'Google OAuth 클라이언트 ID가 설정되어 있지 않습니다. .env 파일에 VITE_GOOGLE_CLIENT_ID를 추가하세요.',
        )
        return
      }

      const oauth2 = window.google?.accounts?.oauth2
      if (!oauth2?.initCodeClient) {
        setError('Google OAuth 클라이언트를 초기화할 수 없습니다. SDK 구성을 확인하세요.')
        return
      }

      codeClientRef.current = oauth2.initCodeClient({
        client_id: clientId,
        scope: 'openid email profile https://www.googleapis.com/auth/drive.file',
        access_type: 'offline',
        prompt: 'consent',
        ux_mode: 'popup',
        redirect_uri: 'postmessage',
        callback: async (response: GoogleCodeResponse) => {
          if (!response.code) {
            setError('Google로부터 인가 코드를 받지 못했습니다. 다시 시도해 주세요.')
            setStatusMessage(null)
            return
          }
          await exchangeAuthorizationCode(response.code)
        },
      })

      setError(null)
      setIsReady(true)
    }

    const handleScriptError = () => {
      if (!isCancelled) {
        setError('Google OAuth 스크립트를 불러오는 데 실패했습니다.')
      }
    }

    if (scriptElement) {
      if (window.google?.accounts?.oauth2?.initCodeClient) {
        initializeGoogleClient()
      } else {
        scriptElement.addEventListener('load', initializeGoogleClient)
        scriptElement.addEventListener('error', handleScriptError)
      }
    } else {
      scriptElement = document.createElement('script')
      scriptElement.id = GOOGLE_SCRIPT_ID
      scriptElement.src = 'https://accounts.google.com/gsi/client'
      scriptElement.async = true
      scriptElement.defer = true
      scriptElement.addEventListener('load', initializeGoogleClient)
      scriptElement.addEventListener('error', handleScriptError)
      document.head.appendChild(scriptElement)
    }

    return () => {
      isCancelled = true
      if (scriptElement) {
        scriptElement.removeEventListener('load', initializeGoogleClient)
        scriptElement.removeEventListener('error', handleScriptError)
      }
    }
  }, [exchangeAuthorizationCode])

  const handleConnectClick = useCallback(() => {
    if (!codeClientRef.current) {
      setError('Google OAuth 클라이언트가 아직 준비되지 않았습니다. 잠시 후 다시 시도하세요.')
      return
    }

    setError(null)
    setTokenResponse(null)
    setStatusMessage('Google 팝업에서 계정을 선택하고 권한을 승인해 주세요.')
    codeClientRef.current.requestCode()
  }, [])

  return (
    <section className="google-card">
      <div className="google-card__content">
        <h2 className="google-card__title">Google 계정과 Drive 권한 동시 연결</h2>
        <p className="google-card__description">
          Google OAuth 2.0 코드 흐름을 사용해 계정 인증과 Drive 파일 접근 권한을 한 번에 요청합니다.
          승인하면 백엔드가 access/refresh 토큰을 교환해 안전하게 저장합니다.
        </p>
      </div>

      <button
        type="button"
        className="google-card__drive-button"
        onClick={handleConnectClick}
        disabled={!isReady || isRequesting}
      >
        {isRequesting ? '권한 요청 중…' : 'Google 계정으로 Drive 연결하기'}
      </button>

      {!isReady && !error && (
        <p className="google-card__helper">Google OAuth 클라이언트를 불러오는 중입니다…</p>
      )}

      {statusMessage && !error && (
        <div className="google-card__status" role="status">
          <strong>진행 중</strong>
          <span>{statusMessage}</span>
        </div>
      )}

      {error && (
        <div className="google-card__status google-card__status--error" role="alert">
          <strong>문제가 발생했습니다.</strong>
          <span>{error}</span>
        </div>
      )}

      {tokenResponse && (
        <div className="google-card__status google-card__status--success" role="status">
          <strong>Drive 권한 연결 완료</strong>
          <span>
            Access Token 만료: {new Date(tokenResponse.expiresAt).toLocaleString()} / Refresh Token
            저장됨
          </span>
          <dl className="google-card__token-details">
            <div>
              <dt>Access Token</dt>
              <dd>{tokenResponse.accessToken}</dd>
            </div>
            {tokenResponse.refreshToken && (
              <div>
                <dt>Refresh Token</dt>
                <dd>{tokenResponse.refreshToken}</dd>
              </div>
            )}
            <div>
              <dt>Scope</dt>
              <dd>{tokenResponse.scope}</dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  )
}
