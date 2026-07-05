import { useCallback, useEffect, useRef } from "react";

interface Props {
  onResize: (width: number) => void;
  getWidth: () => number;
  min: number;
  max: number;
}

export function ResizeHandle({ onResize, getWidth, min, max }: Props) {
  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(0);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      startX.current = e.clientX;
      startW.current = getWidth();
      document.body.classList.add("is-resizing");
    },
    [getWidth],
  );

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      const next = Math.min(max, Math.max(min, startW.current + delta));
      onResize(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.classList.remove("is-resizing");
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [min, max, onResize]);

  return (
    <div
      className="resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Redimensionar painel"
      onMouseDown={onMouseDown}
    />
  );
}
