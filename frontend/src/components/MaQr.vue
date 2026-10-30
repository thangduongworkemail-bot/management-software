<script setup>
import QRCode from 'qrcode'
import { ref, watchEffect } from 'vue'

const props = defineProps({ noiDung: String, kichThuoc: { type: Number, default: 220 } })
const anh = ref('')

watchEffect(async () => {
  anh.value = props.noiDung
    ? await QRCode.toDataURL(props.noiDung, { width: props.kichThuoc, margin: 1, errorCorrectionLevel: 'M' })
    : ''
})
</script>

<template>
  <img v-if="anh" :src="anh" :width="kichThuoc" :height="kichThuoc" alt="Mã VietQR chuyển khoản" class="rounded-lg border border-slate-300" />
</template>
