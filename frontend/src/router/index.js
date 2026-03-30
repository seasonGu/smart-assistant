import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Chat from '../views/Chat.vue'

const routes = [
  { path: '/', component: Home },
  { path: '/chat/:id', component: Chat },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
