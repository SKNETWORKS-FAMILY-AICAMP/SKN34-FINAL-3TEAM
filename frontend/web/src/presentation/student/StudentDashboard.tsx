import { ArrowRight, Play } from 'lucide-react'
import { useStudentHome } from '../../data/classroom/useClassroom.ts'
import type { Child } from '../../domain/classroom.ts'
import { inputLabels, thinkingLabels } from '../../domain/classroom.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import { QueryStateNotice } from '../common/QueryStateNotice.tsx'
export function StudentDashboard({
  child,
  onResume,
  onChoose,
}: {
  child: Child
  onResume: (id: string) => void
  onChoose: () => void
}) {
  const query = useStudentHome(child),
    home = query.error ? undefined : query.data
  return (
    <>
      <div className="cj-feedbar">
        <h1>학습 홈</h1>
        <button
          type="button"
          className="cj-secondary"
          onClick={() => {
            void query.refetch()
          }}
        >
          상태 새로 확인
        </button>
      </div>
      <div className="cj-feed">
        {query.isPending && <QueryStateNotice state="PROCESSING" />}
        <ErrorNotice
          error={query.error}
          retry={() => {
            void query.refetch()
          }}
        />
        {home && (
          <>
            <QueryStateNotice state={home.state}>
              {home.state === 'OK' ? null : undefined}
            </QueryStateNotice>
            {home.state !== 'FAILED' && home.state !== 'PROCESSING' && (
              <>
                <article className="cj-sheet">
                  <h2>{child.nickname} 학생, 오늘의 생각을 남겨 볼까요?</h2>
                  <p>
                    초등 {child.grade}학년 · {home.period.from}~{home.period.to}
                  </p>
                  {home.resume ? (
                    <div className="ux-resume">
                      <small>진행 중인 활동</small>
                      <h3>{home.resume.mission.title}</h3>
                      <p>
                        {home.resume.draft?.savedAt
                          ? `마지막 초안 저장: ${new Date(home.resume.draft.savedAt).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}`
                          : '아직 저장한 초안이 없습니다.'}
                      </p>
                      <button
                        type="button"
                        className="cj-primary"
                        onClick={() => onResume(home.resume!.attemptId)}
                      >
                        <Play />
                        이어서 작성하기
                      </button>
                    </div>
                  ) : (
                    <p>새 미션을 골라 시작할 수 있어요.</p>
                  )}
                  <button type="button" className="cj-secondary" onClick={onChoose}>
                    전체 미션 보기 <ArrowRight />
                  </button>
                </article>
                <article className="cj-sheet">
                  <h2>시작할 수 있는 활동</h2>
                  {home.missions.map((m) => (
                    <div className="cj-metric-line" key={m.id}>
                      <span>
                        {m.title}
                        <small style={{ display: 'block' }}>
                          {m.subject} · {thinkingLabels[m.thinkingType]} ·{' '}
                          {inputLabels[m.inputType]}
                        </small>
                      </span>
                      <span>
                        {m.status === 'COMPLETED'
                          ? '완료'
                          : m.status === 'IN_PROGRESS'
                            ? '진행 중'
                            : '시작 전'}
                      </span>
                    </div>
                  ))}
                </article>
              </>
            )}
            {(home.state === 'FAILED' || home.state === 'PROCESSING') && (
              <button
                type="button"
                className="cj-secondary"
                onClick={() => {
                  void query.refetch()
                }}
              >
                다시 확인
              </button>
            )}
          </>
        )}
      </div>
    </>
  )
}
