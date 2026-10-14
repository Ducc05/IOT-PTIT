import { expect, test } from '@playwright/test'
import { createMockApi } from '../../src/api/mock'
import { fulfillDashboardLists } from './helpers/dashboardLists'

const origin = 'http://127.0.0.1:5174'

test('anonymous visitors see only sign in, then JWT login opens Dashboard and logout closes it', async ({ page }) => {
  const backend = createMockApi({ latency: 0, persist: false })
  const latest = await backend.sensorLatest()
  const trends = await backend.sensorTrends()
  const devices = await backend.devices()
  const account = { id: 1, username: 'operator', email: 'operator@example.com', full_name: 'Admin Example', student_id: null as string | null }
  let profileUpdates = 0
  const contentRequests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/v1/')) contentRequests.push(request.url()) })
  await page.route(`${origin}/api/auth/token/`, route => route.fulfill({ json: { access: 'login-access', refresh: 'login-refresh' } }))
  await page.route(`${origin}/api/auth/me/`, async route => {
    if (route.request().method() === 'PATCH') {
      const values = route.request().postDataJSON()
      expect(values).toEqual({ full_name: 'Nguyễn Văn A', student_id: 'B23DCCN193', email: 'updated@example.com' })
      Object.assign(account, values)
      profileUpdates++
    }
    await route.fulfill({ json: account })
  })
  await page.route(`${origin}/api/v1/**`, async route => {
    if (await fulfillDashboardLists(route, latest, trends)) return
    await route.fulfill({ status: 404, json: {} })
  })
  await page.route(`${origin}/api/v1/devices/`, route => route.fulfill({ json: { count: devices.length, next: null, previous: null, results: devices } }))

  await page.goto(`${origin}/dashboard`)
  await expect(page).toHaveURL(/\/login\?redirect=\/dashboard/)
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.locator('.app-shell')).toHaveCount(0)
  expect(contentRequests).toHaveLength(0)

  await page.getByLabel('Username').fill('operator')
  await page.getByLabel('Password').fill('secure-password')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(`${origin}/dashboard`)
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await expect(page.locator('.sidebar-bottom')).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  await page.getByRole('link', { name: 'Profile', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Chỉnh sửa email' })).toContainText('operator@example.com')
  await expect(page.getByRole('button', { name: 'Chỉnh sửa mã sinh viên' })).toContainText('Chưa cập nhật')
  await page.getByRole('button', { name: /Admin Example/ }).click()
  await page.getByLabel('Họ và tên').fill('Nguyễn Văn A')
  await page.getByLabel('Mã sinh viên').fill('B23DCCN193')
  await page.getByLabel('Email').fill('updated@example.com')
  await page.getByRole('button', { name: 'Lưu', exact: true }).click()
  await expect(page.getByRole('button', { name: /Nguyễn Văn A/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Chỉnh sửa mã sinh viên' })).toContainText('B23DCCN193')
  await expect(page.getByRole('button', { name: 'Chỉnh sửa email' })).toContainText('updated@example.com')
  expect(profileUpdates).toBe(1)
  await page.screenshot({ path: 'test-results/previews/profile-account-desktop.png' })
  await page.reload()
  await expect(page.getByRole('button', { name: /Nguyễn Văn A/ })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: /Nguyễn Văn A/ }).click()
  await expect(page.getByLabel('Họ và tên')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Lưu', exact: true })).toBeInViewport()
  await page.screenshot({ path: 'test-results/previews/profile-account-mobile-edit.png' })
  const mobileBounds = await page.evaluate(() => ({
    main: document.querySelector('.main-content')!.getBoundingClientRect().left,
    summary: document.querySelector('.profile-summary')!.getBoundingClientRect().left,
    resources: document.querySelector('.profile-resources')!.getBoundingClientRect().left,
    heading: document.querySelector('.profile-resources .section-heading')!.getBoundingClientRect().left,
    pageScrollLeft: document.querySelector('.profile-page')!.scrollLeft,
  }))
  expect(mobileBounds.main).toBeGreaterThanOrEqual(0)
  expect(mobileBounds.summary).toBeGreaterThanOrEqual(0)
  expect(mobileBounds.resources).toBeGreaterThanOrEqual(0)
  expect(mobileBounds.heading).toBeGreaterThanOrEqual(0)
  expect(mobileBounds.pageScrollLeft).toBe(0)
  await page.getByRole('button', { name: 'Hủy', exact: true }).click()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.getByRole('button', { name: 'Logout' }).click()
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.locator('.app-shell')).toHaveCount(0)
})

test('an expired stored JWT cannot open a content route', async ({ page }) => {
  let contentRequests = 0
  page.on('request', request => { if (request.url().includes('/api/v1/')) contentRequests++ })
  await page.addInitScript(() => sessionStorage.setItem('iot-auth-http://127.0.0.1:5174/api/v1', JSON.stringify({
    username: 'former_user', email: '', access: 'expired', refresh: 'expired',
  })))
  await page.route(`${origin}/api/auth/me/`, route => route.fulfill({ status: 401, json: { error: { code: 'AUTHENTICATION_REQUIRED' } } }))
  await page.route(`${origin}/api/auth/token/refresh/`, route => route.fulfill({ status: 401, json: { error: { code: 'AUTHENTICATION_REQUIRED' } } }))
  await page.goto(`${origin}/dashboard`)
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await expect(page.locator('.app-shell')).toHaveCount(0)
  expect(contentRequests).toBe(0)
})

test('registration validates confirmation and signs in with the issued JWT', async ({ page }) => {
  const backend = createMockApi({ latency: 0, persist: false })
  const latest = await backend.sensorLatest()
  const trends = await backend.sensorTrends()
  const devices = await backend.devices()
  let registrations = 0
  await page.route(`${origin}/api/auth/register/`, async route => {
    registrations++
    expect(route.request().postDataJSON()).toMatchObject({ username: 'new_operator', email: 'new@example.com', password_confirm: 'StrongPass-2026!' })
    await route.fulfill({ status: 201, json: { id: 2, username: 'new_operator', email: 'new@example.com', access: 'new-access', refresh: 'new-refresh' } })
  })
  await page.route(`${origin}/api/v1/**`, async route => {
    if (await fulfillDashboardLists(route, latest, trends)) return
    await route.fulfill({ status: 404, json: {} })
  })
  await page.route(`${origin}/api/v1/devices/`, route => route.fulfill({ json: { count: devices.length, next: null, previous: null, results: devices } }))

  await page.goto(`${origin}/register`)
  await expect(page.getByRole('heading', { name: 'Create your account' })).toBeVisible()
  await expect(page.locator('.sidebar')).toHaveCount(0)
  await page.getByLabel('Username').fill('new_operator')
  await page.getByLabel('Email').fill('new@example.com')
  await page.getByLabel('Password', { exact: true }).fill('StrongPass-2026!')
  await page.getByLabel('Confirm password').fill('different')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Passwords do not match.')
  expect(registrations).toBe(0)
  await page.getByLabel('Confirm password').fill('StrongPass-2026!')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page).toHaveURL(`${origin}/dashboard`)
  await expect(page.locator('.sidebar-bottom')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  expect(registrations).toBe(1)
})
