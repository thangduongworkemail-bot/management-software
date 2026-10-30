<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { get, post } from '../api'
import { ngay, ngayGio, tien } from '../lib/format'
import { bao, laChu, trangThai, xemGiaVon } from '../store'

const d = ref(null)
const loi = ref('')

async function tai() {
  try { d.value = await get('/tong-quan'); loi.value = '' } catch (e) { loi.value = e.message }
}
onMounted(tai)
watch(() => trangThai.suKien, tai)

const cotCaoNhat = computed(() => Math.max(1, ...(d.value?.doanh_thu_theo_ngay || []).map(x => x.doanh_thu)))

async function duyet(yc, dongY) {
  const lyDo = dongY ? null : prompt('Lý do từ chối (để thợ biết):') || 'Giá quá thấp'
  try {
    await post(`/yeu-cau-duyet/${yc.id}`, { dong_y: dongY, ly_do: lyDo })
    bao(dongY ? `Đã duyệt đơn #${yc.ma_don}` : `Đã từ chối đơn #${yc.ma_don}`, 'thanh-cong')
    tai()
  } catch (e) { bao(e.message, 'loi') }
}
</script>

<template>
  <p v-if="loi" class="the text-do font-bold">{{ loi }}</p>
  <div v-else-if="d" class="grid lg:grid-cols-12 gap-4">
    <section class="lg:col-span-8 space-y-4">
      <div class="grid sm:grid-cols-3 gap-4">
        <div class="the">
          <div class="text-xs font-bold text-slate-600">THU HÔM NAY ({{ d.so_don_thu_tien_hom_nay }} ĐƠN)</div>
          <div class="text-2xl font-extrabold text-do mt-1">{{ tien(d.doanh_thu_hom_nay) }}</div>
        </div>
        <div class="the">
          <div class="text-xs font-bold text-slate-600">ĐANG GIỮ CHỖ / CHỜ TIỀN</div>
          <div class="text-2xl font-extrabold mt-1">{{ d.don_cho_thanh_toan.length }} đơn</div>
          <div v-if="d.don_cho_thanh_toan[0]" class="text-xs font-semibold mt-1">
            #{{ d.don_cho_thanh_toan[0].ma }} ({{ tien(d.don_cho_thanh_toan[0].tong_tien) }})
          </div>
        </div>
        <div class="the">
          <div class="text-xs font-bold text-slate-600">TRẢ HÀNG HÔM NAY</div>
          <div class="text-2xl font-extrabold mt-1">{{ d.tra_hang_hom_nay }} đơn</div>
        </div>
      </div>

      <div class="the space-y-3">
        <div class="flex flex-wrap justify-between gap-2">
          <div class="font-extrabold">TIỀN THU THÁNG NÀY: <span class="text-do">{{ tien(d.doanh_thu_thang) }}</span></div>
          <div v-if="xemGiaVon()" class="font-bold text-sm">Lãi gộp đơn đã chốt: {{ tien(d.loi_nhuan_gop_thang) }}</div>
        </div>
        <div class="flex items-end gap-1 h-40 border-b border-slate-300" role="img" aria-label="Biểu đồ tiền thu 14 ngày gần nhất">
          <div v-for="(n, i) in d.doanh_thu_theo_ngay" :key="n.ngay" class="flex-1 flex flex-col items-center justify-end h-full gap-1">
            <div :class="i === d.doanh_thu_theo_ngay.length - 1 ? 'bg-do' : 'bg-than'" class="w-full max-w-[28px] rounded-t"
              :style="{ height: `${(n.doanh_thu / cotCaoNhat) * 100}%`, minHeight: n.doanh_thu ? '4px' : '0' }"
              :title="`${n.ngay}: ${tien(n.doanh_thu)}`"></div>
          </div>
        </div>
        <div class="flex justify-between text-xs font-bold text-slate-600">
          <span>{{ ngay(d.doanh_thu_theo_ngay[0]?.ngay) }}</span><span class="text-do">Hôm nay</span>
        </div>
      </div>

      <div class="the space-y-3">
        <div class="font-extrabold">TỒN KHO THEO XƯỞNG & CẢNH BÁO SẮP HẾT</div>
        <div class="grid sm:grid-cols-3 gap-3">
          <div v-for="x in d.ton_theo_xuong" :key="x.id" class="bg-than-nhat rounded-lg p-3">
            <div class="font-bold">{{ x.ten }}</div>
            <div class="text-lg font-extrabold">{{ x.ton_hien_co }} sản phẩm</div>
            <div v-if="x.so_mau_sap_het" class="text-xs font-bold text-do">! {{ x.so_mau_sap_het }} mẫu chạm mức tối thiểu</div>
            <div v-else class="text-xs font-semibold">Đủ hàng bán</div>
          </div>
        </div>
        <ul v-if="d.sap_het.length" class="text-sm space-y-1">
          <li v-for="h in d.sap_het" :key="h.id"><strong>{{ h.ten_hien_thi }}</strong> — còn bán được {{ h.ton_kha_dung }} (tối thiểu {{ h.ton_toi_thieu }})</li>
        </ul>
      </div>
    </section>

    <aside class="lg:col-span-4 space-y-4">
      <div v-if="laChu()" class="the border-2 border-do space-y-3">
        <div class="font-extrabold text-do">CẦN CHỦ DUYỆT ({{ d.yeu_cau_cho_duyet.length }})</div>
        <p v-if="!d.yeu_cau_cho_duyet.length" class="text-sm">Không có yêu cầu nào.</p>
        <div v-for="yc in d.yeu_cau_cho_duyet" :key="yc.id" class="bg-than-nhat rounded-lg p-3 space-y-2 text-sm">
          <div class="font-extrabold">{{ yc.nguoi_yeu_cau }} xin bán đơn #{{ yc.ma_don }} dưới giá sàn</div>
          <div v-for="(l, i) in yc.noi_dung.dong" :key="i">
            {{ l.mo_ta }} • Giá sàn {{ tien(l.gia_san) }} → Xin bán <strong>{{ tien(l.xin_ban) }}</strong> ({{ tien(l.chenh_lech) }})
          </div>
          <div class="flex gap-2">
            <button class="nut-do nut-nho" @click="duyet(yc, true)">Chủ duyệt</button>
            <button class="nut-vien nut-nho" @click="duyet(yc, false)">Từ chối</button>
          </div>
        </div>
        <router-link v-if="d.can_doi_soat || d.giao_dich_chua_khop" to="/doi-soat" class="block text-sm font-bold underline">
          {{ d.can_doi_soat }} khoản xác nhận tay chờ đối soát • {{ d.giao_dich_chua_khop }} giao dịch cần xử lý →
        </router-link>
      </div>

      <div class="the space-y-2 text-sm">
        <div class="font-extrabold">HÓA ĐƠN ĐIỆN TỬ</div>
        <div>{{ d.hddt_cho_xuat }} đơn chờ xuất • <span :class="d.hddt_loi ? 'text-do font-bold' : ''">{{ d.hddt_loi }} lỗi</span></div>
        <div class="text-xs">Chạy độc lập, không chặn giao hàng tại quầy.</div>
      </div>

      <div v-if="d.nhat_ky_gan_day" class="the space-y-2">
        <div class="font-extrabold text-sm">HOẠT ĐỘNG GẦN ĐÂY</div>
        <ul class="text-xs space-y-2 border-l-2 border-do pl-3">
          <li v-for="n in d.nhat_ky_gan_day" :key="n.id">
            <strong>{{ n.ten_nguoi_thuc_hien }}</strong> {{ n.hanh_dong }} {{ n.thuc_the_id ? `#${n.thuc_the_id}` : '' }}
            • {{ ngayGio(n.thoi_diem) }}
          </li>
        </ul>
      </div>
    </aside>
  </div>
</template>
