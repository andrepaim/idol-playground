import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  root: 'web',
  build: { outDir: '../dist', emptyOutDir: true, rolldownOptions: { input: {
    studio: fileURLToPath(new URL('./web/index.html', import.meta.url)),
    characters: fileURLToPath(new URL('./web/characters.html', import.meta.url)),
    play: fileURLToPath(new URL('./web/play.html', import.meta.url)),
  }} },
  server: { proxy: { '/api': 'http://127.0.0.1:8000', '/outputs': 'http://127.0.0.1:8000' } },
});
