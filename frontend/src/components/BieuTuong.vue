<script setup>
// Biểu tượng nét 24×24 cho thanh điều hướng trên điện thoại (vẽ bằng đường SVG, không cần thư viện ngoài)
defineProps({ ten: { type: String, required: true } })

const NET = {
  'tong-quan': 'M3 11.5 12 4l9 7.5M5.5 9.5V20h4.5v-5.5h4V20h4.5V9.5',
  'ban-hang': 'M3 4h2.2l2.2 11h10.4l2-7.5H6.4M9 20.5h.01M17 20.5h.01',
  'don-hang': 'M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6M9 16h3',
  kho: 'M3.5 7.5 12 3.5l8.5 4v9L12 20.5l-8.5-4v-9zM3.5 7.5 12 11.5l8.5-4M12 11.5v9',
  'hang-hoa': 'M3.5 12.5V4h8.5l8.5 8.5-8 8-9-8zM8 8.5h.01',
  'doi-soat': 'M8.5 12.5 11 15l4.5-5M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z',
  'hoa-don': 'M7 3h7l5 5v13H7V3zM14 3v5h5M10 13h6M10 17h6',
  'he-thong': 'M15.5 20v-1.5a4 4 0 0 0-4-4h-5a4 4 0 0 0-4 4V20M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21.5 20v-1.5a4 4 0 0 0-3-3.9M15.5 4.1a3.5 3.5 0 0 1 0 6.8',
  'su-co': 'M12 3.5 21.5 20h-19L12 3.5zM12 10v4.5M12 17h.01',
  them: 'M4 6.5h16M4 12h16M4 17.5h16',
  chuong: 'M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16zM10 20.5a2 2 0 0 0 4 0',
  'tai-xuong': 'M12 4v11M7.5 10.5 12 15l4.5-4.5M5 20h14',
  'chia-se-ios': 'M12 3v12M8 7l4-4 4 4M6 11H5v10h14V11h-1',
  'may-chu': 'M4 5h16v6H4V5zM4 13h16v6H4v-6zM8 8h.01M8 16h.01',
  thoat: 'M15 4h4v16h-4M10 16l4-4-4-4M14 12H4',
}
</script>

<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
    stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path :d="NET[ten] || NET.them" />
  </svg>
</template>
