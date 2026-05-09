import axios from 'axios';
import { useAuthStore } from '../store/authStore.js';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

// Keep one configured client so auth headers and API base URL stay consistent.
export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach the latest bearer token at request time because Zustand may update after client creation.
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Normalize FastAPI validation errors and generic network failures into one display string.
export function getApiError(error, fallback = 'Something went wrong. Please try again.') {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || item.message || String(item)).join(' ');
  }
  if (detail && typeof detail === 'object') {
    return detail.message || fallback;
  }
  return detail || error?.message || fallback;
}

export function getUsageLimitDetail(error) {
  // Limit responses include structured usage data so the modal can show accurate backend counters.
  const detail = error?.response?.data?.detail;
  return detail?.code === 'usage_limit_reached' ? detail : null;
}

// Auth helpers return only the response payload so pages do not depend on axios internals.
export async function login(payload) {
  const response = await apiClient.post('/api/login', payload);
  return response.data;
}

export async function register(payload) {
  const response = await apiClient.post('/api/register', payload);
  return response.data;
}

export async function sendChatMessage(payload) {
  const response = await apiClient.post('/api/chat', payload);
  return response.data;
}

export async function fetchPricing() {
  const response = await apiClient.get('/api/pricing');
  return response.data;
}

export async function fetchAccountStatus() {
  const response = await apiClient.get('/api/me');
  return response.data;
}

export async function createCheckoutSession(payload) {
  const response = await apiClient.post('/api/billing/checkout-session', payload);
  return response.data;
}

export async function createPortalSession() {
  const response = await apiClient.post('/api/billing/portal-session');
  return response.data;
}

export async function changeSubscriptionPlan(payload) {
  const response = await apiClient.post('/api/billing/subscription-plan', payload);
  return response.data;
}

export async function fetchHistory() {
  const response = await apiClient.get('/api/history');
  return response.data;
}

export async function deleteHistory() {
  const response = await apiClient.delete('/api/history');
  return response.data;
}

export async function fetchFavorites() {
  const response = await apiClient.get('/api/favorites');
  return response.data;
}

export async function saveFavorite(payload) {
  const response = await apiClient.post('/api/favorites', payload);
  return response.data;
}

export async function deleteFavorite(favoriteId) {
  const response = await apiClient.delete(`/api/favorites/${favoriteId}`);
  return response.data;
}
