// 新手第一课组件测试（V595）。
import { beforeEach, describe, expect, test } from 'vitest'
import { mount } from '@vue/test-utils'

import BeginnerGuide from '../BeginnerGuide.vue'

describe('BeginnerGuide', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  test('渲染三步动线与术语表', () => {
    const wrapper = mount(BeginnerGuide)
    expect(wrapper.text()).toContain('新手第一课')
    expect(wrapper.text()).toContain('先用长盈选好公司')
    expect(wrapper.text()).toContain('再用缠论找买卖点')
    expect(wrapper.text()).toContain('看信号可信度')
    expect(wrapper.text()).toContain('中枢')
    expect(wrapper.text()).toContain('背驰')
  })

  test('点击隐藏后持久化', async () => {
    const wrapper = mount(BeginnerGuide)
    await wrapper.get('.hide-btn').trigger('click')
    expect(wrapper.find('.beginner-guide').exists()).toBe(false)
    expect(localStorage.getItem('easy_tdx.beginner_guide.hidden')).toBe('1')
  })
})
