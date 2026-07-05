import { apiFetch } from "./client";

export interface AuthUser {
  usuario: string;
  perfil: "admin" | "consultor";
}

export async function fetchMe(): Promise<AuthUser | null> {
  try {
    const r = await apiFetch<{ success: boolean; usuario: string; perfil: string }>(
      "/auth/me",
      { skipAuthRedirect: true },
    );
    return {
      usuario: r.usuario,
      perfil: r.perfil as AuthUser["perfil"],
    };
  } catch {
    return null;
  }
}

export async function login(usuario: string, senha: string) {
  return apiFetch<{ success: boolean; usuario: string; perfil: string }>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ usuario, senha }),
      skipAuthRedirect: true,
    },
  );
}

export async function logout() {
  return apiFetch<{ success: boolean }>("/auth/logout", {
    method: "POST",
    skipAuthRedirect: true,
  });
}

export async function checkPrimeiroAcesso(usuario: string) {
  const q = encodeURIComponent(usuario);
  return apiFetch<{
    autorizado: boolean;
    tem_senha: boolean;
  }>(`/auth/primeiro-acesso/check?usuario=${q}`, { skipAuthRedirect: true });
}

export async function primeiroAcesso(
  usuario: string,
  senha: string,
  senha_confirmacao: string,
) {
  return apiFetch<{ success: boolean; message: string }>("/auth/primeiro-acesso", {
    method: "POST",
    body: JSON.stringify({ usuario, senha, senha_confirmacao }),
    skipAuthRedirect: true,
  });
}

export async function listAdministradores() {
  return apiFetch<{ success: boolean; administradores: string[] }>(
    "/auth/administradores",
  );
}

export async function addAdministrador(nome: string) {
  return apiFetch<{ success: boolean; message: string }>("/auth/administradores", {
    method: "POST",
    body: JSON.stringify({ nome }),
  });
}

export async function removeAdministrador(nome: string) {
  return apiFetch<{ success: boolean; message: string }>("/auth/administradores", {
    method: "DELETE",
    body: JSON.stringify({ nome }),
  });
}

export interface ConsultorRow {
  nome: string;
  tem_senha: boolean;
}

export async function listConsultores() {
  return apiFetch<{ success: boolean; consultores: ConsultorRow[] }>(
    "/auth/consultores",
  );
}

export async function addConsultor(nome: string) {
  return apiFetch<{ success: boolean; message: string }>("/auth/consultores", {
    method: "POST",
    body: JSON.stringify({ nome }),
  });
}

export async function removeConsultor(nome: string) {
  return apiFetch<{ success: boolean; message: string }>("/auth/consultores", {
    method: "DELETE",
    body: JSON.stringify({ nome }),
  });
}

export async function resetConsultorSenha(nome: string) {
  return apiFetch<{ success: boolean; message: string }>(
    "/auth/consultores/resetar-senha",
    {
      method: "POST",
      body: JSON.stringify({ nome }),
    },
  );
}
