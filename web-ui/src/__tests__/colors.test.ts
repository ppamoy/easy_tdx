// 涨跌配色（colors.ts）单测：默认红涨绿跌、切换绿涨红跌、持久化。
import { beforeEach, describe, expect, test } from 'vitest'
import { colorScheme, downColor, setColorScheme, upColor } from '../colors'

describe('涨跌配色 colors.ts', () => {
  beforeEach(() => {
    // 每个用例前重置为默认红涨绿跌，避免互相影响
    setColorScheme('red-up')
  })

  test('默认红涨绿跌：up=红 down=绿', () => {
    expect(colorScheme.value).toBe('red-up')
    expect(upColor.value).toBe('#ef4146')
    expect(downColor.value).toBe('#18a058')
  })

  test('切换绿涨红跌：up=绿 down=红', () => {
    setColorScheme('green-up')
    expect(colorScheme.value).toBe('green-up')
    expect(upColor.value).toBe('#18a058')
    expect(downColor.value).toBe('#ef4146')
  })

  test('upColor 与 downColor 始终相反', () => {
    setColorScheme('red-up')
    expect(upColor.value).not.toBe(downColor.value)
    setColorScheme('green-up')
    expect(upColor.value).not.toBe(downColor.value)
  })

  test('切换后持久化到 localStorage', () => {
    setColorScheme('green-up')
    expect(localStorage.getItem('easy-tdx.colorScheme')).toBe('green-up')
    setColorScheme('red-up')
    expect(localStorage.getItem('easy-tdx.colorScheme')).toBe('red-up')
  })
})
