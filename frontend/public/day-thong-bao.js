/* Phần Service Worker nhận thông báo đẩy (Web Push) — được nạp vào sw.js do Workbox sinh ra (importScripts).
   Máy chủ gửi gói JSON đã mã hóa: { tieu_de, noi_dung, url, the }. */

self.addEventListener('push', (event) => {
  let goi = {}
  try { goi = event.data ? event.data.json() : {} } catch { goi = { noi_dung: event.data && event.data.text() } }
  const tieuDe = goi.tieu_de || 'Nội thất Khanh Vân'
  event.waitUntil(self.registration.showNotification(tieuDe, {
    body: goi.noi_dung || '',
    icon: '/pwa-192x192.png',
    badge: '/badge-96x96.png',
    lang: 'vi',
    tag: goi.the || undefined,        // cùng loại thì thông báo mới thay thông báo cũ, không chất đống
    renotify: Boolean(goi.the),
    data: { url: goi.url || '/' },
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const dich = new URL(event.notification.data?.url || '/', self.location.origin).href
  event.waitUntil((async () => {
    const cuaSo = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    // App đang mở thì chuyển tới đúng trang; chưa mở thì mở mới
    for (const c of cuaSo) {
      if (new URL(c.url).origin === self.location.origin && 'focus' in c) {
        await c.focus()
        if ('navigate' in c) await c.navigate(dich).catch(() => {})
        return
      }
    }
    await self.clients.openWindow(dich)
  })())
})

// Dịch vụ đẩy đổi khóa (hiếm): đăng ký lại sẽ được làm khi người dùng mở app lần sau (day.js > dongBoDangKy)
