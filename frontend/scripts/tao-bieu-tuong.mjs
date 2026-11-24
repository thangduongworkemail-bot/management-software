// Sinh mọi biểu tượng và màn chờ của app từ một file gốc: public/icon.svg
//   npm run icons
// - PWA: pwa-192/512, maskable-512 (Android cắt tròn/vuông tùy máy), apple-touch-icon 180 (iPhone), badge 96 (thanh thông báo)
// - Android (nếu đã có thư mục android/): ic_launcher, ic_launcher_round, ic_launcher_foreground, splash
// - iOS (nếu đã có thư mục ios/): AppIcon 1024 (không có kênh trong suốt, Apple bắt buộc), Splash 2732
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const GOC = join(dirname(fileURLToPath(import.meta.url)), '..')
const DO = '#C51A1B'
const svgGoc = readFileSync(join(GOC, 'public/icon.svg'), 'utf8')

// Tách các phần của logo: vòng tròn mờ, hai nét chữ "KV", dòng chữ
const vong = svgGoc.match(/<circle[^>]*\/>/)?.[0] ?? ''
const net = (svgGoc.match(/<path[^>]*\/>/g) ?? []).join('')
const chu = svgGoc.match(/<text[\s\S]*?<\/text>/)?.[0] ?? ''

/**
 * nen: 'bo-goc' (ô vuông bo góc như icon.svg) | 'vuong' (tràn viền) | 'tron' | 'trong'
 * tiLe: thu logo quanh tâm để nằm trong vùng an toàn của biểu tượng có mặt nạ.
 */
function taoSvg({ nen = 'vuong', tiLe = 1, coChu = true, coVong = true, mau = '#FFFFFF', w = 512, h = 512, lechX = 0 }) {
  const lop = {
    'bo-goc': `<rect width="512" height="512" rx="128" fill="${DO}"/>`,
    vuong: `<rect width="512" height="512" fill="${DO}"/>`,
    tron: `<circle cx="256" cy="256" r="256" fill="${DO}"/>`,
    trong: '',
  }[nen]
  const logo = ((coVong ? vong : '') + net + (coChu ? chu : '')).replaceAll('#FFFFFF', mau)
  const d = 256 * (1 - tiLe)
  // Khung không vuông (màn chờ): nền phủ cả khung, logo giữ tỉ lệ ở giữa
  const ngoai = Math.min(w, h)
  const dx = (w - ngoai) / 2
  const dy = (h - ngoai) / 2
  const svg = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">`
    + (nen === 'trong' ? '' : `<rect width="${w}" height="${h}" fill="${nen === 'vuong' ? DO : 'none'}"/>`)
    + `<g transform="translate(${dx} ${dy}) scale(${ngoai / 512})">${nen === 'vuong' ? '' : lop}`
    + `<g transform="translate(${d + lechX} ${d}) scale(${tiLe})">${logo}</g></g></svg>`)
  svg.rong = w
  return svg
}

async function ghi(duong, svg, rong, cao = rong, { khongTrongSuot = false } = {}) {
  // Vẽ SVG ở độ phân giải gấp đôi khung đích rồi thu nhỏ cho nét mịn
  let anh = sharp(svg, { density: Math.min(600, 72 * Math.max(1, (2 * rong) / svg.rong)) }).resize(rong, cao)
  if (khongTrongSuot) anh = anh.flatten({ background: DO }).removeAlpha()
  await anh.png({ compressionLevel: 9 }).toFile(join(GOC, duong))
  console.log(`  ${duong} (${rong}x${cao})`)
}

console.log('PWA:')
await ghi('public/pwa-192x192.png', taoSvg({ nen: 'bo-goc' }), 192)
await ghi('public/pwa-512x512.png', taoSvg({ nen: 'bo-goc' }), 512)
await ghi('public/maskable-512x512.png', taoSvg({ nen: 'vuong', tiLe: 0.78 }), 512)
await ghi('public/apple-touch-icon.png', taoSvg({ nen: 'vuong', tiLe: 0.86 }), 180, 180, { khongTrongSuot: true })
// Badge chỉ có nét chữ KV (Android tô một màu); nét chữ gốc lệch phải 44px so với tâm nên kéo về giữa
await ghi('public/badge-96x96.png', taoSvg({ nen: 'trong', tiLe: 1.1, coChu: false, coVong: false, lechX: -48 }), 96)

const res = 'android/app/src/main/res'
if (existsSync(join(GOC, res))) {
  console.log('Android:')
  const MAT_DO = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 }
  for (const [ten, k] of Object.entries(MAT_DO)) {
    await ghi(`${res}/mipmap-${ten}/ic_launcher.png`, taoSvg({ nen: 'bo-goc', tiLe: 0.92 }), 48 * k)
    await ghi(`${res}/mipmap-${ten}/ic_launcher_round.png`, taoSvg({ nen: 'tron', tiLe: 0.82 }), 48 * k)
    // Biểu tượng thích ứng (Android 8+): lớp trước trong suốt, logo nằm trong vùng an toàn 66/108
    await ghi(`${res}/mipmap-${ten}/ic_launcher_foreground.png`, taoSvg({ nen: 'trong', tiLe: 0.66 }), 108 * k)
  }
  const MAN_CHO = {
    drawable: [480, 320],
    'drawable-land-mdpi': [480, 320], 'drawable-land-hdpi': [800, 480], 'drawable-land-xhdpi': [1280, 720],
    'drawable-land-xxhdpi': [1600, 960], 'drawable-land-xxxhdpi': [1920, 1280],
    'drawable-port-mdpi': [320, 480], 'drawable-port-hdpi': [480, 800], 'drawable-port-xhdpi': [720, 1280],
    'drawable-port-xxhdpi': [960, 1600], 'drawable-port-xxxhdpi': [1280, 1920],
  }
  for (const [thuMuc, [w, h]] of Object.entries(MAN_CHO)) {
    await ghi(`${res}/${thuMuc}/splash.png`, taoSvg({ nen: 'vuong', tiLe: 0.42, w, h }), w, h)
  }
}

const tai = 'ios/App/App/Assets.xcassets'
if (existsSync(join(GOC, tai))) {
  console.log('iOS:')
  await ghi(`${tai}/AppIcon.appiconset/AppIcon-512@2x.png`, taoSvg({ nen: 'vuong', tiLe: 0.86 }), 1024, 1024, { khongTrongSuot: true })
  for (const f of ['splash-2732x2732.png', 'splash-2732x2732-1.png', 'splash-2732x2732-2.png']) {
    await ghi(`${tai}/Splash.imageset/${f}`, taoSvg({ nen: 'vuong', tiLe: 0.22 }), 2732, 2732, { khongTrongSuot: true })
  }
}
