// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import VirtualStockPriceList from './VirtualStockPriceList.vue'

const rows = [
  {
    key: '2330-2026-07-10',
    date: '2026-07-10T09:00:00+08:00',
    minute: '',
    stockId: '2330',
    open: 1000,
    high: 1020,
    low: 995,
    close: 1010,
    volume: 18000,
    amount: 18_180_000,
    turnover: 0,
    spread: 10,
  },
  {
    key: '2330-2026-07-10-09:30',
    date: '2026-07-10',
    minute: '09:30',
    stockId: '2330',
    open: 1010,
    high: 1015,
    low: 1005,
    close: 1012,
    volume: 2500,
    amount: 2_530_000,
    turnover: 0,
    spread: 2,
  },
]

describe('VirtualStockPriceList', () => {
  it('renders price table headers and daily price rows', () => {
    const wrapper = mount(VirtualStockPriceList, {
      props: {
        rows,
        height: 120,
        rowHeight: 40,
      },
    })

    expect(wrapper.text()).toContain('日期')
    expect(wrapper.text()).toContain('開盤價')
    expect(wrapper.text()).toContain('最高')
    expect(wrapper.text()).toContain('最低')
    expect(wrapper.text()).toContain('收盤價')
    expect(wrapper.text()).toContain('成交量(張)')
    expect(wrapper.text()).toContain('2026-07-10')
    expect(wrapper.text()).toContain('1000')
    expect(wrapper.text()).toContain('1020')
    expect(wrapper.text()).toContain('995')
    expect(wrapper.text()).toContain('1010')
    expect(wrapper.text()).toContain('18000')
  })

  it('renders minute rows with the minute next to the date', () => {
    const wrapper = mount(VirtualStockPriceList, {
      props: {
        rows,
        height: 120,
        rowHeight: 40,
      },
    })

    expect(wrapper.text()).toContain('2026-07-10 09:30')
    expect(wrapper.text()).toContain('2500')
  })
})
