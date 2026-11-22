import { useCallback } from "react";
import { useApp } from "@/lib/app-context";

/** Indirection so tests can observe the redirect (jsdom cannot navigate). */
export const navigation = { assign: (url: string): void => window.location.assign(url) };

export const MICROSOFT_AUTH_START = "/api/v1/microsoft/auth/start";

/** Old `connectMicrosoft()`: confirm a switch when already connected, then start the OAuth redirect. */
export function useConnectMicrosoft(): () => Promise<void> {
  const { microsoft, setStatus, askDialog } = useApp();
  return useCallback(async () => {
    if (!microsoft || !microsoft.is_auth_configured) {
      setStatus("Add the Microsoft values and encryption key to .env, then restart the API.", true);
      return;
    }
    if (
      microsoft.is_connected &&
      !(await askDialog({
        title: "Switch Microsoft account?",
        message: `Switch from ${microsoft.connection?.display_name} to a different account.`,
        confirmLabel: "Switch",
      }))
    )
      return;
    navigation.assign(MICROSOFT_AUTH_START);
  }, [microsoft, setStatus, askDialog]);
}
