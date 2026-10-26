import { createBrowserRouter, Link } from 'react-router'
import { AdminHomePage } from './admin/AdminHomePage.tsx'
import { ParentHomePage } from './parent/ParentHomePage.tsx'
import { StudentHomePage } from './student/StudentHomePage.tsx'

// 역할별 화면은 각 폴더(student·parent·admin)에 기능 단위로 추가
export const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <nav className="flex gap-4 p-6">
        <Link to="/student">학생</Link>
        <Link to="/parent">학부모</Link>
        <Link to="/admin">관리자</Link>
      </nav>
    ),
  },
  { path: '/student', element: <StudentHomePage /> },
  { path: '/parent', element: <ParentHomePage /> },
  { path: '/admin', element: <AdminHomePage /> },
])
