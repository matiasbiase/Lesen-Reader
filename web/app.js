/* lesen — frontend.
   Regla de interacción: tocar una palabra tiene que responder YA. Por eso el
   diccionario se pide primero y se pinta apenas llega, y el análisis del LLM
   (que tarda unos segundos) entra después en el mismo panel, sin bloquear.
   Regla de interfaz: si un ícono alcanza, no va texto. */

const $ = (s) => document.querySelector(s);
const api = async (path, body, method) => {
  const r = await fetch("/api" + path, {
    method: method || (body ? "POST" : "GET"),
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return r.json();
};

const svg = (d, extra = "") =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ${extra}>${d}</svg>`;

const ICONS = {
  // temas
  deutschland: svg(`<path d="M3 21h18M5 21V10l7-5 7 5v11M10 21v-6h4v6" stroke-linejoin="round"/>`),
  welt:        svg(`<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.4 4 5.6 4 9s-1.5 6.6-4 9c-2.5-2.4-4-5.6-4-9s1.5-6.6 4-9z"/>`),
  wirtschaft:  svg(`<path d="M3 17l5.5-5.5 3.5 3.5 8-8" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 7h5v5" stroke-linecap="round" stroke-linejoin="round"/>`),
  wissen:      svg(`<path d="M9.5 3h5M10.5 3v6L5.6 18.6A1.6 1.6 0 007 21h10a1.6 1.6 0 001.4-2.4L13.5 9V3" stroke-linejoin="round"/>`),
  tech:        svg(`<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4" stroke-linecap="round"/>`),
  aktuell:     svg(`<path d="M13 2L4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5z" stroke-linejoin="round"/>`),
  // interfaz
  tag:      svg(`<path d="M3 12V5a2 2 0 012-2h7l9 9-9 9-9-9z" stroke-linejoin="round"/><circle cx="7.5" cy="7.5" r="1.2"/>`),
  clock:    svg(`<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2" stroke-linecap="round"/>`),
  check:    svg(`<path d="M4 12.5l5 5 11-11" stroke-linecap="round" stroke-linejoin="round"/>`),
  book:     svg(`<path d="M12 6.6C10.4 5.1 7.9 4.6 4 5.1v12.6c3.9-.5 6.4 0 8 1.5 1.6-1.5 4.1-2 8-1.5V5.1c-3.9-.5-6.4 0-8 1.5z" stroke-linejoin="round"/>`),
  spark:    svg(`<path d="M12 3l1.9 5.3L19 10l-5.1 1.7L12 17l-1.9-5.3L5 10l5.1-1.7L12 3z" stroke-linejoin="round"/>`),
  warn:     svg(`<path d="M12 4l9 16H3l9-16z" stroke-linejoin="round"/><path d="M12 10v4M12 17.2v.1" stroke-linecap="round"/>`),
  close:    svg(`<path d="M6 6l12 12M18 6L6 18" stroke-linecap="round"/>`),
  trash:    svg(`<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" stroke-linecap="round" stroke-linejoin="round"/>`),
  bookmark: svg(`<path d="M6 4h12v17l-6-4-6 4V4z" stroke-linejoin="round"/>`),
  translate:svg(`<path d="M4 6h10M9 4v2c0 4-2.2 7.5-5 9" stroke-linecap="round"/><path d="M7 12c1.6 2.4 3.8 4 6 4.8" stroke-linecap="round"/><path d="M13 20l4-9 4 9M14.6 17h4.8" stroke-linecap="round" stroke-linejoin="round"/>`),
  layers:   svg(`<path d="M12 3l9 5-9 5-9-5 9-5z" stroke-linejoin="round"/><path d="M3 13l9 5 9-5" stroke-linejoin="round"/>`),
  // categorías gramaticales
  sustantivo: svg(`<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 10h8M8 14h5" stroke-linecap="round"/>`),
  verbo:      svg(`<path d="M5 12h9" stroke-linecap="round"/><path d="M11 8l4 4-4 4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="19" cy="12" r="1.4"/>`),
  adjetivo:   svg(`<path d="M12 4l2.4 5.4L20 11l-5.6 1.6L12 18l-2.4-5.4L4 11l5.6-1.6L12 4z" stroke-linejoin="round"/>`),
};
const posIcon = (pos) => ICONS[pos] || "";

// En noticias casi todo es presente, Perfekt y Präteritum: marcarlos no aporta.
// Solo se señala lo que se sale de eso, que es lo que da ganas de leer la nota.
const COMMON = ["praesens", "perfekt", "praeteritum"];
const rareOf = (ts) => (ts || []).filter((t) => !COMMON.includes(t));

/* ---------- tema ---------- */

const SUN = svg(`<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.6 1.6M18.2 18.2l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.6-1.6M18.2 5.8l1.6-1.6" stroke-linecap="round"/>`);
const MOON = svg(`<path d="M20 13.4A8.2 8.2 0 1110.6 4a6.8 6.8 0 009.4 9.4z" stroke-linejoin="round"/>`);

// Todo con ?. : si el HTML que el navegador tiene en caché es más viejo que
// este script, el botón puede no existir. Sin las guardas, un `null.innerHTML`
// tira TypeError acá arriba y aborta el archivo entero: no se enganchan las
// pestañas, no se cargan las noticias, la pantalla queda muerta. Un detalle
// cosmético como el tema no puede tener el poder de voltear la app.
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("lesen-theme", t); } catch (e) {}
  const dark = t === "dark";
  const btn = $("#theme");
  if (btn) {
    btn.innerHTML = dark ? SUN : MOON;
    btn.setAttribute("aria-label", dark ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
  }
  // sin esto la barra de estado de iOS queda del color del tema anterior
  $("#theme-color")?.setAttribute("content", dark ? "#14130f" : "#faf8f4");
  document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]')
    ?.setAttribute("content", dark ? "black-translucent" : "default");
}

applyTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
const themeBtn = $("#theme");
if (themeBtn) {
  themeBtn.onclick = () =>
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
}

const S = {
  topics: [], interests: [], tenses: [], tenseNames: {},
  article: null, statuses: {}, saved: false,
  sel: null, entry: null, chosen: null, sepOk: null, savedWord: null,
  filter: "todas", queue: [], qi: 0, revealed: false,
};

/* ---------- navegación ---------- */

function show(v) {
  document.querySelectorAll(".view").forEach((s) => s.classList.remove("on"));
  $("#v-" + v).classList.add("on");
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.v === v));
  $("#back").hidden = v !== "read";
  $("#bookmark").hidden = v !== "read" || !S.article;
  $("#title").textContent = { feed: "lesen", read: S.article?.title || "Leyendo",
    saved: "Guardadas", vocab: "Tus palabras", study: "Repaso" }[v];
  window.scrollTo(0, 0);
  if (v === "vocab") loadVocab();
  if (v === "study") loadStudy();
  if (v === "saved") loadSaved();
}
document.querySelectorAll(".tab").forEach((t) => t.onclick = () => show(t.dataset.v));
$("#back").onclick = () => show("feed");

/* ---------- temas e intereses ---------- */

async function loadTopics() {
  const { topics } = await api("/topics");
  const prefs = await api("/prefs");
  S.topics = prefs.topics || [];
  S.interests = prefs.interests || [];
  $("#topics").innerHTML = topics.map((t) =>
    `<button class="chip ${S.topics.includes(t.id) ? "on" : ""}" data-t="${t.id}"
      >${ICONS[t.id] || ""}${t.name}</button>`).join("");
  $("#topics").querySelectorAll(".chip").forEach((c) => c.onclick = () => {
    const id = c.dataset.t;
    S.topics = S.topics.includes(id) ? S.topics.filter((x) => x !== id) : [...S.topics, id];
    c.classList.toggle("on");
    savePrefs(); loadHeadlines();
  });
  renderKws();
  loadHeadlines();
}

