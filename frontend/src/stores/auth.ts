import { defineStore } from 'pinia';

import {
  AUTH_TOKEN_STORAGE_KEY,
  fetchMe as fetchMeRequest,
  login as loginRequest,
  logout as logoutRequest,
  normalizeUser,
  type CurrentUser,
  type LoginPayload,
} from '@/api/auth';

interface AuthState {
  token: string;
  currentUser: CurrentUser | null;
  isFetchingMe: boolean;
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    token: localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || '',
    currentUser: null,
    isFetchingMe: false,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    isAdmin: (state) => state.currentUser?.role === 'admin',
  },

  actions: {
    async login(payload: LoginPayload) {
      const response = await loginRequest(payload);

      this.token = response.access_token;
      this.currentUser = normalizeUser(response.user);
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, response.access_token);
    },

    async logout() {
      try {
        if (this.token) {
          await logoutRequest();
        }
      } finally {
        this.clearSession();
      }
    },

    async fetchMe() {
      this.isFetchingMe = true;

      try {
        this.currentUser = await fetchMeRequest();
      } finally {
        this.isFetchingMe = false;
      }
    },

    clearSession() {
      this.token = '';
      this.currentUser = null;
      localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
    },
  },
});
