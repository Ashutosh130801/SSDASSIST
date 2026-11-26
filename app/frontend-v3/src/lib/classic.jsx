import { createContext, useContext } from 'react';

/** The embedded classic runtime: { api: window.__riqClassic | null, ready: bool }.
 *  api.openCase(id) opens the FULL classic case drawer (log call / visit / payment, PTP, history…),
 *  api.openTour(), api.printLiner(), api.nav (live, Services-filtered menu). */
export const ClassicCtx = createContext({ api: null, ready: false });
export const useClassic = () => useContext(ClassicCtx);