function renderKws() {
  $("#kws").innerHTML = S.interests.map((k) =>
    `<button class="chip kw" data-k="${esc(k)}">${esc(k)}${ICONS.close}</button>`).join("");
  $("#kws").querySelectorAll(".chip").forEach((c) => c.onclick = () => {
    S.interests = S.interests.filter((x) => x !== c.dataset.k);
    renderKws(); savePrefs(); loadHeadlines();
  });
}

$("#kwform").onsubmit = (e) => {
  e.preventDefault();
  const v = $("#kwinput").value.trim();
  if (v && !S.interests.includes(v)) {
    S.interests.push(v);
    $("#kwinput").value = "";
    renderKws(); savePrefs(); loadHeadlines();
  }
};

const savePrefs = () => api("/prefs", { topics: S.topics, interests: S.interests });

function renderTenseFilter() {
  $("#tenses").innerHTML = Object.entries(S.tenseNames).map(([k, name]) =>
    `<button class="chip ${S.tenses.includes(k) ? "on" : ""}" data-t="${k}">${name}</button>`).join("");
  $("#tenses").querySelectorAll(".chip").forEach((c) => c.onclick = () => {
    const id = c.dataset.t;
    S.tenses = S.tenses.includes(id) ? S.tenses.filter((x) => x !== id) : [...S.tenses, id];
    c.classList.toggle("on");
    loadHeadlines();
  });
}

/* ---------- noticias ---------- */

async function loadHeadlines() {
  $("#list").innerHTML = `<div class="spinner"></div>`;
  const q = `topics=${S.topics.join(",")}&interests=${encodeURIComponent(S.interests.join(","))}`
          + `&tenses=${S.tenses.join(",")}`;
  const { items, tense_names } = await api("/headlines?" + q);
  if (tense_names && !Object.keys(S.tenseNames).length) {
    S.tenseNames = tense_names; renderTenseFilter();
  }
  if (!items?.length) {
    $("#list").innerHTML = `<div class="empty">${ICONS.welt}<div class="big">Nada por acá</div></div>`;
    return;
  }
  $("#list").innerHTML = items.map((it, i) => `
    <button class="card" data-i="${i}">
      <h2>${esc(it.title)}</h2>
      ${it.summary ? `<p>${esc(it.summary.slice(0, 150))}${it.summary.length > 150 ? "…" : ""}</p>` : ""}
      <div class="meta">
        <span class="src">${ICONS[it.topic] || ""}${esc(it.source)}</span>
        ${(it.matched || []).slice(0, 2).map((m) => `<span class="hit">${ICONS.tag}${esc(m)}</span>`).join("")}
        ${(it.rare || []).slice(0, 2).map((t) =>
          `<span class="tense">${ICONS.clock}${esc(S.tenseNames[t] || t)}</span>`).join("")}
      </div>
    </button>`).join("");
  $("#list").querySelectorAll(".card").forEach((c) => c.onclick = () => openArticle(items[+c.dataset.i]));
}

/* ---------- lector ---------- */

async function openArticle(item) {
  show("read");
  $("#article").innerHTML = `<div class="spinner"></div>`;
  const a = await api("/article", { url: item.link || item.url });
  if (a.error) {
    $("#article").innerHTML = `<div class="empty">${ICONS.warn}<div class="big">No pude abrir esta nota</div></div>`;
    return;
  }
  S.article = { ...a, source: item.source, url: item.link || item.url, topic: item.topic };
  S.statuses = a.statuses || {};
  S.saved = !!a.saved;
  $("#title").textContent = a.title || item.title;
  $("#bookmark").hidden = false;
  $("#bookmark").classList.toggle("on", S.saved);
  renderArticle();
}

$("#bookmark").onclick = async () => {
  if (!S.article) return;
  if (S.saved) {
    await api("/saved?url=" + encodeURIComponent(S.article.url), null, "DELETE");
    S.saved = false;
  } else {
    await api("/saved", { url: S.article.url, title: S.article.title,
      source: S.article.source || "", topic: S.article.topic || "",
      text: S.article.text, tenses: S.article.tenses || [] });
    S.saved = true;
  }
  $("#bookmark").classList.toggle("on", S.saved);
};

