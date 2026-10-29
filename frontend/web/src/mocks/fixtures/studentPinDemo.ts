import type { Child } from '../../domain/classroom.ts'
// 임시 개발 시연 전용. 실제 DB·학생 인증 연동 시 제거한다.
export const temporaryStudentPin = '5090'
export const pinDemoChild: Child = { id: 'demo-pin-student', nickname: '시연 학생', grade: 3, birthYear: 2017, plan: 'FREE' }
