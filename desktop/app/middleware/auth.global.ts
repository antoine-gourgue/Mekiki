// Pages reachable without an account; a signed-in user skips the forms.
const PUBLIC_PAGES = new Set(['/accueil', '/connexion', '/inscription'])
const FORMS = new Set(['/connexion', '/inscription'])

export default defineNuxtRouteMiddleware((to) => {
  // The public website has no engine: everything but its own pages leads to the landing page.
  if (useRuntimeConfig().public.showcase) {
    return PUBLIC_PAGES.has(to.path) ? undefined : navigateTo('/accueil')
  }
  const token = useSessionToken()
  if (PUBLIC_PAGES.has(to.path)) {
    if (token.value && FORMS.has(to.path)) return navigateTo('/')
    return
  }
  if (token.value) return
  if (to.path === '/') return navigateTo('/accueil')
  return navigateTo({ path: '/connexion', query: { redirect: to.fullPath } })
})
