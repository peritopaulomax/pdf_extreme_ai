export interface SseMessage {
  event: string;
  data: string;
}

export function parseSseChunk(buffer: string): {
  messages: SseMessage[];
  remainder: string;
} {
  const messages: SseMessage[] = [];
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";

  for (const block of parts) {
    if (!block.trim()) continue;
    let event = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (dataLines.length) {
      messages.push({ event, data: dataLines.join("\n") });
    }
  }
  return { messages, remainder };
}

export function parseSseData<T>(data: string): T | null {
  try {
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}
