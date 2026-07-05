interface ModelOption {
  id: string;
  label: string;
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
  model?: string;
  onModelChange?: (v: string) => void;
  modelOptions?: readonly ModelOption[];
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder = "Pergunte sobre os autos...",
  model,
  onModelChange,
  modelOptions,
}: Props) {
  return (
    <div className="composer">
      <div className="composer__box">
        <textarea
          className="composer__field"
          rows={2}
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (value.trim() && !disabled) onSubmit();
            }
          }}
        />
        <div className="composer__footer">
          <span className="composer__hint muted">
            Enter envia · Shift+Enter quebra linha
          </span>
          <div className="composer__controls">
            {modelOptions && onModelChange && model && (
              <select
                className="select select--composer"
                value={model}
                disabled={disabled}
                onChange={(e) => onModelChange(e.target.value)}
                title="Modelo"
              >
                {modelOptions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              className="btn btn--primary"
              disabled={disabled || !value.trim()}
              onClick={onSubmit}
            >
              Enviar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
