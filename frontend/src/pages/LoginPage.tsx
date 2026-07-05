import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const successMsg = (location.state as { message?: string } | null)?.message;

  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) navigate("/", { replace: true });
  }, [user, loading, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(usuario, senha);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao entrar");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">Acesso ao Sistema</h1>
        <p className="auth-card__subtitle muted">PDF Extreme AI</p>

        {successMsg && <p className="auth-alert auth-alert--success">{successMsg}</p>}
        {error && <p className="auth-alert auth-alert--error">{error}</p>}

        <form onSubmit={handleSubmit} className="auth-form">
          <label className="auth-form__label">
            Usuário
            <input
              className="input"
              type="text"
              autoComplete="username"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              disabled={submitting}
            />
          </label>
          <label className="auth-form__label">
            Senha
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              placeholder="Digite sua senha do sistema"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              disabled={submitting}
            />
          </label>
          <button type="submit" className="btn btn--primary auth-form__submit" disabled={submitting}>
            {submitting ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="auth-card__footer">
          <Link to="/primeiro-acesso">Primeiro Acesso</Link>
        </p>
      </div>
    </div>
  );
}
