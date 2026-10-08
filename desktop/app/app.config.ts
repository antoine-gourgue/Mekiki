export default defineAppConfig({
  ui: {
    colors: {
      // The red of the Mekiki seal and the warm dark grey of the interface (see main.css).
      primary: 'vermilion',
      neutral: 'ink',
    },
    button: {
      defaultVariants: { size: 'lg' },
      compoundVariants: [
        {
          // White on the seal red, as on the logo: the lighter red is only for text.
          color: 'primary',
          variant: 'solid',
          class:
            'text-white bg-vermilion-500 hover:bg-vermilion-600 active:bg-vermilion-600 disabled:bg-vermilion-500 aria-disabled:bg-vermilion-500',
        },
      ],
    },
    input: { defaultVariants: { size: 'lg' } },
    inputNumber: { defaultVariants: { size: 'lg' } },
    select: { defaultVariants: { size: 'lg' } },
    selectMenu: { defaultVariants: { size: 'lg' } },
    textarea: { defaultVariants: { size: 'lg' } },
    card: {
      variants: {
        variant: {
          outline: { root: 'bg-muted' },
        },
      },
    },
    table: {
      slots: {
        tbody: 'divide-muted',
        th: 'px-5 py-3 text-xs font-medium whitespace-nowrap text-dimmed',
        td: 'px-5 py-3 text-default',
        separator: 'bg-(--ui-border)',
      },
    },
    badge: {
      slots: { base: 'rounded-full' },
    },
    dashboardSidebar: {
      slots: {
        root: 'bg-[#121116]',
        header: 'px-5',
        body: 'px-3.5 gap-5',
        footer: 'px-3.5 py-3',
      },
    },
    dashboardNavbar: {
      slots: {
        root: 'h-auto min-h-(--ui-header-height) border-b-0 px-4 pt-6 sm:px-8 lg:px-10',
        title: 'text-2xl font-semibold tracking-tight',
      },
    },
    dashboardToolbar: {
      slots: {
        root: 'min-h-0 border-b-0 px-4 pt-2 pb-1 sm:px-8 lg:px-10',
      },
    },
    dashboardPanel: {
      slots: {
        // The panel body is a flex column: without this, a long result list squeezes the
        // blocks above it (forms, totals) down to zero height.
        body: '*:shrink-0 px-4 py-5 sm:px-8 sm:py-6 lg:px-10',
      },
    },
  },
})
