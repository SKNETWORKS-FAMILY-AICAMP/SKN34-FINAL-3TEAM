import { Link } from 'react-router'
import { useSession } from '../auth/sessionContext.ts'
import type { SupportTarget } from '../../domain/service.ts'
export function ReportProblem({ targetType,targetId }: { targetType:SupportTarget;targetId:string }) {
  const {session}=useSession()
  if(!session||session.role==='ADMIN')return null
  return <Link to={'/'+session.role.toLowerCase()+'/support?'+new URLSearchParams({targetType,targetId})}>이 결과 오류 신고</Link>
}
