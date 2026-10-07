export default defineAppConfig({
  ui: {
    colors: {
      // The red of the Mekiki seal (see main.css).
      primary: 'vermilion',
      neutral: 'zinc',
    },
    dashboardPanel: {
      slots: {
        // The panel body is a flex column: without this, a long result list squeezes the
        // blocks above it (forms, totals) down to zero height.
        body: '*:shrink-0',
      },
    },
  },
})
