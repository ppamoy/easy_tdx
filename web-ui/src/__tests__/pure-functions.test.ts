/**
 * 纯函数测试：format.ts + market.ts（V389）。
 */

import { describe, expect, test } from 'vitest'

import { fmt2, fmtAccPct, fmtAccSigned, fmtPct, fmtPf } from '../format'
import { detectMarket, marketLabel, toSymbol } from '../market'
import { formatError } from '../api'

describe('format', () => {
  test('fmt2：正常数字保留两位小数', () => {
    expect(fmt2(12.345)).toBe('12.35')
    expect(fmt2(0)).toBe('0.00')
  })

  test('fmt2：null/undefined/NaN/Inf 返回占位符', () => {
    expect(fmt2(null)).toBe('-')
    expect(fmt2(undefined)).toBe('-')
    expect(fmt2(Number.NaN)).toBe('-')
    expect(fmt2(Number.POSITIVE_INFINITY)).toBe('-')
  })

  test('fmtPct：小数转百分比', () => {
    expect(fmtPct(0.1234)).toBe('12.34%')
    expect(fmtPct(null)).toBe('-')
    expect(fmtPct(Number.NaN)).toBe('-')
    expect(fmtPct(Number.POSITIVE_INFINITY)).toBe('-')
  })

  test('fmtAccPct / fmtAccSigned', () => {
    expect(fmtAccPct(0.076)).toBe('7.6%')
    expect(fmtAccSigned(0.05)).toBe('+5.0%')
    expect(fmtAccSigned(-0.03)).toBe('-3.0%')
    expect(fmtAccSigned(0)).toBe('0.0%') // V514: 0 不带 '+'（中性）
    expect(fmtAccSigned(null)).toBe('-')
    expect(fmtAccPct(Number.NaN)).toBe('-')
    expect(fmtAccSigned(Number.POSITIVE_INFINITY)).toBe('-')
  })

  test('fmtPf：盈亏比 999 显示 ∞', () => {
    expect(fmtPf(2.5)).toBe('2.50')
    expect(fmtPf(999)).toBe('∞')
    expect(fmtPf(999.0)).toBe('∞')
    expect(fmtPf(null)).toBe('-')
    expect(fmtPf(Number.NaN)).toBe('-')
    expect(fmtPf(Number.POSITIVE_INFINITY)).toBe('-')
  })
})

describe('market', () => {
  test('detectMarket：沪市 6xx/9xx/5xx', () => {
    expect(detectMarket('600519')).toBe('SH')
    expect(detectMarket('688981')).toBe('SH')
    expect(detectMarket('900901')).toBe('SH')
    expect(detectMarket('510300')).toBe('SH')
  })

  test('detectMarket：北交所 43/83/87/92/4xx/8xx', () => {
    expect(detectMarket('430047')).toBe('BJ')
    expect(detectMarket('830799')).toBe('BJ')
    expect(detectMarket('920000')).toBe('BJ')
    expect(detectMarket('400001')).toBe('BJ')
    expect(detectMarket('833171')).toBe('BJ')
  })

  test('detectMarket：深市默认', () => {
    expect(detectMarket('000001')).toBe('SZ')
    expect(detectMarket('300750')).toBe('SZ')
    expect(detectMarket('002594')).toBe('SZ')
  })

  test('detectMarket：非法输入默认深市', () => {
    expect(detectMarket('abc')).toBe('SZ')
    expect(detectMarket('12345')).toBe('SZ')
  })

  test('toSymbol / marketLabel', () => {
    expect(toSymbol('600519')).toBe('SH:600519')
    expect(toSymbol(' 000001 ')).toBe('SZ:000001')
    expect(marketLabel('SH')).toBe('沪市')
    expect(marketLabel('BJ')).toBe('北交所')
    expect(marketLabel('SZ')).toBe('深市')
  })
})

describe('api formatError', () => {
  test('fetch TypeError 提示网络错误', () => {
    const e = new TypeError('fetch failed')
    expect(formatError(e)).toContain('网络错误')
  })

  test('普通 Error 返回 message', () => {
    expect(formatError(new Error('boom'))).toBe('boom')
  })

  test('非 Error 值转字符串', () => {
    expect(formatError('oops')).toBe('oops')
    expect(formatError(42)).toBe('42')
  })
})
