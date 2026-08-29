// Persistência do perfil via API de Conteúdo do GitHub. Projeto pessoal,
// repositório único -- owner/repo fixos de propósito, não é configurável.

const OWNER = "dicasdofabrito";
const REPO = "filmes-do-fabrito";
const CAMINHO_PERFIL = "data/profile.json";
const CHAVE_TOKEN = "fdf_token";

export function obterToken() {
  return localStorage.getItem(CHAVE_TOKEN);
}

export function salvarToken(token) {
  localStorage.setItem(CHAVE_TOKEN, token);
}

function paraBase64(texto) {
  const bytes = new TextEncoder().encode(texto);
  let binario = "";
  for (const byte of bytes) binario += String.fromCharCode(byte);
  return btoa(binario);
}

function deBase64(base64) {
  const binario = atob(base64.replace(/\n/g, ""));
  const bytes = Uint8Array.from(binario, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function cabecalhos(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

export async function lerPerfilRemoto(token) {
  const resposta = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/${CAMINHO_PERFIL}`,
    { headers: cabecalhos(token) }
  );

  if (resposta.status === 404) {
    return { perfil: { movies: {} }, sha: null };
  }
  if (!resposta.ok) {
    throw new Error(`falha ao ler perfil remoto: ${resposta.status}`);
  }

  const dados = await resposta.json();
  return { perfil: JSON.parse(deBase64(dados.content)), sha: dados.sha };
}

// Por filme, o registro com `at` mais recente vence -- `at` é uma data ISO
// (YYYY-MM-DD), comparável como string.
export function mesclarPerfis(remoto, local) {
  const resultado = { movies: { ...remoto.movies } };
  for (const [id, entradaLocal] of Object.entries(local.movies || {})) {
    const entradaRemota = resultado.movies[id];
    if (!entradaRemota || (entradaLocal.at || "") >= (entradaRemota.at || "")) {
      resultado.movies[id] = entradaLocal;
    }
  }
  return resultado;
}

export async function salvarPerfilRemoto(token, perfil, sha, tentativa = 1) {
  const corpo = {
    message: "atualiza avaliacoes",
    content: paraBase64(JSON.stringify(perfil, null, 2)),
    branch: "master",
  };
  if (sha) corpo.sha = sha;

  const resposta = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/${CAMINHO_PERFIL}`,
    { method: "PUT", headers: cabecalhos(token), body: JSON.stringify(corpo) }
  );

  if (resposta.ok) {
    const dados = await resposta.json();
    return { sha: dados.content.sha };
  }

  if (resposta.status === 409 && tentativa < 3) {
    const { perfil: perfilAtual, sha: shaAtual } = await lerPerfilRemoto(token);
    const mesclado = mesclarPerfis(perfilAtual, perfil);
    return salvarPerfilRemoto(token, mesclado, shaAtual, tentativa + 1);
  }

  throw new Error(`falha ao salvar perfil remoto apos ${tentativa} tentativa(s): ${resposta.status}`);
}
