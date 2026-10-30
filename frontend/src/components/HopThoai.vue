<script setup>
defineProps({ tieuDe: String, mo: Boolean, rong: Boolean })
const emit = defineEmits(['dong'])
</script>

<template>
  <Teleport to="body">
    <div v-if="mo" class="fixed inset-0 z-40 bg-black/40 flex items-end sm:items-center justify-center p-2"
      @click.self="emit('dong')" @keydown.esc="emit('dong')">
      <div role="dialog" aria-modal="true" :aria-label="tieuDe"
        :class="rong ? 'max-w-3xl' : 'max-w-lg'" class="bg-white rounded-2xl w-full max-h-[92vh] overflow-y-auto p-5 space-y-4">
        <div class="flex items-center justify-between gap-2">
          <h2 class="tieu-de">{{ tieuDe }}</h2>
          <button class="nut-vien nut-nho" @click="emit('dong')">Đóng</button>
        </div>
        <slot />
      </div>
    </div>
  </Teleport>
</template>
