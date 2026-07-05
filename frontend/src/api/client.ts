import { parseApiError } from "../lib/apiError";

const raw = import.meta.env.VITE_API_URL?.trim() || "/api";
/** Base URL da API; `/api` usa o proxy do Vite (recomendado em dev na rede). */
export const API_URL = raw.replace(/\/$/, "") || "/api";

export type ApiFetchOptions = RequestInit & {
  skipAuthRedirect?: boolean;
};

export async function apiFetch<T>(
  path: string,
  init?: ApiFetchOptions,
): Promise<T> {
  const { skipAuthRedirect, ...rest } = init ?? {};
  const url = `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
  let res: Response;
  try {
    res = await fetch(url, {
      credentials: "include",
      ...rest,
      headers: {
        "Content-Type": "application/json",
        ...rest.headers,
      },
    });
  } catch {
    throw new Error(
      "Não foi possível contactar a API (proxy/porta 8765). Confirme que o uvicorn está ativo.",
    );
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    if (!text && res.status >= 500) {
      throw new Error(
        "Servidor indisponível. Verifique se a API está rodando (porta 8765).",
      );
    }
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      throw new Error(
        "API offline (erro de proxy). Inicie: uvicorn main:app --port 8765",
      );
    }
    if (res.status === 401 && !skipAuthRedirect) {
      const onLogin =
        window.location.pathname === "/login" ||
        window.location.pathname === "/primeiro-acesso";
      if (!onLogin) {
        window.location.href = "/login";
      }
    }
    throw new Error(parseApiError(text));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
