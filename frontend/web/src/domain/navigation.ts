import type { Role } from './classroom.ts'
export const roleStart = (role: Role) =>
  role === 'STUDENT' ? '/student/home' : role === 'PARENT' ? '/parent/journal' : '/admin/home'
