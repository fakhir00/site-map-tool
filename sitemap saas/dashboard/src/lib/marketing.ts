export const MARKETING_URL = (
  import.meta.env.VITE_MARKETING_URL ||
  (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
    ? 'https://sitemapseo.io'
    : 'http://127.0.0.1:4321')
).replace(/\/$/, '')

export function marketingUrl(path = '/') {
  return `${MARKETING_URL}${path.startsWith('/') ? path : `/${path}`}`
}
