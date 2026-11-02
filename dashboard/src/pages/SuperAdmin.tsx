import { useEffect, useState } from 'react'
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Eye,
  FileText,
  Filter,
  Image as ImageIcon,
  KeyRound,
  Loader2,
  Lock,
  LogOut,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Users,
  X,
  ZoomIn,
} from 'lucide-react'
import { adminAuth, api, DEMO_BACKEND_ENABLED, type AdminStats, type AdminUserRequest } from '../lib/api'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

export function SuperAdmin() {
  // Ensure this page is completely excluded from search engines
  useEffect(() => {
    let meta = document.querySelector('meta[name="robots"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.setAttribute('name', 'robots')
      document.head.appendChild(meta)
    }
    meta.setAttribute('content', 'noindex, nofollow')

    return () => {
      meta?.setAttribute('content', 'noindex, nofollow')
    }
  }, [])

  // Admin login credentials state
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(adminAuth.hasToken())
  const [adminIdInput, setAdminIdInput] = useState('crawladmin@1')
  const [passwordInput, setPasswordInput] = useState('')
  const [loginError, setLoginError] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)

  // Admin data state
  const [requests, setRequests] = useState<AdminUserRequest[]>([])
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loadingData, setLoadingData] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState<'all' | 'pending_approval' | 'approved' | 'rejected'>('all')

  // Lightbox state for viewing payment proof
  const [selectedProof, setSelectedProof] = useState<{
    url: string
    filename?: string | null
    email: string
    name?: string | null
  } | null>(null)

  // Rejection modal state
  const [rejectingUser, setRejectingUser] = useState<AdminUserRequest | null>(null)
  const [rejectionReason, setRejectionReason] = useState(
    'Payment proof could not be verified. Please verify your information and try again or contact customer support.'
  )
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null)
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [copiedEmail, setCopiedEmail] = useState<string | null>(null)

  const showToast = (text: string, type: 'success' | 'error' = 'success') => {
    setToastMessage({ text, type })
    setTimeout(() => setToastMessage(null), 4000)
  }

  const handleAdminLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError('')
    setLoginLoading(true)

    try {
      const res = await api.post<{ access_token: string; admin_id: string }>('/admin/login', {
        admin_id: adminIdInput.trim(),
        password: passwordInput,
      })
      adminAuth.setToken(res.access_token)
      setIsAuthenticated(true)
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : 'Invalid superadmin credentials')
    } finally {
      setLoginLoading(false)
    }
  }

  const handleLogout = () => {
    adminAuth.clear()
    setIsAuthenticated(false)
    setPasswordInput('')
  }

  const loadData = async () => {
    if (!isAuthenticated) return
    setLoadingData(true)
    try {
      const [reqList, statsData] = await Promise.all([
        api.get<AdminUserRequest[]>('/admin/requests'),
        api.get<AdminStats>('/admin/stats'),
      ])
      setRequests(reqList)
      setStats(statsData)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to fetch admin requests', 'error')
    } finally {
      setLoadingData(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    if (!isAuthenticated) return

    const timer = setTimeout(() => {
      if (!cancelled) {
        loadData()
      }
    }, 0)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated])

  const handleApprove = async (user: AdminUserRequest) => {
    setActionLoadingId(user.id)
    try {
      await api.post(`/admin/requests/${user.id}/approve`)
      setRequests((prev) =>
        prev.map((item) =>
          item.id === user.id ? { ...item, status: 'approved', is_active: true, rejection_reason: null } : item
        )
      )
      if (stats) {
        setStats({
          ...stats,
          pending_approval: Math.max(0, stats.pending_approval - 1),
          approved: stats.approved + 1,
        })
      }
      showToast(`Account approved and activated for ${user.email}`)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to approve request', 'error')
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleConfirmReject = async () => {
    if (!rejectingUser) return
    setActionLoadingId(rejectingUser.id)
    try {
      await api.post(`/admin/requests/${rejectingUser.id}/reject`, {
        reason: rejectionReason,
      })
      setRequests((prev) =>
        prev.map((item) =>
          item.id === rejectingUser.id
            ? { ...item, status: 'rejected', is_active: false, rejection_reason: rejectionReason }
            : item
        )
      )
      if (stats) {
        setStats({
          ...stats,
          pending_approval: Math.max(0, stats.pending_approval - 1),
          rejected: stats.rejected + 1,
        })
      }
      showToast(`Registration request for ${rejectingUser.email} rejected`)
      setRejectingUser(null)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to reject request', 'error')
    } finally {
      setActionLoadingId(null)
    }
  }

  const copyToClipboard = (email: string) => {
    navigator.clipboard.writeText(email)
    setCopiedEmail(email)
    setTimeout(() => setCopiedEmail(null), 2000)
  }

  const filteredRequests = requests.filter((item) => {
    if (activeFilter !== 'all' && item.status !== activeFilter) {
      return false
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchesEmail = item.email.toLowerCase().includes(q)
      const matchesName = item.full_name?.toLowerCase().includes(q)
      return matchesEmail || matchesName
    }
    return true
  })

  // Format date nicely
  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr)
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return dateStr
    }
  }

  // ─────────────────────────────────────────────────────────────
  // 1. UNAUTHENTICATED: FIXED CREDENTIAL LOGIN FORM
  // ─────────────────────────────────────────────────────────────
  if (!isAuthenticated) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-abyss px-4 py-12 text-ink">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="mb-6 flex flex-col items-center gap-2">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-warm-red/15 text-warm-red ring-1 ring-warm-red/30 shadow-[0_0_28px_rgba(244,63,94,0.2)]">
              <Shield className="h-6 w-6" />
            </span>
            <div className="flex items-center gap-1.5 rounded-full border border-surface-border bg-surface px-3 py-0.5 text-[11px] font-mono uppercase tracking-wider text-muted">
              <Lock className="h-3 w-3 text-glow-amber" />
              Restricted Area • Noindex
            </div>
            <h1 className="font-display text-xl font-bold tracking-tight">Superadmin Gateway</h1>
          </div>

          <Card className="p-7">
            {DEMO_BACKEND_ENABLED && (
              <div className="mb-4 rounded-xl border border-glow-amber/30 bg-glow-amber/10 p-2.5 text-xs text-glow-amber">
                Demo active: ID <code className="font-mono font-bold">crawladmin@1</code> • Pass{' '}
                <code className="font-mono font-bold">crawlgap@7861</code>
              </div>
            )}

            <form className="space-y-4" onSubmit={handleAdminLogin}>
              {loginError && (
                <div className="rounded-xl border border-warm-red/30 bg-warm-red/10 px-3 py-2 text-xs text-warm-red">
                  {loginError}
                </div>
              )}

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-ink">Admin Identifier</span>
                <div className="relative">
                  <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                  <Input
                    className="pl-9 font-mono text-sm"
                    onChange={(e) => setAdminIdInput(e.target.value)}
                    placeholder="crawladmin@1"
                    required
                    value={adminIdInput}
                  />
                </div>
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-ink">Master Password</span>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                  <Input
                    className="pl-9 font-mono text-sm"
                    onChange={(e) => setPasswordInput(e.target.value)}
                    placeholder="••••••••••••"
                    required
                    type="password"
                    value={passwordInput}
                  />
                </div>
              </label>

              <Button className="w-full" disabled={loginLoading} size="lg" type="submit" variant="glow">
                {loginLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Authenticating...
                  </>
                ) : (
                  <>
                    Authenticate Superadmin
                    <ShieldCheck className="h-4 w-4" />
                  </>
                )}
              </Button>
            </form>

            <div className="mt-5 border-t border-surface-border pt-4 text-center text-[11px] text-muted">
              Private administrative portal • Unauthorized access prohibited
            </div>
          </Card>
        </div>
      </main>
    )
  }

  // ─────────────────────────────────────────────────────────────
  // 2. AUTHENTICATED: SUPERADMIN COCKPIT & REQUESTS AUDIT
  // ─────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-abyss text-ink">
      {/* Toast Alert */}
      {toastMessage && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-2.5 rounded-xl border px-4 py-3 text-sm shadow-2xl backdrop-blur-md animate-fade-up ${
            toastMessage.type === 'success'
              ? 'border-emerald-500/40 bg-surface/95 text-emerald-400 shadow-emerald-500/10'
              : 'border-warm-red/40 bg-surface/95 text-warm-red shadow-warm-red/10'
          }`}
        >
          {toastMessage.type === 'success' ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          ) : (
            <AlertCircle className="h-4 w-4 text-warm-red" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* Top Navbar */}
      <header className="sticky top-0 z-40 border-b border-surface-border bg-abyss/90 backdrop-blur-md px-6 py-3.5">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-warm-red/15 text-warm-red ring-1 ring-warm-red/30 shadow-[0_0_20px_rgba(244,63,94,0.2)]">
              <Shield className="h-5 w-5" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-display font-bold tracking-tight text-ink">GapCrawl Master Admin</span>
                <span className="rounded-full bg-warm-red/20 border border-warm-red/40 px-2 py-0.5 text-[10px] font-mono font-semibold text-warm-red">
                  SUPERADMIN
                </span>
                <span className="hidden sm:inline-block rounded-full bg-surface border border-surface-border px-2 py-0.5 text-[10px] text-muted font-mono">
                  noindex
                </span>
              </div>
              <p className="text-xs text-muted">Approval queue and payment proof audit cockpit</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 rounded-xl border border-surface-border bg-surface/50 px-3 py-1.5 text-xs text-muted font-mono">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              crawladmin@1
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={loadData}
              disabled={loadingData}
              className="gap-1.5"
              title="Refresh requests list"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingData ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="text-muted hover:text-warm-red gap-1.5"
            >
              <LogOut className="h-4 w-4" />
              <span className="hidden sm:inline">Sign out</span>
            </Button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="mx-auto max-w-7xl px-4 sm:px-6 py-8 space-y-7">
        {/* Metric Cards Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="p-4 border-glow-amber/40 bg-surface/70 shadow-[0_0_20px_rgba(245,165,36,0.06)]">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted">Pending Review</span>
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-glow-amber/15 text-glow-amber">
                <Clock className="h-4 w-4" />
              </span>
            </div>
            <p className="mt-2 text-2xl font-bold font-display text-glow-amber">
              {stats?.pending_approval ?? requests.filter((r) => r.status === 'pending_approval').length}
            </p>
            <p className="mt-1 text-[11px] text-muted">Awaiting your approval action</p>
          </Card>

          <Card className="p-4 border-emerald-500/30 bg-surface/70">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted">Approved Users</span>
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
                <CheckCircle2 className="h-4 w-4" />
              </span>
            </div>
            <p className="mt-2 text-2xl font-bold font-display text-emerald-400">
              {stats?.approved ?? requests.filter((r) => r.status === 'approved').length}
            </p>
            <p className="mt-1 text-[11px] text-muted">Active accounts with access</p>
          </Card>

          <Card className="p-4 border-warm-red/30 bg-surface/70">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted">Rejected Requests</span>
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-warm-red/15 text-warm-red">
                <ShieldAlert className="h-4 w-4" />
              </span>
            </div>
            <p className="mt-2 text-2xl font-bold font-display text-warm-red">
              {stats?.rejected ?? requests.filter((r) => r.status === 'rejected').length}
            </p>
            <p className="mt-1 text-[11px] text-muted">Declined payment verification</p>
          </Card>

          <Card className="p-4 border-surface-border bg-surface/70">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-muted">Total Registrations</span>
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface text-ink">
                <Users className="h-4 w-4" />
              </span>
            </div>
            <p className="mt-2 text-2xl font-bold font-display text-ink">
              {stats?.total ?? requests.length}
            </p>
            <p className="mt-1 text-[11px] text-muted">All registered user records</p>
          </Card>
        </div>

        {/* Search & Filter Toolbar */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          {/* Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto rounded-xl border border-surface-border bg-surface/60 p-1 text-xs">
            <button
              onClick={() => setActiveFilter('all')}
              className={`rounded-lg px-3 py-1.5 font-medium transition-colors ${
                activeFilter === 'all'
                  ? 'bg-glow-amber/20 text-glow-amber'
                  : 'text-muted hover:text-ink'
              }`}
            >
              All ({requests.length})
            </button>
            <button
              onClick={() => setActiveFilter('pending_approval')}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium transition-colors ${
                activeFilter === 'pending_approval'
                  ? 'bg-glow-amber/20 text-glow-amber font-semibold'
                  : 'text-muted hover:text-ink'
              }`}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-glow-amber animate-pulse" />
              Pending Review ({requests.filter((r) => r.status === 'pending_approval').length})
            </button>
            <button
              onClick={() => setActiveFilter('approved')}
              className={`rounded-lg px-3 py-1.5 font-medium transition-colors ${
                activeFilter === 'approved'
                  ? 'bg-emerald-500/20 text-emerald-400 font-semibold'
                  : 'text-muted hover:text-ink'
              }`}
            >
              Approved ({requests.filter((r) => r.status === 'approved').length})
            </button>
            <button
              onClick={() => setActiveFilter('rejected')}
              className={`rounded-lg px-3 py-1.5 font-medium transition-colors ${
                activeFilter === 'rejected'
                  ? 'bg-warm-red/20 text-warm-red font-semibold'
                  : 'text-muted hover:text-ink'
              }`}
            >
              Rejected ({requests.filter((r) => r.status === 'rejected').length})
            </button>
          </div>

          {/* Search Box */}
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by email or name..."
              className="pl-9 text-xs"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Requests Table Card */}
        <Card className="overflow-hidden border-surface-border bg-surface/50">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-surface-border bg-surface/80 text-muted uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4 font-semibold">User & Email</th>
                  <th className="py-3 px-4 font-semibold">Submitted</th>
                  <th className="py-3 px-4 font-semibold">Payment Proof (Screenshot)</th>
                  <th className="py-3 px-4 font-semibold">Status</th>
                  <th className="py-3 px-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {filteredRequests.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-muted">
                      {loadingData ? (
                        <div className="flex flex-col items-center justify-center gap-2">
                          <Loader2 className="h-6 w-6 animate-spin text-glow-amber" />
                          <p>Loading registration requests...</p>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center gap-2">
                          <Filter className="h-8 w-8 text-muted/50" />
                          <p className="font-medium text-ink">No requests match your current filter</p>
                          <p className="text-xs text-muted">New user signups will appear here automatically.</p>
                        </div>
                      )}
                    </td>
                  </tr>
                ) : (
                  filteredRequests.map((user) => {
                    const isPending = user.status === 'pending_approval'
                    const isApproved = user.status === 'approved'
                    const isRejected = user.status === 'rejected'
                    const isWorking = actionLoadingId === user.id
                    const adminToken = adminAuth.getToken()
                    const proofUrlWithAuth = user.payment_proof_url
                      ? `${user.payment_proof_url}?token=${encodeURIComponent(adminToken || '')}`
                      : null

                    return (
                      <tr
                        key={user.id}
                        className={`transition-colors hover:bg-surface/90 ${
                          isPending ? 'bg-glow-amber/[0.03]' : ''
                        }`}
                      >
                        {/* User column */}
                        <td className="py-3.5 px-4">
                          <div className="flex flex-col">
                            <span className="font-semibold text-sm text-ink">
                              {user.full_name || 'Anonymous User'}
                            </span>
                            <div className="flex items-center gap-1.5 text-muted mt-0.5">
                              <span className="font-mono text-xs">{user.email}</span>
                              <button
                                type="button"
                                onClick={() => copyToClipboard(user.email)}
                                className="text-muted hover:text-ink transition-colors"
                                title="Copy email address"
                              >
                                {copiedEmail === user.email ? (
                                  <Check className="h-3 w-3 text-emerald-400" />
                                ) : (
                                  <Copy className="h-3 w-3" />
                                )}
                              </button>
                            </div>
                          </div>
                        </td>

                        {/* Date column */}
                        <td className="py-3.5 px-4 text-muted whitespace-nowrap">
                          <div>{formatDate(user.created_at)}</div>
                          {user.reviewed_at && (
                            <div className="text-[10px] text-muted/70">
                              Reviewed: {formatDate(user.reviewed_at)}
                            </div>
                          )}
                        </td>

                        {/* Payment Proof Screenshot column */}
                        <td className="py-3.5 px-4">
                          {user.has_payment_proof && proofUrlWithAuth ? (
                            <div className="flex items-center gap-3">
                              <div
                                onClick={() =>
                                  setSelectedProof({
                                    url: proofUrlWithAuth,
                                    filename: user.payment_proof_filename,
                                    email: user.email,
                                    name: user.full_name,
                                  })
                                }
                                className="group relative h-12 w-16 cursor-pointer overflow-hidden rounded-lg border border-surface-border bg-abyss shrink-0 hover:border-glow-amber transition-all shadow-sm"
                                title="Click to view full screenshot"
                              >
                                <img
                                  src={proofUrlWithAuth}
                                  alt="Payment proof screenshot"
                                  className="h-full w-full object-cover transition-transform group-hover:scale-110"
                                  loading="lazy"
                                  onError={(e) => {
                                    // Fallback if image fails to render direct thumbnail
                                    e.currentTarget.style.display = 'none'
                                  }}
                                />
                                <div className="absolute inset-0 flex items-center justify-center bg-abyss/60 opacity-0 group-hover:opacity-100 transition-opacity">
                                  <ZoomIn className="h-4 w-4 text-glow-amber" />
                                </div>
                              </div>

                              <div className="min-w-0">
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedProof({
                                      url: proofUrlWithAuth,
                                      filename: user.payment_proof_filename,
                                      email: user.email,
                                      name: user.full_name,
                                    })
                                  }
                                  className="truncate text-xs font-medium text-ink hover:text-glow-amber flex items-center gap-1 text-left"
                                >
                                  <ImageIcon className="h-3 w-3 text-glow-amber shrink-0" />
                                  <span className="truncate max-w-[150px]">
                                    {user.payment_proof_filename || 'proof-screenshot.png'}
                                  </span>
                                </button>
                                <span className="block text-[10px] text-muted">Click thumbnail to inspect</span>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1.5 text-muted/70">
                              <FileText className="h-3.5 w-3.5" />
                              <span>No screenshot uploaded yet</span>
                            </div>
                          )}
                        </td>

                        {/* Status column */}
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          {isPending && (
                            <span className="inline-flex items-center gap-1.5 rounded-full border border-glow-amber/40 bg-glow-amber/15 px-2.5 py-1 text-[11px] font-semibold text-glow-amber">
                              <span className="h-1.5 w-1.5 rounded-full bg-glow-amber animate-ping" />
                              Pending Review
                            </span>
                          )}
                          {isApproved && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-[11px] font-semibold text-emerald-400">
                              <CheckCircle2 className="h-3 w-3" />
                              Approved & Active
                            </span>
                          )}
                          {isRejected && (
                            <div>
                              <span className="inline-flex items-center gap-1 rounded-full border border-warm-red/40 bg-warm-red/15 px-2.5 py-1 text-[11px] font-semibold text-warm-red">
                                <ShieldAlert className="h-3 w-3" />
                                Rejected
                              </span>
                              {user.rejection_reason && (
                                <p
                                  className="mt-1 text-[10px] text-muted max-w-xs truncate"
                                  title={user.rejection_reason}
                                >
                                  Reason: {user.rejection_reason}
                                </p>
                              )}
                            </div>
                          )}
                          {!isPending && !isApproved && !isRejected && (
                            <span className="inline-flex items-center gap-1 rounded-full border border-surface-border bg-surface px-2.5 py-1 text-[11px] text-muted">
                              Pending Proof
                            </span>
                          )}
                        </td>

                        {/* Action Buttons in front of each user */}
                        <td className="py-3.5 px-4 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-2">
                            {/* Approve Button */}
                            <Button
                              size="sm"
                              variant={isApproved ? 'secondary' : 'glow'}
                              disabled={isWorking || isApproved}
                              onClick={() => handleApprove(user)}
                              className={`gap-1 ${
                                isApproved
                                  ? 'opacity-60 cursor-default border-emerald-500/30 text-emerald-400'
                                  : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.25)]'
                              }`}
                            >
                              {isWorking ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Check className="h-3.5 w-3.5" />
                              )}
                              <span>{isApproved ? 'Approved' : 'Approve'}</span>
                            </Button>

                            {/* Reject Button */}
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={isWorking || isRejected}
                              onClick={() => {
                                setRejectingUser(user)
                                setRejectionReason(
                                  user.rejection_reason ||
                                    'Payment proof could not be verified. Please verify your information and try again or contact customer support.'
                                )
                              }}
                              className={`gap-1 border-warm-red/40 text-warm-red hover:bg-warm-red/15 ${
                                isRejected ? 'opacity-60 cursor-default' : ''
                              }`}
                            >
                              <X className="h-3.5 w-3.5" />
                              <span>{isRejected ? 'Rejected' : 'Reject'}</span>
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </main>

      {/* ─────────────────────────────────────────────────────────────
          3. FULL SCREEN PROOF LIGHTBOX MODAL
      ───────────────────────────────────────────────────────────── */}
      {selectedProof && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-abyss/90 backdrop-blur-md p-4 animate-fade-in">
          <div className="relative flex max-h-[92vh] max-w-4xl w-full flex-col overflow-hidden rounded-2xl border border-surface-border bg-surface shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-surface-border px-5 py-3.5">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-glow-amber/15 text-glow-amber">
                  <Eye className="h-4 w-4" />
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-ink">
                    Payment Proof Verification • {selectedProof.name || selectedProof.email}
                  </h3>
                  <p className="text-xs text-muted">{selectedProof.email}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={selectedProof.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-lg border border-surface-border p-1.5 text-muted hover:text-ink hover:bg-surface-border/50 transition-colors"
                  title="Open in new window"
                >
                  <ExternalLink className="h-4 w-4" />
                </a>
                <button
                  type="button"
                  onClick={() => setSelectedProof(null)}
                  className="rounded-lg border border-surface-border p-1.5 text-muted hover:text-ink hover:bg-surface-border/50 transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Modal Body / Image Viewer */}
            <div className="flex flex-1 items-center justify-center overflow-auto bg-abyss/80 p-4 min-h-[350px]">
              <img
                src={selectedProof.url}
                alt="Payment proof high resolution preview"
                className="max-h-[75vh] w-auto max-w-full rounded-lg object-contain shadow-md"
              />
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-surface-border bg-surface px-5 py-3 text-xs text-muted">
              <span>File: {selectedProof.filename || 'payment-proof-screenshot'}</span>
              <Button size="sm" variant="secondary" onClick={() => setSelectedProof(null)}>
                Close Preview
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────
          4. REJECTION PROMPT MODAL
      ───────────────────────────────────────────────────────────── */}
      {rejectingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-abyss/85 backdrop-blur-md p-4 animate-fade-in">
          <div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-warm-red/40 bg-surface shadow-2xl p-6 space-y-4">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-warm-red/15 text-warm-red shrink-0">
                <ShieldAlert className="h-5 w-5" />
              </span>
              <div>
                <h3 className="font-display text-base font-bold text-ink">Reject Registration Request</h3>
                <p className="text-xs text-muted mt-0.5">
                  User: <strong className="text-ink">{rejectingUser.email}</strong>
                </p>
              </div>
            </div>

            <p className="text-xs text-muted leading-relaxed">
              When rejected, the user will be prompted with this message on their waitlist screen and instructed to
              verify their information and try again, or contact customer support.
            </p>

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold text-ink">Rejection Reason Message:</span>
              <textarea
                rows={3}
                className="w-full rounded-xl border border-surface-border bg-abyss p-3 text-xs text-ink focus:border-warm-red focus:outline-none"
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Reason why the payment proof was rejected..."
              />
            </label>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-surface-border">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRejectingUser(null)}
                disabled={Boolean(actionLoadingId)}
              >
                Cancel
              </Button>
              <Button
                variant="secondary"
                size="sm"
                className="border-warm-red/50 text-warm-red hover:bg-warm-red/15"
                onClick={handleConfirmReject}
                disabled={Boolean(actionLoadingId)}
              >
                {actionLoadingId ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Rejecting...
                  </>
                ) : (
                  'Confirm Rejection'
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
export default SuperAdmin
