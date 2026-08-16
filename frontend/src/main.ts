import { createPinia } from 'pinia'
import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'
import { installSeo } from './utils/seo'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
installSeo(router)
app.mount('#app')
