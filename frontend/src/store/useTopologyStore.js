// src/store/useTopologyStore.js
import { create } from "zustand";

export const useTopologyStore = create(set => ({
  data: null,        // { nodes, links }
  company: null,
  setTopology: (company, graph) => set({ company, data: graph }),
  clearTopology: () => set({ company: null, data: null })
}));
