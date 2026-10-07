export default defineAppConfig({
  ui: {
    colors: {
      primary: 'indigo',
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
