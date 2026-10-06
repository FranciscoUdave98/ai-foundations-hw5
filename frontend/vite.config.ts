import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard runs at http://localhost:5173 and calls the FastAPI backend at
// http://localhost:8000 directly (the backend allows this origin via CORS).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true, // the backend's CORS allow-list expects exactly this origin
  },
})
