import axios, { AxiosError } from 'axios';
import { useUserStore } from '../store/useUserStore';
import { getMessageApi } from './messageClient';

// Extend Axios config types
declare module 'axios' {
  export interface AxiosRequestConfig {
    hideMessageModal?: boolean; // Hide error message
  }
}

const notifyError = (content: string): void => {
  const messageApi = getMessageApi();
  if (messageApi) {
    messageApi.error(content);
  } else {
    console.error(content);
  }
};

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 10 * 1000,
  headers: {
    'Content-Type': 'application/json;charset=UTF-8',
  },
});

let isRedirecting = false;

// Auth paths to exclude from redirect
const AUTH_PATHS = ['/login'];

const getValidFromPath = (): string => {
  const currentPath = location.pathname;
  if (AUTH_PATHS.some((authPath) => currentPath.startsWith(authPath))) {
    return '/dashboard';
  }
  return currentPath + location.search;
};

const redirectToLogin = (): void => {
  if (isRedirecting) return;
  isRedirecting = true;
  const from = getValidFromPath();
  setTimeout(() => {
    isRedirecting = false;
  }, 1000);
  window.location.href = `/login?from=${encodeURIComponent(from)}`;
};

// Request interceptor
service.interceptors.request.use(
  (config) => {
    const token = useUserStore.getState().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (timezone) {
      config.headers['X-Client-Timezone'] = timezone;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor
service.interceptors.response.use(
  (response) => {
    const { data, status, config } = response;
    const successCodes = [200, 201, 204];

    if (!successCodes.includes(status)) {
      return Promise.reject(response);
    } else {
      // For blob responses, return directly
      if (config.responseType === 'blob') {
        return Promise.resolve(response);
      }

      if (!data || response.status === 204) return Promise.resolve(response);
      const { code } = data;

      if (!successCodes.includes(code)) {
        return Promise.reject(response);
      }
      return Promise.resolve(response);
    }
  },
  async (error: AxiosError) => {
    const status = error?.response?.status;
    if (status === 204) {
      return Promise.resolve(error.response);
    }

    if (status === 401) {
      useUserStore.getState().clearAuth();
      window.localStorage.removeItem('userStore');
      if (!error?.config?.hideMessageModal) {
        notifyError('Session expired, please sign in again');
      }
      redirectToLogin();
      return Promise.reject(error);
    }

    return Promise.reject(error);
  }
);

export default service;
