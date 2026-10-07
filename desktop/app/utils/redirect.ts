/**
 * Page to open after signing in: the `redirect` query when it is a path inside the app,
 * the dashboard otherwise (an absolute or protocol-relative URL could leave the app).
 */
export function afterSignIn(redirect: unknown): string {
  if (typeof redirect !== 'string' || !redirect.startsWith('/') || redirect.startsWith('//')) {
    return '/'
  }
  return redirect
}
