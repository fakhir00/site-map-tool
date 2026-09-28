# Missing account information and stalled dashboard

## Live observations

- Render `/api/health` returned HTTP 200 at revision `78ed110`, matching the
  committed checkout. The earlier deployment mismatch is no longer present.
- The deployed Vercel JavaScript points to
  `https://site-map-tool.onrender.com/api`.
- CORS preflight for `/api/auth/me` permits authorization/content-type headers
  from `https://site-map-tool.vercel.app`.
- An unauthenticated `/api/auth/me` request promptly returns the expected 401
  with the correct CORS header.
- No user token was requested or used. These checks cannot establish whether
  the user's particular signed-in request failed due to connectivity, session
  expiration, or a database issue.

## Confirmed defects and repair

The screenshot matches the initial-loading UI: skeleton cards, zero totals,
“No scans yet,” and a generic “User.” Account failures were not displayed in the
layout. Projects combined two attempts in the API client with four attempts in
React Query, each with a 45-second timeout. A stalled request could therefore
hide behind loading UI for roughly six minutes plus retry delays.

Account and project queries now share a 15-second request deadline, with no
nested retries. Failures are shown throughout the dashboard; automatic retry
occurs every 15 seconds, with an explicit Retry connection button. Network
failure preserves the sign-in token. An actual 401 still sends the user to login.

Missing data is now labeled as loading or unavailable, not an empty account.
Project summary totals wait for data, and account-dependent pages wait until the
account is loaded. The sidebar uses the account email when no full name exists.

The old health endpoint reported only whether the database initialized during
startup. Its `database: connected` value was not a current connectivity check.
Health now performs a bounded three-second `SELECT 1` probe and reports degraded
state if that check fails, without exposing database exception details or
preventing a subsequent successful health check.

## Verification and release

- 146 backend tests passed, including database outage/recovery and timeout cases.
- Dashboard lint and production build passed.
- 28 browser checks passed (27-workflow suite plus the stalled-request test).
  They cover failure visibility, manual recovery, loading, expired sessions,
  a 15-second deadline for a request that never responds, and the existing
  application workflows.

These follow-up changes are local. Commit/push and redeploy Vercel for the
dashboard repair, then manually deploy Render for the live database-health
check. Reload the dashboard after deployment. If the account still cannot load,
the visible error will identify the next diagnostic step; do not create another
account or assume that projects have been deleted.
