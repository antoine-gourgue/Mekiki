// @ts-check
import withNuxt from './.nuxt/eslint.config.mjs'

export default withNuxt({
  ignores: ['src-tauri/**'],
}).append({
  rules: {
    // Formatting belongs to Prettier, which writes void elements as <img />.
    'vue/html-self-closing': 'off',
  },
})