function renderArticle() {
  const a = S.article;
  const words = a.tokens.map((t, i) => {
    if (!t.tappable) return esc(t.text).replace(/\n\n/g, "</p><p>") + (t.ws ? " " : "");
    const st = S.statuses[t.lemma] || "";
    return `<span class="w ${st}" data-i="${i}">${esc(t.text)}</span>${t.ws ? " " : ""}`;
  }).join("");

  $("#article").innerHTML = `
    <div class="reader">
      <h1>${esc(a.title || "")}</h1>
      <div class="byline">
        <span class="origin">${ICONS[a.topic] || ICONS.aktuell}${esc(a.source || "")}</span>
        ${rareOf(a.tenses).map((t) =>
          `<span class="tense">${ICONS.clock}${esc(S.tenseNames[t] || t)}</span>`).join("")}
      </div>
      <div class="prose"><p>${words}</p></div>
    </div>`;

  $("#article").querySelectorAll(".w").forEach((el) => el.onclick = () => tapWord(+el.dataset.i));
}

function tapWord(i) {
  const a = S.article;
  const tok = a.tokens[i];
  const main = tok.is_particle_of != null ? a.tokens[tok.is_particle_of] : tok;

  document.querySelectorAll(".w").forEach((e) => e.classList.remove("sel", "pair"));
  const lit = [main.i];
  if (main.separable?.split) lit.push(main.separable.particle_i);
  lit.forEach((k) => {
    const el = document.querySelector(`.w[data-i="${k}"]`);
    if (el) el.classList.add(lit.length > 1 ? "pair" : "sel");
  });

  S.sel = { tok: main, tapped: tok };
  openSheet(main);
}

/* ---------- hoja de palabra ---------- */

function openSheet(tok) {
  $("#scrim").classList.add("on");
  $("#sheet").classList.add("on");
  $("#sheet").scrollTop = 0;
  S.entry = null; S.chosen = null; S.sepOk = null; S.savedWord = null;
  renderSheet({ loading: true });

  const payload = { word: tok.text, lemma: tok.lemma, sentence: tok.sent,
                    pos: tok.pos, separable: tok.separable || null };

  api("/word", payload).then((d) => {
    S.entry = d.entry; S.savedWord = d.saved; S.sepOk = d.separable_ok;
    if (d.lemma) S.sel.tok = { ...S.sel.tok, lemma: d.lemma };
    if (d.entry?.senses?.length) S.chosen = d.entry.senses[0].n;
    // Si la detección de separable no se confirmó, apago el resaltado del par:
    // no quiero mostrar una Satzklammer que no existe.
    if (tok.separable?.split && !d.separable_ok) {
      document.querySelectorAll(".w.pair").forEach((e) => e.classList.remove("pair"));
      document.querySelector(`.w[data-i="${tok.i}"]`)?.classList.add("sel");
    }
    renderSheet({ ai: "cargando" });
  });

  api("/context", payload).then((ai) => {
    if (S.sel?.tok.i !== tok.i) return;
    if (ai.sense_n) S.chosen = ai.sense_n;
    renderSheet({ ai });
  });
}

function closeSheet() {
  $("#scrim").classList.remove("on");
  $("#sheet").classList.remove("on");
  document.querySelectorAll(".w").forEach((e) => e.classList.remove("sel", "pair"));
  S.sel = null;
}
$("#scrim").onclick = closeSheet;

const ES = `<span class="eslabel">es</span>`;

