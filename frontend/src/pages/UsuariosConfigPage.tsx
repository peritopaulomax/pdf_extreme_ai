import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addAdministrador,
  addConsultor,
  listAdministradores,
  listConsultores,
  removeAdministrador,
  removeConsultor,
  resetConsultorSenha,
} from "../api/auth";
import { useAuth } from "../context/AuthContext";

export function UsuariosConfigPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [newAdmin, setNewAdmin] = useState("");
  const [newConsultor, setNewConsultor] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const { data: adminsData } = useQuery({
    queryKey: ["auth", "admins"],
    queryFn: listAdministradores,
  });

  const { data: consultoresData } = useQuery({
    queryKey: ["auth", "consultores"],
    queryFn: listConsultores,
  });

  const admins = adminsData?.administradores ?? [];
  const consultores = consultoresData?.consultores ?? [];

  const flash = (message: string) => {
    setMsg(message);
    setErr(null);
    window.setTimeout(() => setMsg(null), 4000);
  };

  const flashErr = (message: string) => {
    setErr(message);
    setMsg(null);
  };

  const addAdminMut = useMutation({
    mutationFn: addAdministrador,
    onSuccess: (r) => {
      flash(r.message);
      setNewAdmin("");
      qc.invalidateQueries({ queryKey: ["auth", "admins"] });
    },
    onError: (e: Error) => flashErr(e.message),
  });

  const delAdminMut = useMutation({
    mutationFn: removeAdministrador,
    onSuccess: (r) => {
      flash(r.message);
      qc.invalidateQueries({ queryKey: ["auth", "admins"] });
    },
    onError: (e: Error) => flashErr(e.message),
  });

  const addConsMut = useMutation({
    mutationFn: addConsultor,
    onSuccess: (r) => {
      flash(r.message);
      setNewConsultor("");
      qc.invalidateQueries({ queryKey: ["auth", "consultores"] });
    },
    onError: (e: Error) => flashErr(e.message),
  });

  const delConsMut = useMutation({
    mutationFn: removeConsultor,
    onSuccess: (r) => {
      flash(r.message);
      qc.invalidateQueries({ queryKey: ["auth", "consultores"] });
    },
    onError: (e: Error) => flashErr(e.message),
  });

  const resetMut = useMutation({
    mutationFn: resetConsultorSenha,
    onSuccess: (r) => {
      flash(r.message);
      qc.invalidateQueries({ queryKey: ["auth", "consultores"] });
    },
    onError: (e: Error) => flashErr(e.message),
  });

  return (
    <div className="auth-page usuarios-config-page">
      <div className="usuarios-config">
      <header className="usuarios-config__header">
        <Link to="/" className="btn btn--ghost">
          ← Voltar
        </Link>
        <h1>Configuração de usuários</h1>
      </header>

      {msg && <p className="auth-alert auth-alert--success">{msg}</p>}
      {err && <p className="auth-alert auth-alert--error">{err}</p>}

      <section className="usuarios-section">
        <h2>Administradores</h2>
        <p className="muted">Total: {admins.length}</p>
        <ul className="usuarios-list">
          {admins.map((a) => (
            <li key={a} className="usuarios-list__item">
              <span>{a}</span>
              {a !== user?.usuario && (
                <button
                  type="button"
                  className="btn btn--sm btn--danger"
                  onClick={() => {
                    if (
                      confirm(
                        `Remover administrador "${a}"?`,
                      )
                    ) {
                      delAdminMut.mutate(a);
                    }
                  }}
                >
                  Remover
                </button>
              )}
            </li>
          ))}
        </ul>
        <div className="usuarios-add">
          <input
            className="input"
            placeholder="novo.admin"
            value={newAdmin}
            onChange={(e) => setNewAdmin(e.target.value)}
          />
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => newAdmin.trim() && addAdminMut.mutate(newAdmin.trim())}
          >
            Adicionar
          </button>
        </div>
      </section>

      <section className="usuarios-section">
        <h2>Consultores</h2>
        <p className="muted">Total: {consultores.length}</p>
        <ul className="usuarios-list">
          {consultores.map((c) => (
            <li key={c.nome} className="usuarios-list__item">
              <span>{c.nome}</span>
              <span
                className={`usuarios-badge ${c.tem_senha ? "usuarios-badge--ok" : "usuarios-badge--warn"}`}
              >
                {c.tem_senha ? "Senha cadastrada" : "Sem senha"}
              </span>
              <div className="usuarios-list__actions">
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={!c.tem_senha}
                  onClick={() => {
                    if (
                      confirm(
                        `Resetar senha de "${c.nome}"? Ele precisará fazer novo primeiro acesso.`,
                      )
                    ) {
                      resetMut.mutate(c.nome);
                    }
                  }}
                >
                  Resetar senha
                </button>
                <button
                  type="button"
                  className="btn btn--sm btn--danger"
                  onClick={() => {
                    if (confirm(`Remover consultor "${c.nome}"?`)) {
                      delConsMut.mutate(c.nome);
                    }
                  }}
                >
                  Remover
                </button>
              </div>
            </li>
          ))}
        </ul>
        <div className="usuarios-add">
          <input
            className="input"
            placeholder="consultor.nome"
            value={newConsultor}
            onChange={(e) => setNewConsultor(e.target.value)}
          />
          <button
            type="button"
            className="btn btn--primary"
            onClick={() =>
              newConsultor.trim() && addConsMut.mutate(newConsultor.trim())
            }
          >
            Adicionar
          </button>
        </div>
      </section>
      </div>
    </div>
  );
}
