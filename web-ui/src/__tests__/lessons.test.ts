import { describe, expect, test } from 'vitest'
import { LESSONS, lessonById } from '../content/lessons'

describe('缠论理论教学数据', () => {
  test('六篇概念齐备', () => {
    expect(LESSONS).toHaveLength(6)
    const ids = LESSONS.map((l) => l.id)
    expect(ids).toEqual(['fractal', 'bi', 'segment', 'zs', 'mmd', 'beichi'])
  })

  test('每篇含定义与规则', () => {
    for (const l of LESSONS) {
      expect(l.definition.length).toBeGreaterThan(0)
      expect(l.rules.length).toBeGreaterThan(0)
      expect(l.diagramNote.length).toBeGreaterThan(0)
    }
  })

  test('lessonById 命中与未命中', () => {
    expect(lessonById('zs')?.title).toContain('中枢')
    expect(lessonById('nope')).toBeUndefined()
  })
})
