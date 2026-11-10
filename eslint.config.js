import js from '@eslint/js';
import globals from 'globals';
export default [
  { ignores: ['dist/**', 'node_modules/**', 'models/**', 'outputs/**', '.venv*/**', '.local/**'] },
  js.configs.recommended,
  { files: ['web/**/*.js'], languageOptions: { globals: globals.browser } },
  { files: ['*.js'], languageOptions: { globals: globals.node } },
];
