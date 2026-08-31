// Renderização da tela home: preenche #lista-fileiras com as fileiras de
// shelves.json, pôster a pôster, na ordem publicada. Módulo de DOM --
// sem teste unitário (ver Global Constraints), verificação é visual.

import { obterFilme } from "./store.js";
import { registrarAvaliacao, perfilLocal } from "./perfil.js";
import { amostraOnboarding } from "./onboarding.js";

const URL_POSTER = "https://image.tmdb.org/t/p/w185";
const URL_POSTER_GRANDE = "https://image.tmdb.org/t/p/w500";

function elementoPoster(id) {
  const filme = obterFilme(id);
  const div = document.createElement("a");
  div.href = `#/filme/${id}`;
  div.className = "poster";
  if (!filme) {
    div.textContent = "?";
    return div;
  }
  const img = document.createElement("img");
  img.src = filme.p ? `${URL_POSTER}${filme.p}` : "";
  img.alt = filme.t;
  img.loading = "lazy";
  div.appendChild(img);
  return div;
}

export function renderizarGrade(filmes, titulo) {
  document.getElementById("grade-titulo").textContent = titulo;

  const container = document.getElementById("grade-posteres");
  container.innerHTML = "";
  for (const filme of filmes) {
    const a = document.createElement("a");
    a.href = `#/filme/${filme.id}`;
    a.className = "poster";
    const img = document.createElement("img");
    img.src = filme.p ? `https://image.tmdb.org/t/p/w185${filme.p}` : "";
    img.alt = filme.t;
    img.loading = "lazy";
    a.appendChild(img);
    container.appendChild(a);
  }
}

export function popularFiltroGenero(generos) {
  const select = document.getElementById("filtro-genero");
  // Preserva a primeira opção ("Gênero", já no HTML) e adiciona o resto.
  for (const [id, nome] of Object.entries(generos).sort((a, b) => a[1].localeCompare(b[1], "pt-BR"))) {
    const opcao = document.createElement("option");
    opcao.value = id;
    opcao.textContent = nome;
    select.appendChild(opcao);
  }
}

function renderizarAcoesFicha(idFilme) {
  const container = document.getElementById("ficha-acoes");
  const entrada = perfilLocal().movies[String(idFilme)] || {};

  const botoes = [
    { rotulo: "Já vi", ativo: entrada.seen, aoClicar: () => registrarAvaliacao(idFilme, { seen: !entrada.seen }) },
    { rotulo: "👍 Gostei", ativo: entrada.rating === 1, aoClicar: () => registrarAvaliacao(idFilme, { rating: 1, seen: true }) },
    { rotulo: "👎 Não gostei", ativo: entrada.rating === -1, aoClicar: () => registrarAvaliacao(idFilme, { rating: -1, seen: true }) },
    { rotulo: "🔖 Quero ver", ativo: entrada.want, aoClicar: () => registrarAvaliacao(idFilme, { want: !entrada.want }) },
  ];

  container.innerHTML = "";
  for (const { rotulo, ativo, aoClicar } of botoes) {
    const botao = document.createElement("button");
    botao.textContent = rotulo;
    botao.className = ativo ? "botao-acao ativo" : "botao-acao";
    botao.addEventListener("click", () => {
      aoClicar();
      renderizarAcoesFicha(idFilme); // redesenha para refletir o novo estado
    });
    container.appendChild(botao);
  }
}

// Link clicável pra diretor/elenco na ficha -- leva pra grade filtrada por
// aquela pessoa (mesmo mecanismo de #/grade?keyword=<id>, ver router.js).
// Sem nome em nomes.json, ainda linka (rótulo cai pra "#<id>") -- diferente
// dos chips de keyword, que preferem sumir a mostrar um id cru.
function linkPessoa(id, nome, parametro) {
  return `<a href="#/grade?${parametro}=${id}" class="link-pessoa">${nome || `#${id}`}</a>`;
}

