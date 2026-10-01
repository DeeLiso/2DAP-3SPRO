export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  corePlugins: {
    preflight: false
  },
  theme: {
    extend: {
      colors: {
        ink: '#10221b',
        canvas: '#f5f7f4',
        panel: '#ffffff',
        line: '#dde5df',
        teal: '#0f766e',
        owner: '#d97706',
        player: '#059669',
        danger: '#dc2626'
      },
      fontFamily: {
        sans: ['Noto Sans Myanmar', 'IBM Plex Sans Thai', 'Segoe UI', 'sans-serif'],
        display: ['IBM Plex Sans Thai', 'Noto Sans Myanmar', 'Segoe UI', 'sans-serif']
      },
      boxShadow: {
        quiet: '0 14px 40px rgba(16, 34, 27, 0.08)'
      }
    }
  },
  plugins: []
}