function renderSheet(o) {
  const tok = S.sel?.tok;
  if (!tok) return;
  const sep = tok.separable;
  const e = S.entry;

  let h = `<div class="headword">
      ${tok.article ? `<span class="art">${esc(tok.article)}</span>` : ""}
      <span class="lemma">${esc(tok.lemma)}</span>
      <span class="pos">${posIcon(tok.pos_es)}${esc(tok.pos_es || "")}</span>
    </div>`;

  if (tok.text.toLowerCase() !== tok.lemma.toLowerCase()) {
    h += `<div class="form-note">en el texto: <b>${esc(tok.text)}</b>${
      sep?.split && S.sepOk ? ` … <b>${esc(sep.particle_text)}</b>` : ""}</div>`;
  }

  const ex = e?.extra;
  if (ex?.silabas || ex?.hilfsverb) {
    const partes = (ex.silabas || "").split(",").map((x) => x.trim()).filter(Boolean);
    h += `<div class="forms">
      ${partes.map((p) => `<span>${esc(p)}</span>`).join("<i>·</i>")}
      ${ex.hilfsverb ? `<b>${esc(ex.hilfsverb)}</b>` : ""}
    </div>`;
  }

  // Bloque gramatical: sale de spaCy y las reglas, no del modelo. Solo se
  // muestra una vez que el diccionario confirmó que el verbo existe de verdad.
  if (sep?.is_separable && S.sepOk) {
    h += `<div class="sep">
      <div class="split"><b>${esc(sep.prefix)}</b>${esc(sep.stem)}</div>
      <div class="rule">${sep.split
        ? `Verbo separable, y acá está <b>partido</b>: la partícula «${esc(sep.prefix)}» se fue al final.`
        : `Verbo separable con la partícula <b>pegada</b> en esta forma.`}</div>
      <div class="rule" style="margin-top:6px">${md(sep.rule)}</div>
      ${sep.dual ? `<div class="warn">${ICONS.warn}<span>«${esc(sep.prefix)}» es de los ambiguos: ${esc(sep.dual)}</span></div>` : ""}
    </div>`;
  }

  if (o.loading) {
    h += `<div class="shimmer" style="width:80%"></div><div class="shimmer" style="width:55%"></div>`;
  } else if (e?.senses?.length) {
    h += `<div class="senses">` + e.senses.map((s) => `
      <button class="sense ${S.chosen === s.n ? "on" : ""}" data-n="${s.n}">
        ${S.chosen === s.n && o.ai?.sense_n === s.n ? `<div class="pick">${ICONS.check}aplica acá</div>` : ""}
        ${s.es.length ? `<div class="es">${ES}<span>${esc(s.es.join(", "))}</span></div>` : ""}
        <div class="de">${esc(s.de)}</div>
      </button>`).join("") + `</div>`;
  }

  if (o.ai === "cargando") {
    h += `<div class="ai"><div class="lbl">${ICONS.spark}En esta frase</div>
      <div class="shimmer" style="width:92%"></div><div class="shimmer" style="width:70%"></div></div>`;
  } else if (o.ai && !o.ai.error) {
    h += `<div class="ai">
      <div class="lbl">${ICONS.spark}En esta frase</div>
      ${o.ai.mode === "libre" && o.ai.es ? `<div class="why">${ES} <b>${esc(o.ai.es)}</b></div>` : ""}
      ${o.ai.literal ? `<div class="why" style="color:var(--ink-2)">${esc(o.ai.literal)}</div>` : ""}
      <div class="why">${esc(o.ai.porque || "")}</div>
      ${(o.ai.ejemplos_dict || []).map((x) =>
        `<div class="ex-de">${esc(x)}</div><div class="ex-src">${ICONS.book}del diccionario</div>`).join("")}
      ${o.ai.ejemplo_de ? `
        <div class="ex-de">${esc(o.ai.ejemplo_de)}</div>
        <div class="ex-es">${esc(o.ai.ejemplo_es || "")}</div>` : ""}
    </div>`;
  } else if (o.ai?.error) {
    h += `<div class="ai"><div class="lbl">${ICONS.spark}En esta frase</div>
      <div class="why" style="color:var(--ink-3)">${esc(o.ai.error)}</div></div>`;
  }

  h += `<div class="sentence-box" id="sbox">${esc(tok.sent || "")}</div>`;

  h += `<div class="actions">
      <button class="btn primary" id="save">${ICONS.bookmark}${S.savedWord ? "Guardada" : "Guardar"}</button>
      <button class="btn ok" id="known">${ICONS.check}Ya la sé</button>
    </div>
    <div class="actions">
      <button class="btn" id="tr">${ICONS.translate}Traducir la oración</button>
    </div>`;

  $("#sheetbody").innerHTML = h;

  $("#sheetbody").querySelectorAll(".sense").forEach((b) => b.onclick = () => {
    S.chosen = b.dataset.n; renderSheet(o);
  });
  $("#save").onclick = () => saveWord("aprendiendo", o.ai);
  $("#known").onclick = () => saveWord("sabida", o.ai);
  $("#tr").onclick = async (ev) => {
    const btn = ev.currentTarget;
    btn.innerHTML = `${ICONS.translate}Traduciendo…`;
    const { es } = await api("/translate", { sentence: tok.sent });
    $("#sbox").innerHTML = esc(tok.sent) +
      `<div class="es">${ES}<span>${esc(es || "—")}</span></div>`;
    btn.innerHTML = `${ICONS.translate}Traducir la oración`;
  };
}

