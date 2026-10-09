"use client";

import { useEffect, useState } from "react";
import type { Session } from "./api";

const key = "takeone.localSession";

export function useSession() {
  const [session, setSession] = useState<Session | null | undefined>();
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(key);
      setSession(stored ? JSON.parse(stored) as Session : null);
    } catch { setSession(null); }
  }, []);
  function save(value: Session) {
    window.localStorage.setItem(key, JSON.stringify(value));
    setSession(value);
  }
  function clear() {
    window.localStorage.removeItem(key);
    setSession(null);
  }
  return { session, save, clear };
}
