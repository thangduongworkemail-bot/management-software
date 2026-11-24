<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ tieuDe: String, mo: Boolean, rong: Boolean })
const emit = defineEmits(['dong'])
const hop = ref(null)

// Nút Quay lại của Android (app gốc) đóng hộp thoại trên cùng thay vì rời trang
function quayLai(e) {
  if (!props.mo || !hop.value) return
  const dangMo = document.querySelectorAll('[role=dialog]')
  if (dangMo[dangMo.length - 1] !== hop.value) return
  e.preventDefault()
  emit('dong')
}
onMounted(() => window.addEventListener('kv:quay-lai', quayLai))
onBeforeUnmount(() => window.removeEventListener('kv:quay-lai', quayLai))
</script>

<template>
  <Teleport to="body">
    <div v-if="mo" class="fixed inset-0 z-40 bg-black/40 flex items-end sm:items-center justify-center p-2 lop-phu-hop-thoai"
      @click.self="emit('dong')" @keydown.esc="emit('dong')">
      <div ref="hop" role="dialog" aria-modal="true" :aria-label="tieuDe"
        :class="rong ? 'max-w-3xl' : 'max-w-lg'" class="bg-white rounded-2xl w-full max-h-[92vh] overflow-y-auto overscroll-contain p-5 space-y-4">
        <div class="flex items-center justify-between gap-2">
          <h2 class="tieu-de">{{ tieuDe }}</h2>
          <button class="nut-vien nut-nho" @click="emit('dong')">Đóng</button>
        </div>
        <slot />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Hộp thoại trượt từ dưới lên trên điện thoại: không để thanh home của iPhone che nút cuối */
.lop-phu-hop-thoai { padding-bottom: max(0.5rem, var(--vung-duoi)); padding-top: max(0.5rem, var(--vung-tren)); }
</style>