async function saveWord(status, ai) {
  const tok = S.sel.tok;
  const sense = S.entry?.senses?.find((s) => s.n === S.chosen);
  const es = (ai && ai.es) || sense?.es?.join(", ") || "";
  await api("/vocab", {
    lemma: tok.lemma, form: tok.text, pos: tok.pos_es || tok.pos,
    article: tok.article || "", es, sense_n: S.chosen || "",
    sense_de: sense?.de || "", separable: (S.sepOk && tok.separable) || null,
    sentence: tok.sent, src_title: S.article?.title || "", src_url: S.article?.url || "",
    example_de: ai?.ejemplo_de || "", example_es: ai?.ejemplo_es || "", status,
  });
  S.statuses[tok.lemma] = status;
  document.querySelectorAll(".w").forEach((el) => {
    const t = S.article.tokens[+el.dataset.i];
    if (t && t.lemma === tok.lemma) {
      el.classList.remove("aprendiendo", "sabida"); el.classList.add(status);
    }
  });
  closeSheet();
}

/* ---------- guardadas ---------- */

async function loadSaved() {
  const { articles } = await api("/saved");
  $("#savedlist").innerHTML = articles.length ? articles.map((a, i) => `
    <div class="srow">
      <div class="main" data-i="${i}">
        <h3>${esc(a.title || a.url)}</h3>
        <div class="meta">
          <span class="src">${ICONS[a.topic] || ICONS.aktuell}${esc(a.source || "")}</span>
          ${rareOf(a.tenses).slice(0, 2).map((t) =>
            `<span class="tense">${ICONS.clock}${esc(S.tenseNames[t] || t)}</span>`).join("")}
        </div>
      </div>
      <button class="del" data-u="${esc(a.url)}" aria-label="Quitar">${ICONS.trash}</button>
    </div>`).join("")
    : `<div class="empty">${ICONS.bookmark}<div class="big">Sin notas guardadas</div></div>`;

  $("#savedlist").querySelectorAll(".main").forEach((el) => el.onclick = () =>
    openArticle(articles[+el.dataset.i]));
  $("#savedlist").querySelectorAll(".del").forEach((b) => b.onclick = async () => {
    await api("/saved?url=" + encodeURIComponent(b.dataset.u), null, "DELETE");
    loadSaved();
  });
}

/* ---------- vocabulario ---------- */

