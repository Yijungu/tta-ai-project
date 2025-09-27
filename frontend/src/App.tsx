import './App.css'
import { GoogleLoginCard } from './components/GoogleLoginCard'

function App() {
  return (
    <div className="page">
      <header className="page__header">
        <span className="page__eyebrow">Google Drive 연결</span>
        <h1 className="page__title">한 번의 승인으로 로그인과 Drive 접근까지</h1>
        <p className="page__subtitle">
          아래 버튼을 누르면 Google 계정 확인과 동시에 Drive 파일 접근 권한을 요청합니다.
          승인하면 백엔드가 access/refresh 토큰을 교환해 안전하게 저장합니다.
        </p>
      </header>

      <GoogleLoginCard />
    </div>
  )
}

export default App
