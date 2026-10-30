<script setup>
import { TRANG_THAI_DON } from '../lib/format'

defineProps({ ma: String })
</script>

<template>
  <span v-if="ma" :class="`huy-hieu-${TRANG_THAI_DON[ma]?.[1] || 'xam'}`">{{ TRANG_THAI_DON[ma]?.[0] || ma }}</span>
</template>
