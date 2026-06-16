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

## Vercel deployment

Deploy the `dashboard` directory as the Vercel project root.

Add this environment variable in Vercel before building:

```bash
VITE_API_URL=https://your-deployed-backend.example.com/api
```

The backend must also allow the dashboard origin. Set the backend environment variable to your Vercel URL:

```bash
FRONTEND_URL=https://your-dashboard.vercel.app
```

If you use both preview and production URLs, separate them with commas:

```bash
FRONTEND_URL=https://your-dashboard.vercel.app,https://your-domain.com
```

After changing Vercel environment variables, redeploy the dashboard so Vite bakes the new value into the production bundle.
