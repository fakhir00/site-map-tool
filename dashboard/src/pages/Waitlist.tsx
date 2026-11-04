import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Clock,
  HelpCircle,
  Loader2,
  Mail,
  Map,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { api, DEMO_BACKEND_ENABLED, type RegistrationStatus } from '../lib/api'
import { marketingUrl } from '../lib/marketing'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

export function Waitlist() {
  const navigate = useNavigate()
  const location = useLocation()
  const stateData = location.state as {
    email?: string
    status?: string
    rejection_reason?: string
  } | null

  const storedEmail = sessionStorage.getItem('pending_verification_email') || ''
  const [email, setEmail] = useState(stateData?.email || storedEmail)
  const [inputEmail, setInputEmail] = useState(stateData?.email || storedEmail)
  const [status, setStatus] = useState<string>(stateData?.status || 'pending_approval')
  const [rejectionReason, setRejectionReason] = useState<string | null>(
    stateData?.rejection_reason || null
  )
  const [loading, setLoading] = useState(false)
  const [lastChecked, setLastChecked] = useState<Date | null>(new Date())
  const [error, setError] = useState('')

  const websiteUrl = marketingUrl('/')

  const fetchStatus = async (targetEmail: string) => {
    const cleanEmail = targetEmail.trim().toLowerCase()
    if (!cleanEmail) return

    setLoading(true)
    setError('')
    try {
      const data = await api.get<RegistrationStatus>(
        `/auth/registration-status?email=${encodeURIComponent(cleanEmail)}`
      )
      setStatus(data.status)
      setRejectionReason(data.rejection_reason)
      setLastChecked(new Date())
      sessionStorage.setItem('pending_verification_email', cleanEmail)
      setEmail(cleanEmail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    if (!email) return

    const timer = setTimeout(() => {
      if (!cancelled) {
        fetchStatus(email)
      }
    }, 0)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [email])

  const handleManualCheck = () => {
    if (inputEmail) {
      fetchStatus(inputEmail)
    }
  }

  return (
    <main className="warm-glow-bg flex min-h-screen items-center justify-center bg-abyss px-4 py-12 text-ink">
      <div className="animate-fade-up w-full max-w-lg">
        <a href={websiteUrl} aria-label="CrawlGap homepage" className="mb-6 flex flex-col items-center gap-2">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-glow-amber/15 text-glow-amber ring-1 ring-glow-amber/30 shadow-[0_0_28px_rgba(245,165,36,0.25)]">
            <Map className="h-6 w-6" />
          </span>
          <span className="font-display text-lg font-bold tracking-tight">CrawlGap</span>
        </a>

        {DEMO_BACKEND_ENABLED && (
          <div className="mb-4 rounded-xl border border-glow-amber/30 bg-glow-amber/10 px-3 py-2 text-xs text-glow-amber">
            Demo mode: Open{' '}
            <Link to="/superadmin" className="font-bold underline">
              /superadmin
            </Link>{' '}
            in another tab to approve or reject this request.
          </div>
        )}

        <Card className="p-7 sm:p-8">
          {/* Email selector if email not preset */}
          {!email ? (
            <div className="space-y-4">
              <div className="text-center">
                <h1 className="font-display text-2xl font-bold tracking-tight">Check Approval Status</h1>
                <p className="mt-2 text-sm text-muted">
                  Enter the email address you registered with to check your waitlist status.
                </p>
              </div>

              {error && (
                <div className="rounded-xl border border-warm-red/30 bg-warm-red/10 px-3 py-2 text-sm text-warm-red">
                  {error}
                </div>
              )}

              <div className="space-y-3">
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                  <Input
                    className="pl-9"
                    onChange={(e) => setInputEmail(e.target.value)}
                    placeholder="you@company.com"
                    type="email"
                    value={inputEmail}
                  />
                </div>
                <Button className="w-full" onClick={handleManualCheck} variant="glow" disabled={loading}>
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Check Status'}
                </Button>
              </div>
            </div>
          ) : status === 'approved' ? (
            /* STATE: APPROVED */
            <div className="text-center space-y-6">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30 shadow-[0_0_30px_rgba(16,185,129,0.25)]">
                <Sparkles className="h-8 w-8" />
              </div>

              <div>
                <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Application Approved
                </div>
                <h1 className="mt-3 font-display text-2xl font-bold tracking-tight text-ink">
                  Account Created & Activated!
                </h1>
                <p className="mt-2 text-sm text-muted leading-relaxed">
                  Your payment proof has been verified by the administrator. Your account is ready and you can now sign in
                  to access all GapCrawl features.
                </p>
              </div>

              <div className="rounded-2xl border border-surface-border bg-surface/60 p-4 text-xs text-muted">
                <span className="block font-medium text-ink">{email}</span>
                <span className="text-[11px] text-emerald-400">Status: Active & Approved</span>
              </div>

              <Button
                className="w-full"
                size="lg"
                variant="glow"
                onClick={() => navigate('/login', { state: { email } })}
              >
                Sign in to your dashboard
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          ) : status === 'rejected' ? (
            /* STATE: REJECTED */
            <div className="space-y-6">
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-warm-red/15 text-warm-red ring-1 ring-warm-red/30 shadow-[0_0_30px_rgba(244,63,94,0.2)]">
                  <ShieldAlert className="h-8 w-8" />
                </div>
                <div className="inline-flex items-center gap-1.5 rounded-full border border-warm-red/30 bg-warm-red/10 px-3 py-1 text-xs font-semibold text-warm-red">
                  <AlertCircle className="h-3.5 w-3.5" />
                  Payment Proof Rejected
                </div>
                <h1 className="mt-3 font-display text-2xl font-bold tracking-tight text-ink">
                  Verification Unsuccessful
                </h1>
                <p className="mt-2 text-sm text-muted leading-relaxed">
                  Your registration request could not be approved with the provided payment proof.
                </p>
              </div>

              {/* Rejection Message Box */}
              <div className="rounded-2xl border border-warm-red/30 bg-warm-red/10 p-4 text-sm">
                <p className="font-semibold text-warm-red">Administrator Note:</p>
                <p className="mt-1 text-xs text-ink/90 leading-relaxed">
                  {rejectionReason ||
                    'Payment proof could not be verified. Please verify your payment information and try again or contact customer support.'}
                </p>
              </div>

              <div className="rounded-2xl border border-surface-border bg-surface/40 p-4 text-xs text-muted space-y-1">
                <p className="font-medium text-ink">What you should do next:</p>
                <p className="leading-relaxed">
                  Please verify your transaction screenshot, make sure the date, amount, and reference ID are clearly
                  legible, and try re-uploading below, or contact support if you believe this is an error.
                </p>
              </div>

              <div className="space-y-3">
                <Button
                  className="w-full"
                  size="lg"
                  variant="glow"
                  onClick={() => navigate('/payment-proof', { state: { email } })}
                >
                  <RotateCcw className="h-4 w-4" />
                  Verify Information & Try Again
                </Button>

                <a
                  href={`mailto:support@gapcrawl.com?subject=Payment Proof Verification Issue - ${encodeURIComponent(
                    email
                  )}`}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-surface-border bg-surface/70 px-4 py-2.5 text-sm font-medium text-ink hover:bg-surface hover:border-glow-amber/40 transition-colors"
                >
                  <HelpCircle className="h-4 w-4 text-glow-amber" />
                  Contact Customer Support
                </a>
              </div>
            </div>
          ) : status === 'pending_proof' ? (
            /* STATE: PENDING PROOF */
            <div className="text-center space-y-6">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-glow-amber/15 text-glow-amber ring-1 ring-glow-amber/30">
                <AlertCircle className="h-7 w-7" />
              </div>
              <div>
                <h1 className="font-display text-2xl font-bold tracking-tight">Payment Proof Required</h1>
                <p className="mt-2 text-sm text-muted">
                  We need your payment proof screenshot before your account can be reviewed and approved.
                </p>
              </div>
              <Button
                className="w-full"
                size="lg"
                variant="glow"
                onClick={() => navigate('/payment-proof', { state: { email } })}
              >
                Upload payment proof now
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            /* STATE: PENDING APPROVAL (WAITLIST) */
            <div className="space-y-6">
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-glow-amber/15 text-glow-amber ring-1 ring-glow-amber/30 shadow-[0_0_28px_rgba(245,165,36,0.2)]">
                  <Clock className="h-8 w-8 animate-pulse" />
                </div>
                <div className="inline-flex items-center gap-2 rounded-full border border-glow-amber/30 bg-glow-amber/10 px-3.5 py-1 text-xs font-semibold text-glow-amber">
                  <span className="h-2 w-2 rounded-full bg-glow-amber animate-ping" />
                  Awaiting Superadmin Approval
                </div>
                <h1 className="mt-3 font-display text-2xl font-bold tracking-tight text-ink">
                  You're on the Waitlist!
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  We have received your payment proof for <strong className="text-ink">{email}</strong>. Our team is
                  reviewing the verification request.
                </p>
              </div>

              {/* Progress Tracker */}
              <div className="space-y-3 rounded-2xl border border-surface-border bg-surface/50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">Verification Status</p>

                <div className="space-y-2.5 text-xs">
                  <div className="flex items-center gap-3 text-ink">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                    <span>Account credentials created</span>
                  </div>
                  <div className="flex items-center gap-3 text-ink">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                    <span>Payment proof screenshot uploaded</span>
                  </div>
                  <div className="flex items-center gap-3 text-glow-amber font-medium">
                    <span className="flex h-4 w-4 items-center justify-center rounded-full bg-glow-amber/20 text-[10px] text-glow-amber shrink-0 animate-pulse">
                      ⏳
                    </span>
                    <span>Admin reviewing payment proof (In review...)</span>
                  </div>
                  <div className="flex items-center gap-3 text-muted">
                    <span className="flex h-4 w-4 items-center justify-center rounded-full border border-surface-border text-[10px] shrink-0">
                      ○
                    </span>
                    <span>Account activated & dashboard opened</span>
                  </div>
                </div>
              </div>

              {error && (
                <div className="rounded-xl border border-warm-red/30 bg-warm-red/10 px-3 py-2 text-sm text-warm-red">
                  {error}
                </div>
              )}

              <div className="flex items-center justify-between text-xs text-muted">
                <span>
                  {lastChecked ? `Last checked: ${lastChecked.toLocaleTimeString()}` : 'Checking automatically'}
                </span>
                <button
                  type="button"
                  onClick={() => fetchStatus(email)}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 font-medium text-glow-amber hover:text-[#ffb63d] transition-colors"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                  Check status now
                </button>
              </div>

              <div className="rounded-xl border border-surface-border bg-surface/30 p-3 text-center text-xs text-muted">
                Reviews are usually processed quickly. Once approved, you can sign in directly from the login page.
              </div>

              <div className="pt-2">
                <Button
                  className="w-full"
                  variant="secondary"
                  size="md"
                  onClick={() => navigate('/login', { state: { email } })}
                >
                  Return to sign in
                </Button>
              </div>
            </div>
          )}

          <div className="mt-6 border-t border-surface-border pt-4 text-center text-xs text-muted">
            Need help?{' '}
            <a
              href={`mailto:support@gapcrawl.com?subject=Payment Proof Verification Help - ${encodeURIComponent(email)}`}
              className="text-glow-amber hover:underline"
            >
              Contact customer support
            </a>
          </div>
        </Card>
      </div>
    </main>
  )
}
export default Waitlist
