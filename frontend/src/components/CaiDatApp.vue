<script setup>
import { computed, ref } from 'vue'
import { anGoiY, caiDat, daAnGoiY, moHopThoaiCai } from '../cai-dat'
import { dangChayNhuApp, laAndroid, laIOS } from '../nen-tang'
import BieuTuong from './BieuTuong.vue'

// gon = dải gợi ý một dòng ở đầu trang (có nút ẩn 30 ngày); không gon = mục đầy đủ trong menu "Thêm"
const props = defineProps({ gon: Boolean })

const daAn = ref(daAnGoiY())
const laApp = dangChayNhuApp()
const hien = computed(() => !laApp && !caiDat.vuaCai && (!props.gon || (!daAn.value && (laIOS || laAndroid || caiDat.suKien))))
const cachCai = computed(() => (caiDat.suKien ? 'nut' : laIOS ? 'ios' : laAndroid ? 'android' : 'may-tinh'))

function an() {
  anGoiY()
  daAn.value = true
}
</script>

<template>
  <div v-if="laApp && !gon" class="the flex items-center gap-3 text-sm">
    <BieuTuong ten="tai-xuong" class="w-6 h-6 text-emerald-700 shrink-0" />
    <span class="font-bold">Đang dùng bản app đã cài trên máy này.</span>
  </div>

  <!-- Dải gợi ý gọn ở đầu trang -->
  <section v-else-if="hien && gon" class="khong-in bg-do-nhat border border-do/30 rounded-xl px-3 py-2 mb-3 flex items-center gap-2"
    aria-label="Cài ứng dụng">
    <BieuTuong ten="tai-xuong" class="w-5 h-5 text-do shrink-0" />
    <p class="flex-1 min-w-0 text-sm font-semibold leading-snug">
      <template v-if="cachCai === 'ios'">Cài app: bấm <BieuTuong ten="chia-se-ios" class="inline w-4 h-4 align-text-bottom" />
        <strong>Chia sẻ</strong> › <strong>Thêm vào MH chính</strong></template>
      <template v-else-if="cachCai === 'android'">Cài app: menu <strong>⋮</strong> › <strong>Cài đặt ứng dụng</strong></template>
      <template v-else>Cài app Khanh Vân lên điện thoại để mở nhanh, bán cả khi mất mạng</template>
    </p>
    <button v-if="cachCai === 'nut'" class="nut-do nut-nho shrink-0" @click="moHopThoaiCai">Cài</button>
    <button class="text-sm font-bold underline shrink-0 min-h-[40px] px-1" @click="an">Để sau</button>
  </section>

  <!-- Mục đầy đủ trong menu "Thêm" -->
  <section v-else-if="hien" class="khong-in bg-white border border-slate-300 rounded-xl p-3 sm:p-4 space-y-2" aria-label="Cài ứng dụng">
    <div class="flex items-start gap-3">
      <BieuTuong ten="tai-xuong" class="w-6 h-6 text-do shrink-0 mt-0.5" />
      <div class="flex-1 min-w-0">
        <div class="font-extrabold">Cài app Khanh Vân lên {{ laIOS || laAndroid ? 'điện thoại' : 'máy' }}</div>
        <p class="text-sm">Mở nhanh từ màn hình chính, chạy toàn màn hình, mất mạng vẫn tra giá và bán được.</p>
      </div>
    </div>

    <button v-if="cachCai === 'nut'" class="nut-do w-full" @click="moHopThoaiCai">Cài app ngay</button>

    <ol v-else-if="cachCai === 'ios'" class="text-sm space-y-1 list-decimal pl-5 font-semibold">
      <li>Mở trang này bằng <strong>Safari</strong> (không mở trong Zalo/Facebook).</li>
      <li>Bấm nút <strong>Chia sẻ</strong>
        <BieuTuong ten="chia-se-ios" class="inline w-5 h-5 align-text-bottom" /> ở thanh dưới cùng.</li>
      <li>Chọn <strong>“Thêm vào MH chính”</strong> rồi bấm <strong>Thêm</strong>.</li>
      <li>Mở app từ biểu tượng Khanh Vân mới xuất hiện (iOS 16.4 trở lên mới nhận được thông báo).</li>
    </ol>

    <ol v-else-if="cachCai === 'android'" class="text-sm space-y-1 list-decimal pl-5 font-semibold">
      <li>Mở trang này bằng <strong>Chrome</strong>.</li>
      <li>Bấm nút <strong>⋮</strong> góc trên bên phải.</li>
      <li>Chọn <strong>“Cài đặt ứng dụng”</strong> hoặc <strong>“Thêm vào màn hình chính”</strong>.</li>
    </ol>

    <p v-else class="text-sm font-semibold">Trên Chrome hoặc Edge máy tính: bấm biểu tượng cài đặt ở cuối thanh địa chỉ.</p>
  </section>
</template>
