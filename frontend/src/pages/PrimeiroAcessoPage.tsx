import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { checkPrimeiroAcesso, primeiroAcesso } from "../api/auth";

export function PrimeiroAcessoPage() {
  const navigate = useNavigate();
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [senhaConfirmacao, setSenhaConfirmacao] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const check = await checkPrimeiroAcesso(usuario);
      if (!check.autorizado) {
        setError("Usuário não cadastrado. Entre em contato com um administrador.");
        return;
      }
      if (check.tem_senha) {
        setError("Usuário já possui senha cadastrada. Use a tela de login.");
        return;
      }
      const r = await primeiroAcesso(usuario, senha, senhaConfirmacao);
      navigate("/login", {
        replace: true,
        state: { message: r.message },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao cadastrar senha");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-card__title">Primeiro Acesso</h1>
        <p className="auth-card__subtitle muted">PDF Extreme AI</p>

        <p className="auth-help muted">
          Digite o mesmo usuário que consta na lista de administradores ou consultores.
        </p>
        <p className="auth-help muted">
          Senha: mínimo 8 caracteres, maiúsculas, minúsculas e números.
        </p>

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
              disabled={loading}
            />
          </label>
          <label className="auth-form__label">
            Senha
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              disabled={loading}
            />
          </label>
          <label className="auth-form__label">
            Confirmar senha
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              value={senhaConfirmacao}
              onChange={(e) => setSenhaConfirmacao(e.target.value)}
              disabled={loading}
            />
          </label>
          <button type="submit" className="btn btn--primary auth-form__submit" disabled={loading}>
            {loading ? "Salvando..." : "Cadastrar senha"}
          </button>
        </form>

        <p className="auth-card__footer">
          <Link to="/login">Voltar ao login</Link>
        </p>
      </div>
    </div>
  );
}
