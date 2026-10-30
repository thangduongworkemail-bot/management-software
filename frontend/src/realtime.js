import { bao, trangThai } from './store'

const THONG_DIEP = {
  YEU_CAU_DUYET: d => [`${d.nguoi_yeu_cau} xin bán đơn #${d.ma} dưới giá sàn`, 'canh-bao'],
  KET_QUA_DUYET: d => [d.dong_y ? `Chủ đã DUYỆT giá đơn #${d.ma}` : `Chủ TỪ CHỐI giá đơn #${d.ma}`, d.dong_y ? 'thanh-cong' : 'loi'],
  DON_DA_THANH_TOAN: d => [`Đơn #${d.ma} đã thu đủ tiền`, 'thanh-cong'],
  LECH_TIEN: d => [d.thong_bao, 'canh-bao'],
  GIAO_DICH_CHUA_KHOP: d => [d.thong_bao, 'canh-bao'],
  HDDT_LOI: d => [`Hóa đơn điện tử lỗi: ${d.ly_do}`, 'loi'],
  XUNG_DOT_TON: d => [`Đơn #${d.ma} vượt tồn khả dụng — cần xử lý`, 'canh-bao'],
  MAY_NHAN_TIEN_MAT_KET_NOI: d => [`Máy nhận tiền "${d.ten}" mất kết nối`, 'canh-bao'],
}

let ws = null
let hen = null

export function ketNoiRealtime() {
  if (!trangThai.token || (ws && ws.readyState <= 1)) return
  const giaoThuc = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${giaoThuc}://${location.host}/ws?token=${encodeURIComponent(trangThai.token)}`)
  const ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25_000)
  ws.onmessage = (e) => {
    const sk = JSON.parse(e.data)
    trangThai.suKienCuoi = sk
    trangThai.suKien++
    const tao = THONG_DIEP[sk.loai]
    if (tao) bao(...tao(sk.du_lieu), 8)
  }
  ws.onclose = () => {
    clearInterval(ping)
    ws = null
    if (trangThai.token) {
      clearTimeout(hen)
      hen = setTimeout(ketNoiRealtime, 3000)
    }
  }
}

export function ngatRealtime() {
  clearTimeout(hen)
  ws?.close()
  ws = null
}
