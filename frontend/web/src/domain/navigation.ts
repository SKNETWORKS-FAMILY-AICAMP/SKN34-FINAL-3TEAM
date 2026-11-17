import type { Role } from './classroom.ts'
export const roleStart = (role: Role) =>
  role === 'STUDENT' ? '/student/home' : role === 'PARENT' ? '/parent/journal' : '/admin/home'

export const loginPaths = ['/login', '/signup', '/student/login', '/admin/login'] as const
export type LoginPath = typeof loginPaths[number]
export const isLoginPath = (path: string): path is LoginPath => loginPaths.some(value => value === path)

/** 공개 소개에서 고른 진입 화면. 역할을 부여하는 값이 아니라 기존 세션 자동 복원을 막는 표시다. */
export const landingEntryHref = (path: LoginPath) => `${path}?entry=landing`
export function landingLoginEntry(path: string, search: string): LoginPath | null {
  return isLoginPath(path) && new URLSearchParams(search).get('entry') === 'landing' ? path : null
}

/** 보호자 인증이 필요한 탭에서도 사용자가 고른 가입·관리자 로그인 화면을 유지한다. */
export const adultLoginPath = (path: string) =>
  isLoginPath(path) && path !== '/student/login' ? path : '/login'
