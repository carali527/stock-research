import { expect, test, type Page } from '@playwright/test'

const stockListResponse = {
  date: '2026-07-10',
  type: 'EQUITY',
  exchange: 'TWSE',
  data: [
    { symbol: '2330', name: '台積電', industry: '24' },
    { symbol: '2317', name: '鴻海', industry: '25' },
    { symbol: '2454', name: '聯發科', industry: '24' },
  ],
}

const historicalCandlesResponse = {
  symbol: '2330',
  type: 'EQUITY',
  exchange: 'TWSE',
  timeframe: 'D',
  data: [
    {
      date: '2026-07-08T09:00:00+08:00',
      open: 980,
      high: 1005,
      low: 975,
      close: 1000,
      volume: 12000,
    },
    {
      date: '2026-07-09T09:00:00+08:00',
      open: 1000,
      high: 1020,
      low: 995,
      close: 1010,
      volume: 18000,
    },
  ],
}

async function mockBackend(page: Page) {
  await page.route('**/api/yahoo/listed-hot-rank', async (route) => {
    await route.fulfill({
      json: {
        sourceUrl: 'https://example.test/hot',
        items: [
          { symbol: '2330', name: '台積電' },
          { symbol: '2317', name: '鴻海' },
        ],
      },
    })
  })

  await page.route('**/api/yahoo/listed-change-up-rank', async (route) => {
    await route.fulfill({
      json: {
        sourceUrl: 'https://example.test/change-up',
        items: [{ symbol: '2454', name: '聯發科' }],
      },
    })
  })

  await page.route('**/fugle/marketdata/v1.0/stock/intraday/tickers**', async (route) => {
    await route.fulfill({ json: stockListResponse })
  })

  await page.route('**/fugle/marketdata/v1.0/stock/intraday/ticker/**', async (route) => {
    await route.fulfill({
      json: {
        date: '2026-07-10',
        type: 'EQUITY',
        exchange: 'TWSE',
        symbol: '2330',
        name: '台積電',
        industry: '24',
      },
    })
  })

  await page.route('**/fugle/marketdata/v1.0/stock/historical/candles/**', async (route) => {
    await route.fulfill({ json: historicalCandlesResponse })
  })
}

test.beforeEach(async ({ page }) => {
  await mockBackend(page)
})

test('shows home rankings from mocked API data', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: '上市成交量排行' })).toBeVisible()
  await expect(page.getByRole('link', { name: '台積電（2330）' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '上市漲幅排行' })).toBeVisible()
  await expect(page.getByRole('link', { name: '聯發科（2454）' })).toBeVisible()
})

test('searches the stock list and opens the stock price page', async ({ page }) => {
  await page.goto('/stock/demo')

  await expect(page.getByRole('heading', { name: '股票總覽' })).toBeVisible()
  await page.getByPlaceholder('代號 / 名稱 / 產業別').fill('台積電')

  await expect(page.getByRole('button', { name: /台積電\s+2330/ })).toBeVisible()
  await expect(page.getByText('清單筆數：1')).toBeVisible()

  await page.getByRole('button', { name: /台積電\s+2330/ }).click()
  await expect(page).toHaveURL(/\/stock\/2330\/price$/)
  await expect(page.getByRole('heading', { name: '股價日成交資訊' })).toBeVisible()
  await expect(page.getByText('股票代碼: 2330')).toBeVisible()
})

test('adds a stock to favorites and shows it in the favorites page', async ({ page }) => {
  await page.goto('/stock/2330/price')

  await page.getByRole('button', { name: '加入自選' }).click()
  await page.getByRole('link', { name: '自選清單' }).click()

  await expect(page.getByText('已收藏：1 檔')).toBeVisible()
  await expect(page.getByRole('link', { name: '台積電（2330）' })).toBeVisible()
})
