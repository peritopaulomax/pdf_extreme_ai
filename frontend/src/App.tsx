import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UnifiedSidebar } from "./components/UnifiedSidebar";
import { MainWorkspace } from "./components/MainWorkspace";
import { ConfigDrawer } from "./components/ConfigDrawer";
import { ResizeHandle } from "./components/ResizeHandle";
import { PrivateRoute, AdminRoute } from "./components/PrivateRoute";
import { useLayoutWidths } from "./hooks/useLayoutWidths";
import { useWorkspaceUrl } from "./hooks/useWorkspaceUrl";
import { AuthProvider } from "./context/AuthContext";
import { LoginPage } from "./pages/LoginPage";
import { PrimeiroAcessoPage } from "./pages/PrimeiroAcessoPage";
import { UsuariosConfigPage } from "./pages/UsuariosConfigPage";
import type { WorkspaceMode } from "./api/types";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1 },
  },
});

const showDevFooter = import.meta.env.DEV;

function AppShell() {
  const {
    navWidth,
    sourcesWidth,
    setNavWidth,
    setSourcesWidth,
    navMin,
    navMax,
    sourcesMin,
    sourcesMax,
  } = useLayoutWidths();
  const { projectId: urlProjectId, conversationId: urlConversationId, setProjectId: setUrlProject, setConversationId: setUrlConversation } =
    useWorkspaceUrl();
  const [projectId, setProjectIdState] = useState<string | null>(urlProjectId);
  const [conversationId, setConversationIdState] = useState<string | null>(
    urlConversationId,
  );
  const [mode, setMode] = useState<WorkspaceMode>("rag");
  const [configOpen, setConfigOpen] = useState(false);

  useEffect(() => {
    setProjectIdState(urlProjectId);
    setConversationIdState(urlConversationId);
  }, [urlProjectId, urlConversationId]);

  const setProjectId = useCallback(
    (id: string | null) => {
      setProjectIdState(id);
      setUrlProject(id);
      if (!id) {
        setConversationIdState(null);
        setUrlConversation(null);
      }
    },
    [setUrlProject, setUrlConversation],
  );

  const setConversationId = useCallback(
    (id: string | null) => {
      setConversationIdState(id || null);
      setUrlConversation(id || null);
    },
    [setUrlConversation],
  );

  const handleProjectSelect = useCallback(
    (id: string) => {
      if (id) {
        setProjectId(id);
        setConversationId(null);
      } else {
        setProjectId(null);
      }
      setConfigOpen(false);
    },
    [setProjectId, setConversationId],
  );

  return (
    <div className="app">
      <div className="app__nav" style={{ width: navWidth }}>
        <UnifiedSidebar
          projectId={projectId}
          conversationId={conversationId}
          mode={mode}
          onSelectProject={handleProjectSelect}
          onSelectConversation={setConversationId}
          onOpenConfig={() => setConfigOpen(true)}
        />
      </div>
      <ResizeHandle
        getWidth={() => navWidth}
        onResize={setNavWidth}
        min={navMin}
        max={navMax}
      />
      <MainWorkspace
        projectId={projectId}
        conversationId={conversationId}
        mode={mode}
        onModeChange={setMode}
        onConversationId={setConversationId}
        sourcesWidth={sourcesWidth}
        onSourcesWidthChange={setSourcesWidth}
        sourcesMin={sourcesMin}
        sourcesMax={sourcesMax}
      />
      <ConfigDrawer
        open={configOpen}
        projectId={projectId}
        onClose={() => setConfigOpen(false)}
      />
      {showDevFooter && (
        <footer className="app-dev-footer" title="Somente em desenvolvimento">
          dev
        </footer>
      )}
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/primeiro-acesso" element={<PrimeiroAcessoPage />} />
            <Route
              path="/configuracoes/usuarios"
              element={
                <AdminRoute>
                  <UsuariosConfigPage />
                </AdminRoute>
              }
            />
            <Route
              path="/"
              element={
                <PrivateRoute>
                  <AppShell />
                </PrivateRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
