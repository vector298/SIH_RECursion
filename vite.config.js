import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Standard build: npm run build  ->  dist/
// Relative base so dist/ can also be opened from a file server or any subpath.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: { outDir: 'dist' },
})
