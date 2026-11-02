import { useSearchParams } from 'react-router'
import { SupportResults } from './SupportResults.tsx'
import { ServiceCenter } from '../service/ServiceCenter.tsx'

/** 기존 알림의 /support?reportId=…·inquiryId=…를 실제 서버 결과 화면으로 연결한다. */
export function SupportEntry() {
  const [params] = useSearchParams()
  return params.has('reportId') || params.has('inquiryId')
    ? <SupportResults />
    : <ServiceCenter page="support" />
}
