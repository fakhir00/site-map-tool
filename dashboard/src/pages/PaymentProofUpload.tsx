import { type ChangeEvent, type DragEvent, type FormEvent, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  CheckCircle2,
  FileCheck,
  ImageIcon,
  Loader2,
  Mail,
  Map,
  ShieldCheck,
  UploadCloud,
  X,
} from 'lucide-react'
import { api, DEMO_BACKEND_ENABLED } from '../lib/api'
import { marketingUrl } from '../lib/marketing'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input } from '../components/ui/Input'

export function PaymentProofUpload() {
  const navigate = useNavigate()
  const location = useLocation()
  const stateData = location.state as { email?: string; fullName?: string } | null

  const storedEmail = sessionStorage.getItem('pending_verification_email') || ''
  const [email, setEmail] = useState(stateData?.email || storedEmail)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const websiteUrl = marketingUrl('/')

  const handleFileSelection = (file: File) => {
    setError('')
    setSelectedFile(file)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
    }
    // Create preview for image files
    if (file.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(file))
    } else {
      setPreviewUrl(null)
    }
  }

  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      handleFileSelection(file)
    }
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file) {
      handleFileSelection(file)
    }
  }

  const handleRemoveFile = () => {
    setSelectedFile(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')

    const cleanEmail = email.trim().toLowerCase()
    if (!cleanEmail) {
      setError('Please provide your registered account email.')
      return
    }

    if (!selectedFile) {
      setError('Please select or drag a picture of your payment proof.')
      return
    }

    setLoading(true)

    try {
      const formData = new FormData()
      formData.append('email', cleanEmail)
      formData.append('file', selectedFile)

      await api.upload('/auth/upload-payment-proof', formData)

      sessionStorage.setItem('pending_verification_email', cleanEmail)
      navigate('/waitlist', {
        replace: true,
        state: { email: cleanEmail, status: 'pending_approval' },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload payment proof')
    } finally {
      setLoading(false)
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

        {/* Steps roadmap header */}
        <div className="mb-6 grid grid-cols-3 gap-2">
          <div className="flex items-center gap-2 rounded-xl border border-surface-border bg-surface/60 p-2.5 text-xs">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
            <div className="truncate">
              <p className="font-semibold text-ink">Step 1</p>
              <p className="truncate text-muted">Account</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-glow-amber/50 bg-glow-amber/10 p-2.5 text-xs shadow-[0_0_15px_rgba(245,165,36,0.15)]">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-glow-amber text-[10px] font-bold text-abyss">
              2
            </span>
            <div className="truncate">
              <p className="font-semibold text-glow-amber">Step 2</p>
              <p className="truncate text-glow-amber/80">Payment proof</p>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-surface-border bg-surface/30 p-2.5 text-xs opacity-60">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-surface-border text-[10px] font-semibold text-muted">
              3
            </span>
            <div className="truncate">
              <p className="font-semibold text-ink">Step 3</p>
              <p className="truncate text-muted">Waitlist</p>
            </div>
          </div>
        </div>

        <Card className="p-7 sm:p-8">
          <div className="mb-6 text-center">
            <h1 className="font-display text-2xl font-bold tracking-tight">Send Payment Proof</h1>
            <p className="mt-2 text-sm leading-6 text-muted">
              Upload a picture of your receipt or transaction screenshot in any image format to verify your account.
            </p>
          </div>

          {DEMO_BACKEND_ENABLED && (
            <div className="mb-5 rounded-xl border border-glow-amber/30 bg-glow-amber/10 px-3 py-2 text-sm text-glow-amber">
              Demo mode is active. You can upload any sample image to test the verification pipeline.
            </div>
          )}

          <form className="space-y-5" onSubmit={handleSubmit}>
            {error && (
              <div className="rounded-xl border border-warm-red/30 bg-warm-red/10 px-3 py-2.5 text-sm text-warm-red">
                {error}
              </div>
            )}

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink">Registered Email Address</span>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                <Input
                  autoComplete="email"
                  className="pl-9"
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@company.com"
                  required
                  type="email"
                  value={email}
                />
              </div>
            </label>

            <div>
              <span className="mb-1.5 block text-sm font-medium text-ink">Payment Screenshot / Receipt</span>

              {!selectedFile ? (
                <div
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  className={`group relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
                    isDragging
                      ? 'border-glow-amber bg-glow-amber/10 scale-[1.01]'
                      : 'border-surface-border bg-surface/40 hover:border-surface-border hover:bg-surface/70'
                  }`}
                >
                  <input
                    type="file"
                    accept="image/*,.png,.jpg,.jpeg,.webp,.gif,.bmp,.svg,.heic,.heif,.tiff,.pdf"
                    onChange={handleFileInputChange}
                    className="absolute inset-0 cursor-pointer opacity-0"
                    id="payment-proof-input"
                  />
                  <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-surface border border-surface-border group-hover:scale-105 group-hover:border-glow-amber/40 transition-all text-glow-amber shadow-sm">
                    <UploadCloud className="h-7 w-7" />
                  </div>
                  <p className="text-sm font-semibold text-ink">
                    Drop your screenshot here, or <span className="text-glow-amber underline">browse files</span>
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    Supports any image format (PNG, JPG, WebP, GIF, SVG, HEIC, etc.)
                  </p>
                </div>
              ) : (
                <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface/70 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      {previewUrl ? (
                        <div className="h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-surface-border bg-abyss">
                          <img
                            src={previewUrl}
                            alt="Payment preview"
                            className="h-full w-full object-cover"
                          />
                        </div>
                      ) : (
                        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-xl border border-surface-border bg-surface text-glow-amber">
                          <ImageIcon className="h-7 w-7" />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <FileCheck className="h-4 w-4 shrink-0 text-emerald-400" />
                          <p className="truncate text-sm font-semibold text-ink">{selectedFile.name}</p>
                        </div>
                        <p className="mt-0.5 text-xs text-muted">
                          {(selectedFile.size / 1024 / 1024).toFixed(2)} MB • Ready to upload
                        </p>
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={handleRemoveFile}
                      className="text-muted hover:text-warm-red hover:bg-warm-red/10"
                      aria-label="Remove uploaded file"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-surface-border bg-surface/30 p-3.5 text-xs text-muted">
              <div className="flex items-start gap-2.5">
                <ShieldCheck className="h-4 w-4 shrink-0 text-glow-amber mt-0.5" />
                <p className="leading-relaxed">
                  Your payment proof is encrypted and sent directly to our superadmin verification queue. Once verified,
                  your account will be automatically approved and ready for use.
                </p>
              </div>
            </div>

            <Button
              className="w-full"
              disabled={loading || !selectedFile}
              size="lg"
              type="submit"
              variant="glow"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Uploading proof...
                </>
              ) : (
                <>
                  Submit payment proof & join waitlist
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </form>

          <div className="mt-6 flex flex-col items-center justify-center gap-2 border-t border-surface-border pt-5 text-center text-xs text-muted">
            <p>
              Already submitted proof?{' '}
              <Link
                className="font-semibold text-glow-amber hover:text-[#ffb63d] hover:underline"
                to="/waitlist"
                state={{ email }}
              >
                Check waitlist approval status
              </Link>
            </p>
            <p>
              Need to change credentials?{' '}
              <Link className="text-muted hover:text-ink hover:underline" to="/register">
                Back to registration
              </Link>
            </p>
          </div>
        </Card>
      </div>
    </main>
  )
}
export default PaymentProofUpload
