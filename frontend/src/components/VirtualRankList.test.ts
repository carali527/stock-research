// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import VirtualRankList, { type RankRow } from './VirtualRankList.vue'

const rows: RankRow[] = [
  {
    key: '2330',
    stockId: '2330',
    stockName: '台積電',
    subtitle: '半導體',
    valueText: '1,000',
  },
  {
    key: '2317',
    stockId: '2317',
    stockName: '鴻海',
    valueText: '200',
  },
]

describe('VirtualRankList', () => {
  it('renders rank rows and emits the selected stock id', async () => {
    const wrapper = mount(VirtualRankList, {
      props: {
        title: '成交量排行',
        rows,
      },
    })

    expect(wrapper.text()).toContain('成交量排行')
    expect(wrapper.text()).toContain('Top 2')
    expect(wrapper.text()).toContain('台積電')
    expect(wrapper.text()).toContain('半導體')

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('select')).toEqual([['2330']])
  })
})
