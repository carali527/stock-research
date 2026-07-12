import { describe, expect, it } from 'vitest'
import { apiUrl } from './apiBase'

describe('apiUrl', () => {
  it('keeps absolute same-origin paths unchanged', () => {
    expect(apiUrl('/api/stocks')).toBe('/api/stocks')
  })

  it('adds a leading slash to relative paths', () => {
    expect(apiUrl('api/stocks')).toBe('/api/stocks')
  })
})
