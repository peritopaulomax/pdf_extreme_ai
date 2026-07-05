import type { ChatMessage, RetrievedChunk } from "../api/types";

export function buildExportMarkdown(opts: {
  projectName: string;
  modelName: string;
  userPrompt: string;
  assistantMessage: ChatMessage;
}): string {
  const { projectName, modelName, userPrompt, assistantMessage } = opts;
  const lines = [
    `# Resposta — ${projectName}`,
    "",
    `- **Modelo:** ${modelName}`,
    "",
    "## Pergunta",
    "",
    userPrompt.trim(),
    "",
    "## Resposta",
    "",
    assistantMessage.content.trim(),
    "",
  ];
  if (assistantMessage.thinking) {
    lines.push("## Thinking", "", assistantMessage.thinking.trim(), "");
  }
  if (assistantMessage.telemetry) {
    lines.push("## Telemetria", "", assistantMessage.telemetry, "");
  }
  const chunks = assistantMessage.retrieved_chunks;
  if (chunks?.length) {
    lines.push("## Trechos recuperados", "");
    chunks.forEach((ch: RetrievedChunk, i: number) => {
      const name = ch.display_name || ch.source_file || "?";
      lines.push(`### ${i + 1}. ${name} (p.${ch.page ?? 0})`, "", ch.snippet || "", "");
    });
  }
  return lines.join("\n").trim() + "\n";
}

export function downloadText(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
