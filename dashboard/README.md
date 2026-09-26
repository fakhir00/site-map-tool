# SiteMapSEO Dashboard

React/Vite dashboard for the SiteMapSEO backend API.

## Local development

```bash
npm install
npm run dev
```

The local dashboard expects the backend at:

```bash
http://localhost:8000/api
```

Override it when needed:

```bash
VITE_API_URL=https://your-backend.example.com/api npm run dev
```

To run the dashboard without the FastAPI backend, enable the browser-backed demo backend:

```bash
VITE_ENABLE_DEMO_BACKEND=true npm run dev
```

## Browser regression checks

Run `npm run test:browser` with Playwright Chromium installed. To use an existing
Chrome installation, set `PLAYWRIGHT_CHROME_PATH` to its executable. Tests start
Vite on port 4173 and mock API responses; they do not modify production accounts
or spend provider credits. Run `npm run lint` and `npm run build` separately.

## Vercel deployment

Deploy the `dashboard` directory as the Vercel project root.

Add this environment variable in Vercel before building:

```bash
VITE_API_URL=https://your-deployed-backend.example.com/api
```

If you want the deployed dashboard to run as a self-contained demo instead, set:

```bash
VITE_ENABLE_DEMO_BACKEND=true
```

Without `VITE_API_URL`, production uses the same-origin `/api` endpoint. Configure a reverse proxy for it or set the backend URL above. Demo mode is enabled only when explicitly requested; demo accounts and results stay in the browser and do not perform real scans.

The backend must also allow the dashboard origin. Set the backend environment variable to your Vercel URL:

```bash
FRONTEND_URL=https://your-dashboard.vercel.app
```

If you use both preview and production URLs, separate them with commas:

```bash
FRONTEND_URL=https://your-dashboard.vercel.app,https://your-domain.com
```

After changing Vercel environment variables, redeploy the dashboard so Vite bakes the new value into the production bundle.
