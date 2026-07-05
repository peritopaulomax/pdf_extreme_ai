export function parseApiError(text: string): string {
  if (!text) return "Erro desconhecido";
  try {
    const j = JSON.parse(text) as {
      error?: string;
      detail?: string | { error?: string };
    };
    if (typeof j.detail === "object" && j.detail?.error) return j.detail.error;
    if (typeof j.detail === "string") return j.detail;
    if (j.error) return j.error;
  } catch {
    /* not JSON */
  }
  return text;
}