export function renderizarFicha(detalhe, nomes) {
  const container = document.getElementById("ficha-conteudo");

  const nomeDiretores = detalhe.d
    .map((id) => linkPessoa(id, nomes.director[id], "diretor"))
    .join(", ");
  const nomeElenco = detalhe.c
    .map((id) => linkPessoa(id, nomes.cast[id], "ator"))
    .join(", ");
  const chipsKeywords = detalhe.k
    .map((id) => (nomes.keyword && nomes.keyword[id] ? { id, nome: nomes.keyword[id] } : null))
    .filter(Boolean);

  // Nota do TMDB (0-10) + contagem de votos, sempre juntas -- uma nota alta
  // com poucos votos é bem menos confiável, e mostrar as duas deixa o
  // Fabio julgar isso sozinho em vez de esconder.
  const nota = typeof detalhe.v === "number" ? detalhe.v.toFixed(1) : null;
  const votos = typeof detalhe.n === "number" ? detalhe.n.toLocaleString("pt-BR") : null;

  container.innerHTML = `
    <div class="ficha">
      <img class="ficha-poster" src="${detalhe.p ? URL_POSTER_GRANDE + detalhe.p : ""}" alt="${detalhe.t}" />
      <div class="ficha-info">
        <h2>${detalhe.t} ${detalhe.y ? `(${detalhe.y})` : ""}</h2>
        ${nota ? `<p class="ficha-nota">⭐ ${nota} <span class="ficha-nota-votos">(${votos} votos)</span></p>` : ""}
        <p class="ficha-meta">${detalhe.r} min ${nomeDiretores ? "· dirigido por " + nomeDiretores : ""}</p>
        <p class="ficha-sinopse">${detalhe.ov || "Sem sinopse disponível."}</p>
        ${nomeElenco ? `<p class="ficha-elenco"><strong>Elenco:</strong> ${nomeElenco}</p>` : ""}
        ${chipsKeywords.length ? `<div class="ficha-keywords">${chipsKeywords.map(({ id, nome }) => `<a href="#/grade?keyword=${id}" class="chip">${nome}</a>`).join("")}</div>` : ""}
        <div class="ficha-acoes" id="ficha-acoes"></div>
        <div id="ficha-similares"></div>
      </div>
    </div>
  `;

  renderizarAcoesFicha(detalhe.id);
}

export function renderizarSimilares(pares) {
  const container = document.getElementById("ficha-similares");
  if (pares.length === 0) {
    container.innerHTML = "<p>Sem sugestões parecidas no momento.</p>";
    return;
  }
  const linha = document.createElement("div");
  linha.className = "fileira-linha";
  for (const { id } of pares) {
    linha.appendChild(elementoPoster(id));
  }
  container.innerHTML = "<h3>Se você gostou desse</h3>";
  container.appendChild(linha);
}

export function renderizarOnboarding(filmes, aoConcluir) {
  const amostra = amostraOnboarding(filmes, 200);
  let indice = 0;

  const container = document.getElementById("onboarding-cartoes");

  function proximo() {
    if (indice >= amostra.length) {
      aoConcluir();
      return;
    }
    const filme = amostra[indice];
    container.innerHTML = `
      <img src="https://image.tmdb.org/t/p/w342${filme.p || ""}" alt="${filme.t}" style="width:200px;border-radius:8px" />
      <p>${filme.t} ${filme.y ? `(${filme.y})` : ""}</p>
      <div class="onboarding-botoes">
        <button data-acao="visto-gostei">👍 Já vi, gostei</button>
        <button data-acao="visto-nao-gostei">👎 Já vi, não gostei</button>
        <button data-acao="nao-visto">Não vi</button>
        <button data-acao="pular">Pular</button>
      </div>
    `;
    container.querySelectorAll("button").forEach((botao) => {
      botao.addEventListener("click", () => {
        const acao = botao.dataset.acao;
        if (acao === "visto-gostei") registrarAvaliacao(filme.id, { rating: 1, seen: true });
        else if (acao === "visto-nao-gostei") registrarAvaliacao(filme.id, { rating: -1, seen: true });
        else if (acao === "nao-visto") registrarAvaliacao(filme.id, { seen: false });
        indice++;
        proximo();
      });
    });
  }
  proximo();
}

export function renderizarHome(fileiras) {
  const container = document.getElementById("lista-fileiras");
  container.innerHTML = "";

  for (const fileira of fileiras) {
    const secao = document.createElement("section");
    secao.className = "fileira";

    const titulo = document.createElement("a");
    titulo.href = `#/grade/${fileira.key}`;
    titulo.className = "fileira-titulo";
    titulo.textContent = fileira.title;
    secao.appendChild(titulo);

    const linha = document.createElement("div");
    linha.className = "fileira-linha";
    for (const id of fileira.ids) {
      linha.appendChild(elementoPoster(id));
    }
    secao.appendChild(linha);

    container.appendChild(secao);
  }
}
