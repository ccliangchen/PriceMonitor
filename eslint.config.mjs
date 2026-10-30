import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    ignores: ['out/**', 'release/**', 'node_modules/**', 'backend/**', 'resources/**']
  },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'off'
    }
  }
)
