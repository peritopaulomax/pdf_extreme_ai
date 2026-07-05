import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "pdf-extreme-ai-layout-v1";
const DEFAULT_NAV = 272;
const DEFAULT_SOURCES = 300;
const NAV_MIN = 220;
const NAV_MAX = 420;
const SOURCES_MIN = 240;
const SOURCES_MAX = 520;

type Stored = { nav?: number; sources?: number };

function load(): Stored {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Stored;
  } catch {
    return {};
  }
}

function save(data: Stored) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* ignore */
  }
}

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

export function useLayoutWidths() {
  const initial = load();
  const [navWidth, setNavWidthState] = useState(
    clamp(initial.nav ?? DEFAULT_NAV, NAV_MIN, NAV_MAX),
  );
  const [sourcesWidth, setSourcesWidthState] = useState(
    clamp(initial.sources ?? DEFAULT_SOURCES, SOURCES_MIN, SOURCES_MAX),
  );

  useEffect(() => {
    save({ nav: navWidth, sources: sourcesWidth });
  }, [navWidth, sourcesWidth]);

  const setNavWidth = useCallback((w: number) => {
    setNavWidthState(clamp(w, NAV_MIN, NAV_MAX));
  }, []);

  const setSourcesWidth = useCallback((w: number) => {
    setSourcesWidthState(clamp(w, SOURCES_MIN, SOURCES_MAX));
  }, []);

  return {
    navWidth,
    sourcesWidth,
    setNavWidth,
    setSourcesWidth,
    navMin: NAV_MIN,
    navMax: NAV_MAX,
    sourcesMin: SOURCES_MIN,
    sourcesMax: SOURCES_MAX,
  };
}
