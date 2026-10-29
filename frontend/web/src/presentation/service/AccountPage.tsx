import { useState } from 'react'
import { Workspace, QueryFeedback } from '../common/Workspace.tsx'
import { parentApi } from '../../data/parent/api.ts'
import { useParentQuery } from '../../data/parent/queries.ts'
import { ProfileSettings } from '../parent/AccountForms.tsx'
import { AccountLifecycle } from './AccountLifecycle.tsx'
import { Withdrawal } from './Withdrawal.tsx'
export function AccountPage() {
  const q=useParentQuery(['children'],signal=>parentApi.children(signal))
  const [id,setId]=useState('')
  const child=q.data?.items.find(c=>c.id===id)??q.data?.items[0]
  return <Workspace title="계정·자녀 관리" nav={[{path:'/parent/journal',label:'대시보드·공책'},{path:'/parent/account',label:'계정·자녀 관리'}]}>
    <div className="svc-page"><h1>계정·자녀 관리</h1><QueryFeedback query={q}/>
      {child&&<><label>관리할 자녀<select value={child.id} onChange={e=>setId(e.target.value)}>{q.data?.items.map(c=><option key={c.id} value={c.id}>{c.nickname}</option>)}</select></label><ProfileSettings key={child.id} child={child}/><AccountLifecycle key={'manage'+child.id} child={child}/></>}
      {!child&&<p>연결된 자녀 정보를 확인할 수 없습니다. 탈퇴 사전 확인은 아래에서 진행할 수 있습니다.</p>}
      <Withdrawal/>
    </div>
  </Workspace>
}
