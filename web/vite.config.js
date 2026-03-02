import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    server: {
        host: "0.0.0.0",
        port: 5173,
        proxy: {
            "/auth": "http://127.0.0.1:8000",
            "/nodes": "http://127.0.0.1:8000",
            "/edges": "http://127.0.0.1:8000",
            "/memories": "http://127.0.0.1:8000",
            "/query": "http://127.0.0.1:8000",
            "/graph": "http://127.0.0.1:8000",
            "/paths": "http://127.0.0.1:8000",
            "/ingest": "http://127.0.0.1:8000",
            "/health": "http://127.0.0.1:8000",
            "/metrics": "http://127.0.0.1:8000",
            "/ready": "http://127.0.0.1:8000",
        },
    },
});
