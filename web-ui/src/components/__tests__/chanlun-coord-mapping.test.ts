/**
 * V733：买卖点标记**逐点坐标**契约测试 —— 真后端 ground truth × 真组件。
 *
 * 补的是哪个缺口
 * --------------
 * `mmd-chart-contract.test.ts` 用的是**人造 K 线**（单调递增、bar_index 与下标
 * 一一对应），因此它锁住的只是「字段有没有被搬运」，无法暴露：
 *   - 真实数据中 bar_index 与数组下标**不一致**时的错位；
 *   - 真实日期有重复/跳空（30min 一天多根）时的 date 回退分支；
 *   - 真实 anchor_val 落在 K 线极值之外时的取价。
 *
 * 本测试改用**真后端算出的 ground truth**（scripts/gen_chanlun_gt.py 由
 * `easy_tdx.chanlun.analyser` 跑真 fixture 生成），喂进**真组件**，逐点断言：
 *   每个买卖点标记的 (x=bar_index, y=anchor_val) 与后端一致。
 *
 * 牙齿（防空转）
 * --------------
 * 1. ground truth 非空，且至少覆盖 2 种买卖点类型；
 * 2. 标记数量必须与 ground truth **完全相等**（漏画/多画直接失败）；
 * 3. 注入对照：把 anchor_val 抹掉 ⇒ 价格必须偏离（证明判据能抓到 V731 那个 bug）。
 */

import { describe, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

import gt from './__fixtures__/chanlun_gt.json'
import type { ChanlunMmd } from '../ChanlunChart.vue'
import type { Bar } from '../../types'

// V731: jsdom 无 canvas，不 stub 的话 zrender 会在 clearRect 上抛错
let lastOption: any = null
const instance = {
  setOption: (opt: any) => {
    lastOption = opt
  },
  resize: () => undefined,
  dispose: () => undefined,
  getOption: () => undefined,
}
vi.mock('../../echarts-setup', () => {
  const noop = () => undefined
  return {
    default: { init: () => instance, use: noop, registerTheme: noop },
    UP_COLOR: '#ef4146',
    DOWN_COLOR: '#18a058',
    FX_COLOR: '#ffffff',
    FX_BORDER_COLOR: '#1f2430',
  }
})

import ChanlunChart from '../ChanlunChart.vue'

type GtCase = {
  bars: Bar[]
  mmds: ChanlunMmd[]
}

const CASES = gt as unknown as Record<string, GtCase>

async function renderCase(c: GtCase) {
  lastOption = null
  const wrapper = mount(ChanlunChart, {
    props: {
      bars: c.bars,
      mmds: c.mmds,
      bis: [],
      xds: [],
      zss: [],
      fxs: [],
      bcs: [],
    },
    global: { plugins: [createPinia()] },
    attachTo: document.body,
  })
  await flushPromises()
  wrapper.unmount()
  return lastOption
}

/** 买卖点是「买点/卖点」两条 scatter series，data 项为 { name, value:[x, y] }。 */
function collectMarks(opt: any): Array<{ name: string; x: number; y: number }> {
  const out: Array<{ name: string; x: number; y: number }> = []
  for (const s of opt?.series ?? []) {
    if (s?.name !== '买点' && s?.name !== '卖点') continue
    for (const d of s?.data ?? []) {
      if (!Array.isArray(d?.value) || d.value.length < 2) continue
      out.push({ name: d.name ?? s.name, x: d.value[0], y: d.value[1] })
    }
  }
  return out
}

describe('买卖点逐点坐标契约（真后端 ground truth × 真组件）', () => {
  test('牙齿：ground truth 非空且覆盖多种买卖点类型', () => {
    const all = Object.values(CASES).flatMap((c) => c.mmds)
    expect(all.length).toBeGreaterThan(0)
    const types = new Set(all.map((m) => m.type))
    expect(types.size).toBeGreaterThanOrEqual(2)
    // 每个买卖点都必须带 bar_index 与 anchor_val，否则无法逐点比对
    for (const m of all) {
      expect(m.bar_index, `买卖点 ${m.type} 缺 bar_index`).toBeTypeOf('number')
      expect(m.anchor_val, `买卖点 ${m.type} 缺 anchor_val`).toBeTypeOf('number')
    }
  })

  for (const [name, c] of Object.entries(CASES)) {
    test(`${name}：每个标记都落在后端指定的 bar_index 与 anchor_val 上`, async () => {
      const opt = await renderCase(c)
      const marks = collectMarks(opt)

      // 牙齿 2：数量必须全等，不做「部分通过」
      expect(marks.length, `${name} 标记数 ${marks.length} != ground truth ${c.mmds.length}`).toBe(
        c.mmds.length,
      )

      // 逐点比对：按 bar_index 排序后一一对应
      const truth = [...c.mmds].sort((a, b) => (a.bar_index ?? 0) - (b.bar_index ?? 0))
      const got = [...marks].sort((a, b) => a.x - b.x)

      for (let i = 0; i < truth.length; i++) {
        const t = truth[i]
        const g = got[i]
        expect(
          g.x,
          `${name} 第 ${i} 个 ${t.type} 横轴错位：${g.x} != bar_index ${t.bar_index}`,
        ).toBe(t.bar_index)
        expect(
          g.y,
          `${name} 第 ${i} 个 ${t.type} 纵轴错位：${g.y} != anchor_val ${t.anchor_val}`,
        ).toBeCloseTo(t.anchor_val as number, 6)
      }
    })
  }

  test('对照：抹掉 anchor_val ⇒ 价格必须偏离（证明判据能抓到 V731 漏映射）', async () => {
    const c = Object.values(CASES).find((x) => x.mmds.length >= 2)
    expect(c, '需要至少一个含 2 个以上买卖点的用例').toBeTruthy()

    // 正常：精确等于 anchor_val
    const okMarks = collectMarks(await renderCase(c as GtCase))
    // 对照：抹掉 anchor_val（复现 V731 的 mapMmds 漏映射）
    const broken: GtCase = {
      bars: (c as GtCase).bars,
      mmds: (c as GtCase).mmds.map((m) => ({ ...m, anchor_val: undefined })),
    }
    const badMarks = collectMarks(await renderCase(broken))

    expect(badMarks.length).toBe(okMarks.length)

    const okSorted = [...okMarks].sort((a, b) => a.x - b.x)
    const badSorted = [...badMarks].sort((a, b) => a.x - b.x)
    const truth = [...(c as GtCase).mmds].sort((a, b) => (a.bar_index ?? 0) - (b.bar_index ?? 0))

    // 横轴不受影响（bar_index 仍在），纵轴必须至少有一处偏离 anchor_val
    const deviated = truth.filter(
      (t, i) => Math.abs(badSorted[i].y - (t.anchor_val as number)) > 1e-6,
    )
    expect(
      deviated.length,
      '对照组价格竟与 anchor_val 完全一致 ⇒ 说明 anchor_val 判据形同虚设',
    ).toBeGreaterThan(0)
    // 正常组则必须全部精确命中（否则上面的逐点测试就是空过）
    for (let i = 0; i < truth.length; i++) {
      expect(Math.abs(okSorted[i].y - (truth[i].anchor_val as number))).toBeLessThan(1e-6)
    }
  })
})
