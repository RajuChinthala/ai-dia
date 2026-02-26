import axios from "axios";

// Base URL can be overridden via VITE_API_BASE; falls back to /api for Vite proxy.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
});

export default api;
