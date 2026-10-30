<script setup>
import { onMounted, ref, watch } from 'vue'
import { get, post } from '../api'
import { ngayGio, tien } from '../lib/format'
import { bao, trangThai } from '../store'
import HuyHieu from '../components/HuyHieu.vue'

const tongKet = ref(null)
const ds = ref({ xac_nhan_tay: [], giao_dich_can_xu_ly: [] })

async function tai() {
  ;[tongKet.value, ds.value] = await Promise.all([get('/chot-ngay'), get('/doi-soat')])
}
onMounted(tai)
watch(() => trangThai.suKien, tai)

async function lam(duongDan, body, thongBao) {
  try { await post(duongDan, body); bao(thongBao, 'thanh-cong'); tai() } catch (e) { bao(e.message, 'loi', 8) }
}

function ghep(gd) {
  const ma = prompt('Ghép giao dịch này vào mã đơn nào? (vd KV261027005)')
  if (!ma) return
  get(`/don-hang/ma/${ma.trim()}`).then(d => lam(`/doi-soat/giao-dich/${gd.id}/ghep`, { don_id: d.id }, `Đã ghép vào đơn #${d.ma}`))
    .catch(e => bao(e.message, 'loi'))
}
</script>

<template>
  <div v-if="tongKet" class="space-y-4">
    <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="the"><div class="text-xs font-bold text-slate-600">TIỀN MẶT TẠI QUẦY</div><div class="text-xl font-extrabold mt-1">{{ tien(tongKet.tien_mat) }}</div></div>
      <div class="the"><div class="text-xs font-bold text-slate-600">CK TỰ ĐỘNG (MÁY NHẬN TIỀN / WEBHOOK)</div><div class="text-xl font-extrabold mt-1">{{ tien(tongKet.chuyen_khoan_tu_dong) }}</div></div>
      <div class="the border-2 border-do"><div class="text-xs font-bold text-do">CK "XÁC NHẬN TAY"</div><div class="text-xl font-extrabold text-do mt-1">{{ tien(tongKet.chuyen_khoan_xac_nhan_tay) }} ({{ tongKet.so_khoan_xac_nhan_tay }} khoản)</div></div>
      <div class="the"><div class="text-xs font-bold text-slate-600">ĐƠN LỆCH TIỀN HÔM NAY</div><div class="text-xl font-extrabold mt-1">{{ tongKet.so_don_lech_tien }} đơn</div></div>
    </div>

    <div class="grid lg:grid-cols-12 gap-4">
      <section class="lg:col-span-7 the space-y-3">
        <div class="font-extrabold">ĐỐI SOÁT "XÁC NHẬN TAY" VỚI SAO KÊ NGÂN HÀNG</div>
        <p v-if="!ds.xac_nhan_tay.length" class="text-sm">Không còn khoản nào cần đối soát.</p>
        <div v-for="t in ds.xac_nhan_tay" :key="t.id" class="flex flex-wrap justify-between items-center gap-2 border-b border-slate-200 pb-3">
          <div class="text-sm">
            <div class="font-extrabold">Đơn #{{ t.ma_don }} • {{ tien(t.so_tien) }} <span class="huy-hieu-loi">XÁC NHẬN TAY</span></div>
            <div>{{ ngayGio(t.thoi_diem) }} • {{ t.nguoi_xac_nhan }} • Bằng chứng:
              <template v-for="b in t.bang_chung || []" :key="b.gia_tri">
                <strong v-if="b.kieu === 'BON_SO_CUOI'">mã GD *{{ b.gia_tri }}</strong>
                <a v-else :href="b.gia_tri" target="_blank" class="underline">ảnh biên lai</a>&nbsp;
              </template>
            </div>
          </div>
          <button class="nut-do nut-nho" @click="lam(`/doi-soat/thanh-toan/${t.id}/da-khop`, {}, 'Đã đánh dấu khớp sao kê')">Đã khớp sao kê</button>
        </div>
      </section>

      <section class="lg:col-span-5 the space-y-3">
        <div class="font-extrabold">TIỀN VỀ CẦN XỬ LÝ</div>
        <p v-if="!ds.giao_dich_can_xu_ly.length" class="text-sm">Không có giao dịch lệch hay chưa khớp.</p>
        <div v-for="g in ds.giao_dich_can_xu_ly" :key="g.id" class="bg-than-nhat rounded-lg p-3 text-sm space-y-2">
          <div class="flex justify-between gap-2"><strong>{{ tien(g.so_tien) }}</strong><HuyHieu :ma="g.trang_thai" /></div>
          <div>"{{ g.noi_dung }}" • {{ g.nguon }} • {{ ngayGio(g.nhan_luc) }}</div>
          <div v-if="g.ghi_chu" class="font-bold">{{ g.ghi_chu }}</div>
          <div class="flex flex-wrap gap-2">
            <template v-if="g.trang_thai === 'LECH_TIEN' && g.don_id">
              <router-link :to="`/don-hang`" class="nut-vien nut-nho">Tạo QR bù {{ tien(g.con_phai_thu) }}</router-link>
              <button class="nut-do nut-nho" @click="lam(`/don-hang/${g.don_id}/chap-nhan-giam`, { ghi_chu: 'Chấp nhận khi đối soát' }, `Đã chốt đơn #${g.ma_don}`)">Chấp nhận giảm</button>
            </template>
            <button v-if="g.trang_thai === 'CHUA_KHOP' && !g.don_id" class="nut-vien nut-nho" @click="ghep(g)">Ghép vào đơn…</button>
          </div>
        </div>
      </section>
    </div>

    <div class="the flex flex-wrap justify-between items-center gap-3">
      <div>
        <div class="font-extrabold">KHÓA SỔ NGÀY {{ new Date(tongKet.ngay).toLocaleDateString('vi-VN') }}</div>
        <div class="text-sm">Tổng thu {{ tien(tongKet.tong_thu) }} • {{ tongKet.so_don_chot }} đơn đã chốt
          <template v-if="tongKet.da_chot_so"> • Đã khóa lúc {{ ngayGio(tongKet.da_chot_so.thoi_diem) }} bởi {{ tongKet.da_chot_so.ten_nguoi_thuc_hien }}</template></div>
        <div v-if="tongKet.so_xac_nhan_tay_chua_doi_soat" class="text-sm font-bold text-do">Còn {{ tongKet.so_xac_nhan_tay_chua_doi_soat }} khoản xác nhận tay chưa đối soát.</div>
      </div>
      <button class="nut-do" :disabled="!!tongKet.da_chot_so" @click="lam('/chot-ngay', {}, 'Đã khóa sổ ngày — ghi vào nhật ký')">Khóa sổ chốt ngày hôm nay</button>
    </div>
  </div>
</template>
