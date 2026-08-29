// Renderização da tela home: preenche #lista-fileiras com as fileiras de
// shelves.json, pôster a pôster, na ordem publicada. Módulo de DOM --
// sem teste unitário (ver Global Constraints), verificação é visual.

import { obterFilme } from "./store.js";

const URL_POSTER = "https://image.tmdb.org/t/p/w185";

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
