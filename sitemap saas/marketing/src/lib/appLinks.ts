const dashboardBaseUrl = (
  import.meta.env.PUBLIC_DASHBOARD_URL ||
  (import.meta.env.DEV ? 'http://127.0.0.1:5173' : 'https://app.sitemapseo.io')
).replace(/\/$/, '');

export function dashboardUrl(path = '/') {
  return `${dashboardBaseUrl}${path.startsWith('/') ? path : `/${path}`}`;
}
