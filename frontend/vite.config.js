import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: [],
      manifest: {
        name: 'NoteStream',
        short_name: 'NoteStream',
        description: 'Generate notes and quizzes from YouTube tutorials',
        theme_color: '#112e57',
        background_color: '#f4f7fb',
        display: 'standalone',
        start_url: '/',
        icons: []
      }
    })
  ]
})
