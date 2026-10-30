/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        do: { DEFAULT: '#C51A1B', dam: '#9E1415', nhat: '#FDECEC' },
        than: { DEFAULT: '#1E293B', nhat: '#F1F5F9' },
      },
      fontFamily: { sans: ['"Be Vietnam Pro"', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [],
}
