import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import type { Connect } from 'vite'
// Figma source files are named dashboard.html/profile.html. Vite's default
// fallback would otherwise serve those artifacts instead of the Vue routes.
const appRoutes: Connect.NextHandleFunction = (request, _response, next) => {
  const url = new URL(request.url || '/', 'http://localhost')
  if (request.method === 'GET' && /^\/(dashboard|data|history|profile)\/?$/.test(url.pathname) && request.headers.accept?.includes('text/html')) {
    request.url = `/index.html${url.search}`
  }
  next()
}
export default defineConfig({
  plugins: [vue(), { name: 'iot-app-routes', configureServer: server => { server.middlewares.use(appRoutes) }, configurePreviewServer: server => { server.middlewares.use(appRoutes) } }],
  server: { strictPort: true }, build: { target: 'es2022' },
  test: { include: ['tests/unit/**/*.test.ts'] },
})
