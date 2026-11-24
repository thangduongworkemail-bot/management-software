<script setup>
import { computed, ref, watch } from 'vue'
import { put, taiFileLen } from '../api'
import { thuNhoAnh } from '../lib/anh'
import { urlMayChu } from '../nen-tang'
import { bao, laChu } from '../store'

// Ảnh minh họa của một mặt hàng (biến thể hoặc bộ). Mặc định là ô nhỏ trong bảng danh mục;
// lon = khung lớn trong hộp chi tiết. Chỉ Chủ được thêm / đổi / gỡ ảnh.
const props = defineProps({ hang: { type: Object, required: true }, lon: Boolean })
const emit = defineEmits(['da-doi'])

const chonFile = ref(null)
const dangTai = ref(false)
const hong = ref(false)   // file ảnh không tải được (đã xóa, URL hết hạn…) thì coi như chưa có ảnh
watch(() => props.hang.anh_url, () => { hong.value = false })

const coAnh = computed(() => !!props.hang.anh_url && !hong.value)

async function datAnh(layUrl, thongBao) {
  dangTai.value = true
  try {
    const kieu = props.hang.kieu === 'BO' ? 'bo' : 'bien-the'
    const kq = await put(`/hang-hoa/${kieu}/${props.hang.id}/anh`, { anh_url: await layUrl() })
    emit('da-doi', kq.anh_url)
    bao(thongBao, 'thanh-cong')
  } catch (e) { bao(e.message, 'loi') } finally { dangTai.value = false }
}

function daChon(e) {
  const file = e.target.files[0]
  e.target.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) { bao('Hãy chọn một file ảnh (JPG, PNG, WebP)', 'loi'); return }
  datAnh(async () => taiFileLen(await thuNhoAnh(file), 'anh-mau'), `Đã cập nhật ảnh minh họa ${props.hang.ma}`)
}

function goAnh() {
  if (confirm(`Gỡ ảnh minh họa của ${props.hang.ten}?`)) datAnh(async () => null, `Đã gỡ ảnh minh họa ${props.hang.ma}`)
}
</script>

<template>
  <div v-if="!lon" class="w-14 h-14">
    <img v-if="coAnh" :src="urlMayChu(hang.anh_url)" :alt="hang.ten" width="56" height="56" loading="lazy" decoding="async"
      class="w-14 h-14 rounded-lg object-cover border border-slate-200 bg-white" @error="hong = true" />
    <button v-else-if="laChu()" type="button" :disabled="dangTai" :aria-label="`Thêm ảnh minh họa cho ${hang.ten}`"
      class="w-14 h-14 rounded-lg border-2 border-dashed border-slate-400 text-xs font-bold text-slate-600 leading-tight
             hover:border-do hover:text-do focus-visible:outline focus-visible:outline-2 focus-visible:outline-do disabled:opacity-50"
      @click.stop="chonFile.click()">{{ dangTai ? 'Đang tải…' : '+ Ảnh' }}</button>
    <div v-else class="w-14 h-14 rounded-lg bg-than-nhat" aria-hidden="true" />
    <input v-if="laChu()" ref="chonFile" type="file" accept="image/*" class="hidden" @click.stop @change="daChon" />
  </div>

  <div v-else-if="coAnh || laChu()" class="space-y-2">
    <img v-if="coAnh" :src="urlMayChu(hang.anh_url)" :alt="hang.ten" decoding="async"
      class="w-full max-h-80 object-contain rounded-lg bg-than-nhat" @error="hong = true" />
    <div v-else class="h-32 rounded-lg border-2 border-dashed border-slate-300 grid place-items-center text-sm text-slate-600">
      Chưa có ảnh minh họa</div>
    <div v-if="laChu()" class="flex flex-wrap gap-2">
      <button type="button" class="nut-vien nut-nho" :disabled="dangTai" @click="chonFile.click()">
        {{ dangTai ? 'Đang tải ảnh…' : coAnh ? 'Đổi ảnh' : '+ Thêm ảnh minh họa' }}</button>
      <button v-if="hang.anh_url" type="button" class="nut-vien nut-nho" :disabled="dangTai" @click="goAnh">Gỡ ảnh</button>
      <input ref="chonFile" type="file" accept="image/*" class="hidden" @change="daChon" />
    </div>
  </div>
</template>
