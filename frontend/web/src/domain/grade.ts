/**
 * 학생 학년 (#432). core 저장 학년은 초3(3)~중3(9)이고 매년 3월 1일(KST)에 자동으로 한 학년 오른다.
 * 새 등록은 지원 학년 초3~6(P03)만 받는다. 중학생은 중학교 과정 확장 전까지 초6 문제를 받는다.
 */
export const MIN_GRADE = 3
export const MAX_GRADE = 9
export const REGISTRATION_GRADES = [3, 4, 5, 6] as const
export const EDITABLE_GRADES = [3, 4, 5, 6, 7, 8, 9] as const

export function isStoredGrade(grade: unknown): grade is number {
  return Number.isInteger(grade) && Number(grade) >= MIN_GRADE && Number(grade) <= MAX_GRADE
}

export function gradeLabel(grade: number): string {
  return grade <= 6 ? `초등 ${grade}학년` : `중학교 ${grade - 6}학년`
}

export const gradePromotionNotice =
  '학년은 매년 3월 1일에 자동으로 한 학년 올라가요(중학교 3학년까지). 2월 1일 이후 학년을 바꿨다면 그 해에는 자동으로 올리지 않아요. 중학생은 중학교 과정이 생기기 전까지 초등 6학년 문제를 받아요.'
