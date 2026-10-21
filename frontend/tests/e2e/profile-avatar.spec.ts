import { expect, test } from '@playwright/test'
import { useApiSession } from './helpers/auth'

const origin = 'http://127.0.0.1:5174'
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ1sAAAAASUVORK5CYII=', 'base64')

test('clicking the avatar selects one image, uploads it, and preserves it after reload', async ({ page }) => {
  await useApiSession(page)
  const account = { id: 1, username: 'tester', email: '', full_name: 'Tester', student_id: null, avatar: null as string | null }
  let uploads = 0
  let rejectUpload = false
  await page.route(`${origin}/api/auth/me/`, async route => {
    if (route.request().method() === 'POST') {
      expect(route.request().headers()['content-type']).toContain('multipart/form-data; boundary=')
      expect(route.request().postDataBuffer()?.toString()).toContain('name="avatar"; filename="photo.png"')
      expect(route.request().postDataBuffer()?.toString()).toContain('name="full_name"\r\n\r\nTester')
      expect(route.request().postDataBuffer()?.toString()).toContain('name="student_id"\r\n\r\n\r\n')
      expect(route.request().postDataBuffer()?.toString()).toContain('name="email"\r\n\r\n\r\n')
      uploads++
      if (rejectUpload) return route.fulfill({ status: 400, json: { error: { code: 'VALIDATION_ERROR', message: 'Ảnh tải lên không hợp lệ.', details: {} } } })
      account.avatar = `${origin}/media/avatars/new.png`
    }
    return route.fulfill({ json: account })
  })
  await page.route(`${origin}/media/avatars/new.png`, route => route.fulfill({ contentType: 'image/png', body: png }))
  await page.goto(`${origin}/profile`)
  const changeAvatar = page.getByRole('button', { name: 'Đổi ảnh đại diện' })
  await expect(changeAvatar).toBeVisible()
  expect(await page.getByLabel('Chọn ảnh đại diện').evaluate(input => (input as HTMLInputElement).multiple)).toBe(false)
  const chooserPromise = page.waitForEvent('filechooser')
  await changeAvatar.click()
  const chooser = await chooserPromise
  expect(chooser.isMultiple()).toBe(false)
  await chooser.setFiles({ name: 'photo.png', mimeType: 'image/png', buffer: png })
  await expect(page.getByText('Đã đổi ảnh đại diện.', { exact: true })).toBeVisible()
  const avatar = changeAvatar.getByRole('img')
  await expect(avatar).toHaveAttribute('src', account.avatar!)
  await expect.poll(() => avatar.evaluate(img => (img as HTMLImageElement).naturalWidth)).toBe(1)
  expect(uploads).toBe(1)

  await page.reload()
  await expect(avatar).toHaveAttribute('src', account.avatar!)
  await page.getByLabel('Chọn ảnh đại diện').setInputFiles({ name: 'not-image.txt', mimeType: 'text/plain', buffer: Buffer.from('text') })
  await expect(page.getByRole('alert')).toHaveText('Vui lòng chọn ảnh JPG, PNG hoặc WebP.')
  expect(uploads).toBe(1)
  await page.getByLabel('Chọn ảnh đại diện').setInputFiles({ name: 'large.png', mimeType: 'image/png', buffer: Buffer.alloc(5 * 1024 * 1024 + 1) })
  await expect(page.getByRole('alert')).toHaveText('Ảnh đại diện không được vượt quá 5 MB.')
  expect(uploads).toBe(1)

  rejectUpload = true
  await page.getByLabel('Chọn ảnh đại diện').setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: png })
  await expect(page.getByRole('alert')).toHaveText('Ảnh tải lên không hợp lệ.')
  await expect(avatar).toHaveAttribute('src', account.avatar!)
  await expect(changeAvatar).toBeEnabled()
  expect(uploads).toBe(2)
})
