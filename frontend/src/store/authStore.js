import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// Persist auth and settings only; durable chat history is backend-gated by plan.
export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      user: null,
      currentConversationId: crypto.randomUUID(),
      chatTurns: [],
      latestResponse: null,
      settings: {
        topk: 3,
        maxHistoryTurns: 3,
      },
      setAuth: ({ token, user }) =>
        set({
          token,
          user,
          chatTurns: [],
          latestResponse: null,
          currentConversationId: crypto.randomUUID(),
        }),
      // Logout intentionally resets conversation state so private answers do not survive account changes.
      logout: () =>
        set({
          token: null,
          user: null,
          chatTurns: [],
          latestResponse: null,
          currentConversationId: crypto.randomUUID(),
        }),
      // Refresh safe account fields from /api/me so plan badges do not stay stale after seeding/upgrades.
      setUser: (user) => set({ user }),
      setChatTurns: (chatTurns) => set({ chatTurns }),
      setLatestResponse: (latestResponse) => set({ latestResponse }),
      // Start a new local conversation without changing the signed-in account.
      clearConversation: () =>
        set({
          chatTurns: [],
          latestResponse: null,
          currentConversationId: crypto.randomUUID(),
        }),
      // Merge settings updates so individual controls do not need to know the full settings object.
      updateSettings: (settings) =>
        set((state) => ({
          settings: {
            ...state.settings,
            ...settings,
          },
        })),
    }),
    {
      name: 'sonicmind-auth',
      version: 2,
      migrate: (persistedState) => ({
        token: persistedState?.token || null,
        user: persistedState?.user || null,
        currentConversationId: persistedState?.currentConversationId || crypto.randomUUID(),
        settings: persistedState?.settings || { topk: 3, maxHistoryTurns: 3 },
      }),
      // Persist only serializable UI state; mutation objects and transient loading flags stay in React Query.
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        currentConversationId: state.currentConversationId,
        settings: state.settings,
      }),
    },
  ),
);
