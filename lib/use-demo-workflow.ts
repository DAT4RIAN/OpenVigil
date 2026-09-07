"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  canonicalDemoWorkflow,
  transitionDemoWorkflow,
  type DemoWorkflowAction,
  type DemoWorkflowState,
} from "./demo-workflow";

interface DemoWorkflowStore extends DemoWorkflowState {
  dispatch: (action: DemoWorkflowAction) => void;
}

export const useDemoWorkflow = create<DemoWorkflowStore>()(
  persist(
    (set) => ({
      ...canonicalDemoWorkflow,
      dispatch: (action) => set((state) => transitionDemoWorkflow(state, action)),
    }),
    {
      name: "windops-wt023-demo-v1",
      storage: createJSONStorage(() => window.localStorage),
      skipHydration: true,
      partialize: ({ dispatch, ...state }) => {
        void dispatch;
        return state;
      },
    },
  ),
);

export const hydrateDemoWorkflow = (): void => {
  void useDemoWorkflow.persist.rehydrate();
};
