/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0f172a',
        navy: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#1d4ed8',
          700: '#1e3a8a',
          800: '#172554',
          900: '#0f172a',
        },
        steel: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        },
        sand: '#f8f4ea',
      },
      boxShadow: {
        panel: '0 18px 40px rgba(15, 23, 42, 0.10)',
        soft: '0 10px 24px rgba(15, 23, 42, 0.08)',
      },
      fontFamily: {
        sans: ['"Noto Sans KR"', '"Apple SD Gothic Neo"', 'sans-serif'],
        serif: ['"Noto Serif KR"', '"Nanum Myeongjo"', 'serif'],
      },
      backgroundImage: {
        'grid-soft':
          'radial-gradient(circle at 1px 1px, rgba(148, 163, 184, 0.16) 1px, transparent 0)',
      },
    },
  },
  plugins: [],
};
