import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

export interface ApiError extends Error {
  status?: number;
  isNetworkError?: boolean;
}

const NETWORK_ERROR_PATTERNS =
  /getaddrinfo failed|errno\s*11001|network error|econnrefused|enotfound|econnaborted/i;

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message: string =
      error.response?.data?.error || error.message || "Error de red";
    const offline = typeof navigator !== "undefined" && navigator.onLine === false;
    const noResponse = !error.response && !!error.request;
    const isNetworkError =
      offline || noResponse || NETWORK_ERROR_PATTERNS.test(message);
    const wrapped: ApiError = new Error(message);
    wrapped.status = error.response?.status;
    wrapped.isNetworkError = isNetworkError;
    return Promise.reject(wrapped);
  },
);
