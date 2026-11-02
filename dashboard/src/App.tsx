import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { DashboardLayout } from './components/DashboardLayout'
import { auth } from './lib/api'
import { ThemeProvider } from './components/ThemeProvider'

const Login = lazy(() => import('./pages/Login').then((module) => ({ default: module.Login })))
const Register = lazy(() => import('./pages/Register').then((module) => ({ default: module.Register })))
const ProjectsList = lazy(() => import('./pages/ProjectsList').then((module) => ({ default: module.ProjectsList })))
const ProjectDetail = lazy(() => import('./pages/ProjectDetail').then((module) => ({ default: module.ProjectDetail })))
const Settings = lazy(() => import('./pages/Settings').then((module) => ({ default: module.Settings })))
const WebsitePromptGenerator = lazy(() => import('./pages/WebsitePromptGenerator'))
const GapPageGenerator = lazy(() => import('./pages/GapPageGenerator'))
const ScanInterface = lazy(() => import('./pages/ScanInterface'))
const WriteBlog = lazy(() => import('./pages/WriteBlog'))
const WriteBlogArticle = lazy(() => import('./pages/WriteBlogArticle'))
const SavedKeywords = lazy(() => import('./pages/SavedKeywords'))
const GoldHunter = lazy(() => import('./pages/GoldHunter').then((module) => ({ default: module.GoldHunter })))
const HubSpokeWorkspace = lazy(() => import('./pages/HubSpokeWorkspace').then((module) => ({ default: module.HubSpokeWorkspace })))
const PaymentProofUpload = lazy(() => import('./pages/PaymentProofUpload').then((module) => ({ default: module.PaymentProofUpload })))
const Waitlist = lazy(() => import('./pages/Waitlist').then((module) => ({ default: module.Waitlist })))
const SuperAdmin = lazy(() => import('./pages/SuperAdmin').then((module) => ({ default: module.SuperAdmin })))

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
    <ThemeProvider defaultTheme="dark" storageKey="sitemap-theme">
      <BrowserRouter>
        <Suspense fallback={<div className="mx-auto mt-24 h-32 max-w-5xl animate-pulse rounded-2xl bg-surface" />}>
          <Routes>
          <Route element={<PublicRoute />}>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
          </Route>

          {/* Payment Proof Verification & Waitlist */}
          <Route path="/payment-proof" element={<PaymentProofUpload />} />
          <Route path="/waitlist" element={<Waitlist />} />

          {/* Superadmin Portal - Hidden & Noindex */}
          <Route path="/superadmin" element={<SuperAdmin />} />

          <Route element={<PrivateRoute />}>
            <Route path="/" element={<DashboardLayout />}>
              <Route index element={<ProjectsList />} />
              <Route path="projects/:projectId" element={<ProjectDetail />} />
              <Route path="website-prompts" element={<WebsitePromptGenerator />} />
              <Route path="scan" element={<ScanInterface />} />
              <Route path="write-blog" element={<WriteBlog />} />
              <Route path="write-blog/:projectId" element={<WriteBlogArticle />} />
              <Route path="gap-page-prompts" element={<GapPageGenerator />} />
              <Route path="saved-keywords" element={<SavedKeywords />} />
              <Route path="gold-hunter" element={<GoldHunter />} />
              <Route path="hub-spoke" element={<HubSpokeWorkspace />} />
              <Route path="settings" element={<Settings />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ThemeProvider>
  )
}

export default App
