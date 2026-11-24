<script setup>
import { ref } from 'vue'
import { datMayChu, kiemTraMayChu, mayChu } from '../nen-tang'

// Chỉ dùng trong app Android/iOS: giao diện nằm trong app, dữ liệu ở máy chủ của cửa hàng.
const emit = defineEmits(['xong'])
const diaChi = ref(mayChu.goc)
const loi = ref('')
const dangThu = ref(false)

async function luu() {
  loi.value = ''
  dangThu.value = true
  try {
    datMayChu(await kiemTraMayChu(diaChi.value))
    emit('xong')
  } catch (e) {
    loi.value = e.message
  } finally {
    dangThu.value = false
  }
}
</script>

<template>
  <form class="space-y-3" @submit.prevent="luu">
    <div>
      <label class="nhan" for="may-chu">Địa chỉ máy chủ của cửa hàng</label>
      <input id="may-chu" v-model="diaChi" class="o-nhap" inputmode="url" autocapitalize="off" autocorrect="off"
        spellcheck="false" autocomplete="url" placeholder="vd: khanhvan.onrender.com" required />
      <p class="text-xs text-slate-600 mt-1">
        Là địa chỉ đang mở trên máy tính quầy, ví dụ <strong>https://ten-cua-hang.onrender.com</strong>,
        hoặc <strong>192.168.1.10:8000</strong> khi điện thoại dùng chung wifi với máy quầy.
      </p>
    </div>
    <p v-if="loi" class="text-do font-bold" role="alert">{{ loi }}</p>
    <button class="nut-do w-full" :disabled="dangThu">{{ dangThu ? 'Đang kiểm tra kết nối…' : 'Kết nối' }}</button>
  </form>
</template>
