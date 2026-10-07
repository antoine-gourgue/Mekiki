// Pages reachable without an account; a signed-in user skips the forms.
const PUBLIC_PAGES = new Set(['/accueil', '/connexion', '/inscription'])
const FORMS = new Set(['/connexion', '/inscription'])

export default defineNuxtRouteMiddleware((to) => {
  const token = useSessionToken()
  if (PUBLIC_PAGES.has(to.path)) {
    if (token.value && FORMS.has(to.path)) return navigateTo('/')
    return
  }
  if (token.value) return
  if (to.path === '/') return navigateTo('/accueil')
  return navigateTo({ path: '/connexion', query: { redirect: to.fullPath } })
})
