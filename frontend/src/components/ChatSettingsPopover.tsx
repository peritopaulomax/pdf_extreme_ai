import { useRef, useEffect, useState } from "react";
import { PROFILE_OPTIONS } from "../api/types";
import type { ChatMode } from "../api/types";

interface Props {
  mode: ChatMode;
  profile: string;
  auditMode: boolean;
  deepMode?: boolean;
  useProjectMemory: boolean;
  onProfileChange: (v: string) => void;
  onAuditModeChange: (v: boolean) => void;
  onDeepModeChange?: (v: boolean) => void;
  onUseProjectMemoryChange: (v: boolean) => void;
  disabled?: boolean;
}

export function ChatSettingsPopover({
  mode,
  profile,
  auditMode,
  deepMode = false,
  useProjectMemory,
  onProfileChange,
  onAuditModeChange,
  onDeepModeChange,
  onUseProjectMemoryChange,
  disabled,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="settings-popover" ref={ref}>
      <button
        type="button"
        className="btn btn--ghost btn--icon"
        title="Configurações do chat"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        ⚙
      </button>
      {open && (
        <div className="settings-popover__menu">
          {mode === "rag" && (
            <>
              <label className="settings-popover__row">
                <span>Estratégia RAG</span>
                <select
                  className="select"
                  value={profile}
                  onChange={(e) => onProfileChange(e.target.value)}
                >
                  {PROFILE_OPTIONS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="settings-popover__check">
                <input
                  type="checkbox"
                  checked={auditMode}
                  onChange={(e) => onAuditModeChange(e.target.checked)}
                />
                Modo auditoria
              </label>
              <label className="settings-popover__check">
                <input
                  type="checkbox"
                  checked={deepMode}
                  onChange={(e) => onDeepModeChange?.(e.target.checked)}
                />
                Modo profundo
              </label>
              {deepMode && (
                <p className="muted settings-popover__hint">
                  Ativa busca mais ampla com perfil pericial, multi-query e reforço de referências cruzadas.
                </p>
              )}
            </>
          )}
          {mode === "free" && (
            <label className="settings-popover__check">
              <input
                type="checkbox"
                checked={useProjectMemory}
                onChange={(e) => onUseProjectMemoryChange(e.target.checked)}
              />
              Incluir memória do caso
            </label>
          )}
        </div>
      )}
    </div>
  );
}
