import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import prettier from 'eslint-config-prettier'
import tseslint from 'typescript-eslint'
import globals from 'globals'

// V391 前端 lint 落地：eslint flat config（务实级）。
// 只拦真正会出错的：未定义变量、语法错误、Vue 模板基础规则；
// 不启用 no-explicit-any 等强类型洁癖规则——项目现有 44 个 Vue 文件
// 大量使用 any 作为「后端动态 JSON 边界」的务实选择，强制改造无收益。
export default [
  { ignores: ['dist/**', 'node_modules/**', 'src/**/*.test.ts', 'src/**/__tests__/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/essential'],
  prettier,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-useless-assignment': 'off',
      // 现有模板中 `a < b` 等比较表达式会让 vue-eslint-parser 误判为标签起始，
      // vue-tsc 与 vite build 均已通过，属解析器误报，务实关闭。
      'vue/no-parsing-error': 'off',
      // 既有模板中 v-for 与 v-if 混用是历史结构，重构收益低风险高，务实关闭。
      'vue/no-use-v-if-with-v-for': 'off',
    },
  },
]
