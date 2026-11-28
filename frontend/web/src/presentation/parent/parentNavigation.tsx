import { BookOpen, CreditCard, FileText, Settings, Smartphone } from 'lucide-react'

const icon = { size: 22, strokeWidth: 1.8, 'aria-hidden': true } as const
export const parentNavigation = [
  { path: '/parent/journal', label: '학습 현황', short: '학습', icon: <BookOpen {...icon} /> },
  { path: '/parent/report', label: '리포트·기록에 물어보기', short: '리포트', icon: <FileText {...icon} /> },
  { path: '/parent/settings', label: '계정·자녀 설정', short: '설정', icon: <Settings {...icon} /> },
  { path: '/parent/devices', label: '기기·PIN', short: '기기', icon: <Smartphone {...icon} /> },
  { path: '/parent/billing', label: '이용권·결제', short: '결제', icon: <CreditCard {...icon} /> },
]
