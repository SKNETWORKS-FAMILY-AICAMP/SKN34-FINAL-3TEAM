import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import { useAuthentication } from '../../data/classroom/useClassroom.ts'
import { parentApi } from '../../data/parent/api.ts'
import { ErrorNotice } from '../shared/ClassroomParts.tsx'
import audit from '../../requirements-audit.json'
import './service.css'
export function ReviewPage() {
  const [filter,setFilter]=useState(''),[search,setSearch]=useState(''),[error,setError]=useState<unknown>(null)
  const [page,setPage]=useState(0)
  const {setSession,setSelected}=useSession(),auth=useAuthentication(),navigate=useNavigate()
  async function enter(role: 'parent'|'admin'|'student') {
    try {
      const next=await auth.login.mutateAsync({email:role==='admin'?'admin@example.test':'parent@example.test',password:'demo-only'})
      setSession(next);setSelected('')
      if(role==='student'){const child=(await parentApi.children()).items[0];if(!child)throw new Error('시연 자녀가 없습니다.');setSession(await auth.enter.mutateAsync(child));navigate('/student/home')}
      else navigate(role==='admin'?'/admin/models':'/parent/help')
    }catch(e){setError(e)}
  }
  const rows=audit.filter(r=>(!filter||r.status===filter)&&(!search||[r.id,r.name,r.description,r.note].join(' ').includes(search)))
  return <main id="class-journal" data-requirements-count={audit.length} style={{padding:'32px 20px'}}><div className="svc-page"><h1>사고뭉치 요구사항 구현 점검</h1><p>2026-10-29 · 엑셀의 기능 ID 165개를 최신 develop c608f52 기준으로 대조했습니다. 화면 구현과 실제 서버·모델·PG 검증을 구분합니다.</p>
    <section className="ws-card"><h2>직접 확인하기</h2><p>아래 버튼은 개발 시연 계정의 기존 로그인 API를 사용합니다. 실제 사용자·실결제 데이터는 사용하지 않습니다.</p><div className="ws-actions">{(['parent','student','admin'] as const).map(role=><button key={role} disabled={auth.login.isPending||auth.enter.isPending} onClick={()=>void enter(role)}>{({parent:'학부모',student:'학생',admin:'관리자'})[role]} 시연 시작</button>)}</div><ErrorNotice error={error}/></section>
    <section className="ws-card"><h2>이번에 확인할 화면</h2><ul><li>학부모: 도움말 → 일반 문의·오류 신고 → 내 접수 내역 → 공지 → 알림 읽음·수신 설정</li><li>학부모 계정·자녀 관리: 정보 수정 → 영향 안내 → Google 재확인 → 연결 해제·삭제 요청 또는 탈퇴</li><li>관리자 모델·프롬프트: 평가 근거 등록 → 범위 확인 → 승인·활성화 → 이전 버전 복귀</li><li>리포트: 기존 상세·근거·다운로드 화면. 실제 파일 생성 서비스 연결은 별도 확인</li></ul><p>삭제·탈퇴 시연은 접수 상태까지만 진행합니다. 백엔드 소비자의 실제 삭제 완료를 만들지 않습니다.</p></section>
    <div className="ws-actions"><label>상태<select value={filter} onChange={e=>{setFilter(e.target.value);setPage(0)}}><option value="">전체 {audit.length}개</option>{[...new Set(audit.map(r=>r.status))].map(s=><option key={s}>{s}</option>)}</select></label><label>요구사항 검색<input value={search} onChange={e=>{setSearch(e.target.value);setPage(0)}} placeholder="기능 ID 또는 이름"/></label></div>
    <p>{rows.length}개 항목 · 기존 구현 표시는 코드가 있다는 뜻이며 이번 작업에서 모든 실제 연동을 검증했다는 뜻은 아닙니다.</p>
    {rows.slice(page*20,(page+1)*20).map(r=><article key={r.id} className="ws-card"><h2>{r.id} · {r.name}</h2><p><strong>{r.status}</strong> · 원본 엑셀 {r.row}행</p><p>{r.description}</p><p>{r.note}</p><small>코드·근거: {r.evidence}</small>{r.path&&<p><Link to={r.path}>화면 열기 (역할 로그인 필요)</Link></p>}</article>)}
    <div className="ws-actions"><button disabled={!page} onClick={()=>setPage(p=>p-1)}>이전 20개</button><span>{rows.length? page*20+1:0}~{Math.min((page+1)*20,rows.length)} / {rows.length}</span><button disabled={(page+1)*20>=rows.length} onClick={()=>setPage(p=>p+1)}>다음 20개</button></div>
  </div></main>
}
