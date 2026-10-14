import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { applyTheme, readStoredTheme } from './lib/theme'
import './styles/main.css'

// 挂载前先落主题，避免首帧闪烁（持久化值 → 系统偏好）
applyTheme(readStoredTheme())

createApp(App).use(router).mount('#app')