async function loadVocab() {
  const { words, stats } = await api("/vocab?status=" + S.filter);
  $("#vstats").innerHTML = `
    <div class="stat"><div class="n">${stats.total}</div><div class="l">guardadas</div></div>
    <div class="stat"><div class="n">${stats.aprendiendo}</div><div class="l">aprendiendo</div></div>
    <div class="stat"><div class="n">${stats.para_repasar}</div><div class="l">para repasar</div></div>`;
  $("#vlist").innerHTML = words.length ? words.map((w) => `
    <div class="vrow">
      <div class="main">
        <div class="de">${w.article ? `<span class="art">${esc(w.article)} </span>` : ""}${esc(w.lemma)}</div>
        <div class="es">${ES}<span>${esc(w.es || "—")}</span></div>
        ${w.sentence ? `<div class="ctx">${esc(w.sentence)}</div>` : ""}
      </div>
      <span class="badge ${w.status === "sabida" ? "sabida" : ""}">
        ${w.status === "sabida" ? ICONS.check + "sabida" : ICONS.layers + w.box}</span>
    </div>`).join("")
    : `<div class="empty">${ICONS.bookmark}<div class="big">Todavía no guardaste nada</div></div>`;
  $("#vfilter").querySelectorAll(".chip").forEach((c) => c.onclick = () => {
    S.filter = c.dataset.f;
    $("#vfilter").querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === c));
    loadVocab();
  });
}

/* ---------- repaso ---------- */

async function loadStudy() {
  const { words } = await api("/study");
  S.queue = words; S.qi = 0; S.revealed = false;
  renderStudy();
}

function renderStudy() {
  const w = S.queue[S.qi];
  if (!w) {
    $("#studybox").innerHTML = `<div class="empty">${ICONS.check}<div class="big">Nada para repasar ahora</div></div>`;
    return;
  }
  $("#studybox").innerHTML = `
    <div class="counter">${S.qi + 1} / ${S.queue.length}</div>
    <div class="flash">
      <div class="q">${w.article ? esc(w.article) + " " : ""}${esc(w.lemma)}</div>
      ${S.revealed ? `<div class="a">${ES}<span>${esc(w.es || "—")}</span></div>` : ""}
      ${w.sentence ? `<div class="ctx">${esc(w.sentence)}</div>` : ""}
      ${S.revealed && w.example_de ? `<div class="ex">${esc(w.example_de)}</div>` : ""}
    </div>
    ${S.revealed
      ? `<div class="actions">
           <button class="btn" id="bad">${ICONS.close}No me salió</button>
           <button class="btn ok" id="good">${ICONS.check}La sabía</button>
         </div>`
      : `<div class="actions"><button class="btn primary" id="rev">Mostrar</button></div>`}`;

  if (S.revealed) {
    $("#good").onclick = () => grade(w, true);
    $("#bad").onclick = () => grade(w, false);
  } else {
    $("#rev").onclick = () => { S.revealed = true; renderStudy(); };
  }
}

async function grade(w, ok) {
  await api("/study/review", { lemma: w.lemma, ok });
  S.qi++; S.revealed = false;
  renderStudy();
}

/* ---------- utilidades ---------- */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
// negritas de las reglas gramaticales: el texto es nuestro, no del usuario
function md(s) { return esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>"); }

/* ---------- red de seguridad ----------
   Si algo revienta al arrancar, antes quedaba una pantalla en blanco sin
   ninguna pista. Ahora se ve qué pasó y hay un botón para recargar salteando
   la caché, que es la causa más común (HTML viejo + script nuevo). */

function fatal(msg) {
  const box = document.createElement("div");
  box.className = "fatal";
  box.innerHTML = `<b>La app no pudo arrancar</b>
    <span>${esc(msg)}</span>
    <button id="hardreload">Recargar de cero</button>`;
  document.body.appendChild(box);
  box.querySelector("#hardreload").onclick = () => {
    location.replace(location.pathname + "?r=" + Date.now());
  };
}

window.addEventListener("error", (e) => {
  if (!document.querySelector(".fatal")) fatal(e.message || "Error desconocido");
});

try {
  api("/health").then((h) => {
    const d = $("#health");
    if (!d) return;
    d.className = "dot" + (h.ollama ? "" : " off");
    d.title = h.ollama ? "Ollama conectado" : "Ollama no responde";
  }).catch(() => {});
  loadTopics().catch((e) => fatal("No pude hablar con el servidor. ¿Está corriendo run.sh?"));
} catch (e) {
  fatal(e.message);
}
