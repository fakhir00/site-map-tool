import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { DashboardLayout } from './components/DashboardLayout'
import { Login } from './pages/Login'
import { Register } from './pages/Register'
import { ProjectsList } from './pages/ProjectsList'
import { ProjectDetail } from './pages/ProjectDetail'
import { Settings } from './pages/Settings'
import WebsitePromptGenerator from './pages/WebsitePromptGenerator'
import GapPageGenerator from './pages/GapPageGenerator'
import ScanInterface from './pages/ScanInterface'
import WriteBlog from './pages/WriteBlog'
import WriteBlogArticle from './pages/WriteBlogArticle'
import { auth } from './lib/api'

function PrivateRoute() {
  const location = useLocation()

  if (!auth.hasToken()) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}

function PublicRoute() {
  if (auth.hasToken()) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<PublicRoute />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
        </Route>

        <Route element={<PrivateRoute />}>
          <Route path="/" element={<DashboardLayout />}>
            <Route index element={<ProjectsList />} />
            <Route path="projects/:projectId" element={<ProjectDetail />} />
            <Route path="website-prompts" element={<WebsitePromptGenerator />} />
            <Route path="scan" element={<ScanInterface />} />
            <Route path="write-blog" element={<WriteBlog />} />
            <Route path="write-blog/:projectId" element={<WriteBlogArticle />} />
            <Route path="gap-page-prompts" element={<GapPageGenerator />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
