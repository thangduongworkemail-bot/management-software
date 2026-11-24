import { createApp } from 'vue'
import App from './App.vue'
import './cai-dat' // bắt sự kiện "có thể cài app" ngay từ đầu
import { laAppGoc } from './nen-tang'
import { router } from './router'
import './style.css'

createApp(App).use(router).mount('#app')

// Service Worker: chạy offline và nhận thông báo đẩy cho bản web/PWA.
// App gốc (APK/iOS) đã chứa sẵn giao diện trong app nên không cần.
if (!laAppGoc && 'serviceWorker' in navigator) {
  import('virtual:pwa-register').then(({ registerSW }) => registerSW({ immediate: true }))
}
