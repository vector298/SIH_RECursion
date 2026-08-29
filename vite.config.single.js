import { defineConfig, mergeConfig } from 'vite'
import { viteSingleFile } from 'vite-plugin-singlefile'
import base from './vite.config.js'

// One self-contained file: npm run build:single  ->  dist-single/index.html
// Everything (CSS, JS, assets) is inlined, so the file can be opened directly
// in a browser with no server. Works on Windows, macOS and Linux.
export default mergeConfig(base, defineConfig({
  plugins: [viteSingleFile()],
  build: {
    outDir: 'dist-single',
    cssCodeSplit: false,
    assetsInlineLimit: 100000000,
  },
}))
