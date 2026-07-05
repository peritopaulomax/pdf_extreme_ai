import { useState } from "react";

interface Props {
  thinking: string;
  defaultExpanded?: boolean;
}

export function ThinkingBlock({ thinking, defaultExpanded = false }: Props) {
  const [open, setOpen] = useState(defaultExpanded);

  return (
    <details
      className="thinking-block"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary>Thinking do modelo</summary>
      <pre className="thinking-block__body">{thinking}</pre>
    </details>
  );
}
