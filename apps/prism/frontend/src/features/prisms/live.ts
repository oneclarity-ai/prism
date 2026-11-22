import { useCallback, useRef, useState } from "react";

/**
 * State with a synchronous mirror: async workflows read `ref.current` (always the latest value, like the
 * old module-level `state` object) while rendering reads the returned snapshot.
 */
export function useLiveState<S extends object>(initial: S) {
  const ref = useRef<S>(initial);
  const [snapshot, setSnapshot] = useState<S>(initial);
  const patch = useCallback((change: Partial<S>) => {
    ref.current = { ...ref.current, ...change };
    setSnapshot(ref.current);
  }, []);
  return [snapshot, patch, ref] as const;
}
