import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message: string =
      error.response?.data?.error || error.message || "Error de red";
    return Promise.reject(new Error(message));
  },
);
