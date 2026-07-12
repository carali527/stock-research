// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import VirtualStockInfoList from './VirtualStockInfoList.vue'

const rows = [
  {
    id: '2330',
    stockId: '2330',
    stockName: '台積電',
    industry: '半導體業',
    type: 'EQUITY',
    date: '2026-07-10',
  },
  {
    id: '2317',
    stockId: '2317',
    stockName: '鴻海',
    industry: '其他電子業',
    type: 'EQUITY',
    date: '2026-07-10',
  },
]

describe('VirtualStockInfoList', () => {
  it('renders the stock info table header and visible rows', () => {
    const wrapper = mount(VirtualStockInfoList, {
      props: {
        rows,
        visibleRows: 2,
      },
    })

    expect(wrapper.text()).toContain('股票名稱/代號')
    expect(wrapper.text()).toContain('產業別')
    expect(wrapper.text()).toContain('台積電')
    expect(wrapper.text()).toContain('2330')
    expect(wrapper.text()).toContain('半導體業')
    expect(wrapper.text()).toContain('鴻海')
    expect(wrapper.text()).toContain('其他電子業')
  })

  it('emits the selected stock id when a stock row is clicked', async () => {
    const wrapper = mount(VirtualStockInfoList, {
      props: {
        rows,
        visibleRows: 2,
      },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('select')).toEqual([['2330']])
  })
})
