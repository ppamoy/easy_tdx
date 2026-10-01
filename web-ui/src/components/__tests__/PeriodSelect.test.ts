// PeriodSelect 单测：渲染全量 7 档周期、中文标签、v-model 双向绑定。
import { describe, expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PeriodSelect from '../PeriodSelect.vue'
import type { Category } from '../../types'

describe('PeriodSelect', () => {
  test('默认渲染全量 7 档周期，含日线/周线/月线/分钟线', () => {
    const w = mount(PeriodSelect)
    const opts = w.findAll('option').map((o) => o.text())
    expect(opts).toContain('日线')
    expect(opts).toContain('周线')
    expect(opts).toContain('月线')
    expect(opts).toContain('30分钟')
    expect(opts).toContain('60分钟')
    expect(w.findAll('option')).toHaveLength(7)
    w.unmount()
  })

  test('v-model 双向绑定：选择后 emit update:modelValue', async () => {
    const w = mount(PeriodSelect, { props: { modelValue: 'DAY' as Category } })
    await w.find('select').setValue('MIN_30')
    expect(w.emitted('update:modelValue')?.[0]).toEqual(['MIN_30'])
    w.unmount()
  })

  test('options 属性可裁剪可选集合', () => {
    const w = mount(PeriodSelect, {
      props: { modelValue: 'DAY' as Category, options: ['DAY', 'MIN_30'] as Category[] },
    })
    expect(w.findAll('option')).toHaveLength(2)
    w.unmount()
  })

  test('label 文案渲染', () => {
    const w = mount(PeriodSelect, { props: { label: '周期' } })
    expect(w.find('label').text()).toBe('周期')
    w.unmount()
  })

  test('disabled 透传给 select', () => {
    const w = mount(PeriodSelect, { props: { disabled: true } })
    expect((w.find('select').element as HTMLSelectElement).disabled).toBe(true)
    w.unmount()
  })
})
