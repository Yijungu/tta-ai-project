import { useMemo, useState } from 'react'

interface ProjectManagementPageProps {
  projectId: string
}

type SectionLevel = 'primary' | 'secondary'

interface SectionDefinition {
  id: string
  label: string
  level: SectionLevel
  parentId?: string
  description: string
  actionLabel: string
}

const sections: SectionDefinition[] = [
  {
    id: 'feature-tc',
    label: '기능 및 TC 생성 메뉴',
    level: 'primary',
    description: '테스트 커버리지를 빠르게 준비할 수 있도록 필요한 문서나 자료를 업로드하고 기능 및 테스트케이스를 생성하세요.',
    actionLabel: '기능 및 TC 생성하기',
  },
  {
    id: 'defect-report',
    label: '결함리포트 생성',
    level: 'primary',
    description: '결함 리포트 생성을 위한 전반적인 자료를 업로드하고 자동화된 리포트를 한 번에 생성합니다.',
    actionLabel: '결함 리포트 생성하기',
  },
  {
    id: 'defect-report-issue',
    label: '결함',
    parentId: 'defect-report',
    level: 'secondary',
    description: '버그 및 이슈 항목을 업로드하면 상세 결함 리포트를 자동으로 작성해 드립니다.',
    actionLabel: '결함 리포트 생성하기',
  },
  {
    id: 'defect-report-security',
    label: '보안성',
    parentId: 'defect-report',
    level: 'secondary',
    description: '보안 취약점과 관련된 자료를 업로드하고 보안성 중심의 결함 리포트를 생성하세요.',
    actionLabel: '보안성 리포트 생성하기',
  },
  {
    id: 'performance-report',
    label: '성능평가리포트 생성',
    level: 'primary',
    description: '성능 측정 결과를 업로드하면 핵심 지표가 정리된 성능평가 리포트를 만들어 드립니다.',
    actionLabel: '성능평가 리포트 생성하기',
  },
]

export function ProjectManagementPage({ projectId }: ProjectManagementPageProps) {
  const projectName = useMemo(() => {
    const searchParams = new URLSearchParams(window.location.search)
    const name = searchParams.get('name')
    return name ?? projectId
  }, [projectId])

  const [activeSectionId, setActiveSectionId] = useState<string>('feature-tc')

  const activeSection = sections.find((section) => section.id === activeSectionId) ?? sections[0]

  return (
    <div className="project-management-layout">
      <header className="project-management-header">
        <div className="project-management-header__content">
          <p className="project-management-header__eyebrow">프로젝트 관리</p>
          <h1 className="project-management-header__title">{projectName}</h1>
          <p className="project-management-header__subtitle">
            프로젝트별 테스트와 리포트 생성을 한 곳에서 빠르게 관리하세요.
          </p>
        </div>
      </header>

      <div className="project-management-page">
        <aside className="project-management-sidebar">
          <div className="project-management-overview">
            <span className="project-management-overview__label">프로젝트</span>
            <strong className="project-management-overview__name">{projectName}</strong>
          </div>

          <nav aria-label="프로젝트 관리 메뉴" className="project-management-menu">
            <ul className="project-management-menu__list">
              {sections
                .filter((section) => section.level === 'primary')
                .map((section) => {
                  const childSections = sections.filter((child) => child.parentId === section.id)

                  return (
                    <li key={section.id} className="project-management-menu__group">
                      <button
                        type="button"
                        className={[
                          'project-management-menu__item',
                          'project-management-menu__item--primary',
                          activeSectionId === section.id ? 'project-management-menu__item--active' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        onClick={() => setActiveSectionId(section.id)}
                      >
                        <span aria-hidden="true" className="project-management-menu__prefix">
                          -
                        </span>
                        <span className="project-management-menu__label">{section.label}</span>
                      </button>

                      {childSections.length > 0 && (
                        <ul className="project-management-menu__sublist">
                          {childSections.map((childSection) => (
                            <li key={childSection.id}>
                              <button
                                type="button"
                                className={[
                                  'project-management-menu__item',
                                  'project-management-menu__item--secondary',
                                  activeSectionId === childSection.id
                                    ? 'project-management-menu__item--active'
                                    : '',
                                ]
                                  .filter(Boolean)
                                  .join(' ')}
                                onClick={() => setActiveSectionId(childSection.id)}
                              >
                                <span aria-hidden="true" className="project-management-menu__prefix">
                                  &gt;
                                </span>
                                <span className="project-management-menu__label">{childSection.label}</span>
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  )
                })}
            </ul>
          </nav>
        </aside>

        <main className="project-management-content" aria-label="프로젝트 관리 컨텐츠">
          <section className="project-management-section" aria-labelledby={`section-${activeSection.id}`}>
            <div className="project-management-section__header">
              <h2 id={`section-${activeSection.id}`} className="project-management-section__title">
                {activeSection.label}
              </h2>
              <p className="project-management-section__description">{activeSection.description}</p>
            </div>

            <div className="project-management-upload" role="group" aria-labelledby={`section-${activeSection.id}`}>
              <div className="project-management-upload__dropzone">
                <input
                  className="project-management-upload__input"
                  id={`upload-${activeSection.id}`}
                  type="file"
                  multiple
                />
                <label htmlFor={`upload-${activeSection.id}`} className="project-management-upload__label">
                  <span className="project-management-upload__icon" aria-hidden="true">
                    ⬆
                  </span>
                  <span className="project-management-upload__text">
                    파일을 이곳에 끌어오거나 클릭하여 업로드하세요.
                  </span>
                </label>
              </div>
              <p className="project-management-upload__helper">
                지원 형식: PDF, XLSX, CSV, DOCX — 최대 200MB
              </p>
            </div>

            <div className="project-management-actions">
              <button type="button" className="project-management-primary-button">
                {activeSection.actionLabel}
              </button>
              <button type="button" className="project-management-secondary-button">
                업로드 내역 관리
              </button>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}

