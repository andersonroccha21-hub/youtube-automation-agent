/* No frontend dependencies: state is loaded from the local FastAPI server. */
"use strict";

const paths = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  play: '<path d="m9 5 11 7-11 7V5Z"/>',
  save: '<path d="M5 3h12l4 4v14H3V3h2Z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
  "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  sliders: '<path d="M4 6h16M4 12h16M4 18h16"/><path d="M8 3v6M16 9v6M10 15v6"/>',
  "chevron-down": '<path d="m6 9 6 6 6-6"/>',
  flask: '<path d="M9 3h6M10 3v6L4 19a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M7 15h10"/>',
  bolt: '<path d="m13 2-9 12h7l-1 8 10-12h-7l1-8Z"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  refresh: '<path d="M20 7a8 8 0 1 0 0 10M20 3v5h-5"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  search: '<circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
  script: '<path d="M14 3H5v18h14V8l-5-5Z"/><path d="M14 3v5h5M8 12h8M8 16h6"/>',
  scenes: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M9 9v11M15 9v11M8 4l3 5M15 4l3 5"/>',
  mic: '<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
  film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4M7 12h10"/>',
};
const stageDefinitions = [
  ["pesquisa_titulos", "Pesquisa e títulos", "search"], ["thumbnail", "Thumbnail", "image"],
  ["roteiro", "Roteiro", "script"], ["plano_visual", "Plano visual", "scenes"],
  ["narracao", "Narração", "mic"], ["imagens", "Imagens", "layers"], ["edicao", "Edição", "film"],
];
const labels = {pending:"Pendente", ready:"Pronta para continuar", running:"Rodando", pending_approval:"Aguardando aprovação", completed:"Concluída", failed:"Falha na execução", rejected:"Revisão solicitada", interrupted:"Execução interrompida"};
const state = {channels:[], channel:null, run:null, runs:[], reviewKey:null, selection:null, reviewer:"", actionPending:false, loading:false, detailKey:"", historyKey:"", pollTimer:null};
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[char]));
const svg = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.layers}</svg>`;

function icons(root = document) {
  root.querySelectorAll("[data-icon]:not([data-rendered])").forEach((element) => {
    element.innerHTML = svg(element.dataset.icon);
    element.dataset.rendered = "true";
  });
}
function connection(online) {
  const element = $("#connection");
  element.className = `connection ${online ? "connected" : "offline"}`;
  element.innerHTML = `<i></i>${online ? "Servidor local" : "Sem conexão"}`;
}
function alertMessage(message = "") {
  $("#alert").textContent = message;
  $("#alert").hidden = !message;
}
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {headers:{Accept:"application/json", ...(options.body ? {"Content-Type":"application/json"} : {})}, ...options});
  } catch (_) {
    connection(false);
    throw new Error("Não foi possível conectar ao servidor. Confira se o dashboard está rodando.");
  }
  connection(true);
  const data = await response.json();
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Confira os campos preenchidos e tente novamente.";
    throw new Error(detail);
  }
  return data;
}
const basePath = (run = state.run) => `/api/channels/${encodeURIComponent(run.channel_id)}/runs/${encodeURIComponent(run.id)}`;
function formatDate(value) { return new Intl.DateTimeFormat("pt-BR", {day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit"}).format(new Date(value)); }
function setStored(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* Optional preference. */ } }
function stored(key) { try { return localStorage.getItem(key); } catch (_) { return null; } }

function renderStages(run) {
  $("#stages").innerHTML = stageDefinitions.map(([id, label, icon], index) => {
    const step = run?.stages.find((stage) => stage.id === id) || {status:"pending", has_output:false};
    return `<li class="stage" data-status="${step.status}"><button class="stage-button" data-stage="${id}" ${step.has_output ? "" : "disabled"} aria-label="${esc(label)}: ${labels[step.status]}. ${step.has_output ? "Ver resultado" : "Sem resultado ainda"}"><span class="stage-top"><span class="stage-icon">${svg(step.status === "completed" ? "check-circle" : icon)}</span><span class="stage-step">${String(index + 1).padStart(2,"0")}</span></span><span class="stage-name">${esc(label)}</span><span class="stage-code">${id}</span><span class="stage-state">${labels[step.status]}</span></button></li>`;
  }).join("");
}

function renderChannel() {
  const channel = state.channels.find((item) => item.id === state.channel);
  $("#channel-description").textContent = channel ? `${channel.language} · ${channel.niche}` : "Adicione um config.yaml válido em channels/ para começar.";
  const demo = $("input[name=mode]:checked").value === "demo";
  $("#mode-description").textContent = demo ? "Teste o fluxo com conteúdo sintético, sem chamadas pagas." : "Utiliza os provedores, fontes e voz configurados no YAML do canal.";
  const warning = !demo && channel && !channel.production_ready;
  $("#readiness").hidden = !warning;
  $("#readiness").textContent = warning ? `Produção ainda não configurada: ${channel.production_error}` : "";
  $("#start-button").disabled = !channel || state.loading || warning;
}

function renderHistory() {
  const key = JSON.stringify([state.channel, state.runs, state.run?.id]);
  if (state.historyKey === key) return;
  state.historyKey = key;
  $("#run-count").textContent = state.runs.length;
  $("#history-list").innerHTML = state.runs.length ? state.runs.map((run) =>
    `<button type="button" class="history-row ${state.run?.id === run.id ? "selected" : ""}" data-run="${esc(run.id)}"><span class="history-icon">${svg(run.status === "completed" ? "check-circle" : "film")}</span><span class="history-info"><strong>${esc(run.topic)}</strong><small>${esc(formatDate(run.created_at))} · ${run.demo ? "Demonstração" : "Produção"} · ${run.completed_stages}/7 etapas</small></span><span class="status status-${run.status}">${labels[run.status] || run.status}</span></button>`
  ).join("") : '<p class="history-empty">Nenhuma execução neste canal. Sua próxima produção pode começar agora.</p>';
}

function renderReview(run) {
  const review = run.review;
  const key = `${run.id}:${review.stage}:${review.artifact_digest}`;
  if (state.reviewKey === key) { reviewButtons(); return; }
  state.reviewKey = key;
  state.selection = null;
  const thumbnails = review.stage === "thumbnail";
  let content;
  if (review.candidates.length) {
    content = `<div class="candidate-list ${thumbnails ? "thumb-options" : ""}">${review.candidates.map((candidate, index) =>
      `<label class="candidate ${thumbnails ? "thumb-option" : ""}">${thumbnails ? `<img src="${esc(candidate.image_url)}" alt="Thumbnail candidata ${index + 1}, ID ${esc(candidate.id)}" loading="lazy">` : ""}<span class="candidate-header"><input type="radio" name="candidate" value="${esc(candidate.id)}"><strong>${esc(thumbnails ? `Variação ${index + 1}` : candidate.title)}</strong></span>${thumbnails ? "" : `<p>${esc(candidate.angle)}</p><p>${esc(candidate.rationale)}</p>`}<span class="candidate-code">${esc(candidate.id)}</span></label>`
    ).join("")}</div>`;
  } else if (review.stage === "roteiro") {
    content = `<div class="review-content">${review.content.sections.map((section) => `<strong>${esc(section.heading)}</strong><p>${esc(section.narration)}</p>`).join("")}</div>`;
  } else {
    content = `<pre class="review-content">${esc(JSON.stringify(review.content, null, 2))}</pre>`;
  }
  if (review.media?.length) {
    content += `<div class="review-media">${review.media.map((media) => {
      if (media.kind === "audio") return `<audio controls preload="metadata" src="${esc(media.url)}" aria-label="Áudio para revisão"></audio>`;
      if (media.kind === "video") return `<video controls preload="metadata" src="${esc(media.url)}" aria-label="Vídeo para revisão"></video>`;
      if (media.kind === "image") return `<img src="${esc(media.url)}" alt="Imagem para revisão" loading="lazy">`;
      return "";
    }).join("")}</div>`;
  }
  const sources = (review.sources || []).filter((source) => /^https?:\/\//i.test(source.url));
  $("#review").innerHTML = `<div class="review-body"><div class="review-notice">${thumbnails ? "Revise as imagens e selecione a thumbnail que deseja usar." : review.stage === "pesquisa_titulos" ? "Revise as propostas e escolha o título da sua produção." : `Revise o resultado de ${esc(review.label)} antes de continuar.`} A próxima etapa começa após sua aprovação.</div>${review.summary ? `<p class="review-summary">${esc(review.summary)}</p>` : ""}${content}${sources.length ? `<div class="source-links">${sources.map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.title)}</a>`).join("")}</div>` : ""}<div class="review-controls"><label for="reviewer">Seu nome como revisor</label><input id="reviewer" type="text" maxlength="200" autocomplete="name" placeholder="Nome de quem revisou" value="${esc(state.reviewer)}"><div class="review-feedback"><label for="feedback">Ajustes solicitados <span class="muted">(para revisar ou rejeitar)</span></label><textarea id="feedback" rows="2" maxlength="4000" placeholder="O que você gostaria de ajustar?"></textarea></div><div class="review-buttons"><button type="button" class="button button-secondary" id="revise-button">Solicitar revisão</button><button type="button" class="button button-primary" id="approve-button">${svg("check")}Aprovar e continuar</button></div></div></div>`;
  reviewButtons();
}

function reviewButtons() {
  const approve = $("#approve-button"), revise = $("#revise-button");
  if (!approve || !state.run?.review) return;
  const needsSelection = ["pesquisa_titulos", "thumbnail"].includes(state.run.review.stage);
  const blocked = state.actionPending || state.run.busy;
  approve.disabled = blocked || !$("#reviewer").value.trim() || (needsSelection && !state.selection);
  revise.disabled = blocked || !$("#feedback").value.trim();
}

function renderRun(run) {
  state.run = run;
  const key = JSON.stringify(run);
  if (state.detailKey === key) { reviewButtons(); return; }
  state.detailKey = key;
  renderStages(run);
  $("#run-heading").textContent = run ? run.topic : "Nenhuma execução selecionada";
  $("#run-subtitle").textContent = run ? `${run.channel_name} · ${run.demo ? "Demonstração" : "Produção"} · ${formatDate(run.created_at)}` : "Inicie um vídeo ou selecione uma execução no histórico.";
  $("#run-status").className = `status status-${run?.status || "pending"}`;
  $("#run-status").textContent = run ? (run.busy && run.status === "ready" ? "Na fila" : labels[run.status]) : "Pronto para começar";
  $("#progress-label").textContent = `${run?.completed_stages || 0} de 7 etapas concluídas`;
  $("#progress-percent").textContent = `${run?.progress || 0}%`;
  $("#progress-fill").style.width = `${run?.progress || 0}%`;
  $("#progress").setAttribute("aria-valuenow", run?.progress || 0);
  $("#mode-badge").hidden = !run;
  $("#mode-badge").textContent = run?.demo ? "DEMO" : "PRODUÇÃO";
  $("#empty-state").hidden = !!run;
  $("#review").hidden = !run?.review;
  $("#video-result").hidden = !run?.video;
  $("#running-state").hidden = !run || !!run.review || !!run.video;
  if (!run) {
    $("#production-heading").textContent = "Sua próxima produção começa aqui";
    state.reviewKey = null;
    return;
  }
  if (run.review) {
    $("#production-heading").textContent = `Aprovar ${run.review.stage === "pesquisa_titulos" ? "título" : run.review.label.toLocaleLowerCase("pt-BR")}`;
    renderReview(run);
  } else {
    state.reviewKey = null;
    $("#review").innerHTML = "";
    $("#production-heading").textContent = run.video ? "Seu vídeo ficou pronto" : "Sua produção está em andamento";
    const failed = ["failed", "rejected", "interrupted"].includes(run.status);
    $("#working-title").textContent = failed ? labels[run.status] : run.current ? `${stageDefinitions.find((item) => item[0] === run.current)[1]} em andamento` : "Sua execução está na fila";
    $("#working-description").textContent = run.error || (run.status === "rejected" ? "A etapa foi rejeitada. Solicite uma nova versão para continuar." : run.status === "interrupted" ? "O servidor foi reiniciado ou a execução foi interrompida. Você pode retomar do último checkpoint." : "As skills trabalham em sequência. Você pode acompanhar o progresso por aqui.");
    $("#run-actions").innerHTML = !run.busy && ["ready", "failed", "interrupted"].includes(run.status) ? '<button class="button button-secondary" data-action="resume">Retomar execução</button>' : "";
    if (failed && run.current && !run.busy) {
      $("#run-actions").innerHTML += '<div class="w-full"><label for="failed-feedback" class="muted small">Instruções para refazer a etapa</label><textarea id="failed-feedback" maxlength="4000" placeholder="Descreva os ajustes necessários"></textarea><button class="button button-secondary" data-action="revise-failed">Refazer etapa</button></div>';
    }
  }
  if (run.video) {
    const video = $("#final-video");
    if (video.getAttribute("src") !== run.video.url) video.src = run.video.url;
    $("#video-title").textContent = run.selected_title || run.topic;
    $("#video-details").textContent = `${run.video.width} × ${run.video.height} · ${run.video.duration_seconds.toFixed(1)} s${run.demo ? " · Conteúdo sintético de demonstração" : ""}`;
    $("#video-download").href = run.video.url;
    $("#video-download").download = run.demo ? "final.demo.mp4" : "final.mp4";
  } else {
    const video = $("#final-video");
    if (video.hasAttribute("src")) { video.pause(); video.removeAttribute("src"); video.load(); }
  }
  renderHistory();
}

async function loadRun(id) {
  const channel = state.channel;
  const run = await api(`/api/channels/${encodeURIComponent(channel)}/runs/${encodeURIComponent(id)}`);
  if (state.channel !== channel || state.run?.id !== id) return;
  renderRun(run);
}
async function chooseRun(id) {
  state.run = {id, channel_id:state.channel};
  state.detailKey = "";
  state.reviewKey = null;
  setStored(`darklab-run:${state.channel}`, id);
  await loadRun(id);
}
async function loadHistory() {
  if (!state.channel) return;
  const channel = state.channel;
  const result = await api(`/api/channels/${encodeURIComponent(channel)}/runs`);
  if (channel !== state.channel) return;
  state.runs = result.runs;
  renderHistory();
  if (!state.run && result.runs.length) {
    const remembered = stored(`darklab-run:${channel}`);
    await chooseRun(result.runs.find((run) => run.id === remembered)?.id || result.runs[0].id);
  }
}
async function chooseChannel(id) {
  state.channel = id;
  state.runs = [];
  state.detailKey = "";
  renderRun(null);
  renderHistory();
  renderChannel();
  setStored("darklab-channel", id);
  alertMessage();
  await loadHistory();
}

async function action(operation) {
  if (state.actionPending) return;
  state.actionPending = true;
  alertMessage();
  reviewButtons();
  try { await operation(); }
  catch (error) { alertMessage(error.message); }
  finally { state.actionPending = false; reviewButtons(); }
}
async function approve() {
  const run = state.run;
  const review = run.review;
  const body = {stage:review.stage, reviewer:$("#reviewer").value.trim(), selected_id:state.selection, artifact_digest:review.artifact_digest};
  await api(`${basePath(run)}/approve`, {method:"POST", body:JSON.stringify(body)});
  await loadRun(run.id);
  await loadHistory();
}
async function revise(stage, feedback) {
  if (!feedback.trim()) throw new Error("Descreva os ajustes para gerar uma nova versão.");
  const run = state.run;
  await api(`${basePath(run)}/revise`, {method:"POST", body:JSON.stringify({stage, feedback:feedback.trim()})});
  await loadRun(run.id);
  await loadHistory();
}
async function showCheckpoint(stage) {
  const data = await api(`${basePath()}/checkpoints/${stage}`);
  const field = {pesquisa_titulos:"research",thumbnail:"thumbnail",roteiro:"script",plano_visual:"visual_plan",narracao:"narration",imagens:"assets",edicao:"video"}[stage];
  $("#checkpoint-title").textContent = stageDefinitions.find((item) => item[0] === stage)[1];
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(data[field], null, 2);
  $("#checkpoint-content").replaceChildren(pre);
  $("#checkpoint-dialog").showModal();
}

$("#channel").addEventListener("change", (event) => action(() => chooseChannel(event.target.value)));
document.querySelectorAll("input[name=mode]").forEach((input) => input.addEventListener("change", renderChannel));
$("#new-run-form").addEventListener("submit", (event) => {
  event.preventDefault();
  action(async () => {
    const topic = $("#topic").value.trim();
    if (!topic) throw new Error("Defina o tema do vídeo antes de iniciar.");
    state.loading = true;
    renderChannel();
    try {
      const run = await api("/api/runs", {method:"POST", body:JSON.stringify({channel_id:state.channel, topic, demo:$("input[name=mode]:checked").value === "demo"})});
      await chooseRun(run.id);
      await loadHistory();
    } finally { state.loading = false; renderChannel(); }
  });
});
$("#review").addEventListener("change", (event) => {
  if (event.target.name === "candidate") state.selection = event.target.value;
  reviewButtons();
});
$("#review").addEventListener("input", (event) => {
  if (event.target.id === "reviewer") state.reviewer = event.target.value;
  reviewButtons();
});
$("#review").addEventListener("click", (event) => {
  if (event.target.closest("#approve-button")) action(approve);
  if (event.target.closest("#revise-button")) action(() => revise(state.run.review.stage, $("#feedback").value));
});
$("#history-list").addEventListener("click", (event) => {
  const row = event.target.closest("[data-run]");
  if (row) action(() => chooseRun(row.dataset.run));
});
$("#stages").addEventListener("click", (event) => {
  const button = event.target.closest("[data-stage]");
  if (button && !button.disabled) action(() => showCheckpoint(button.dataset.stage));
});
$("#run-actions").addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  action(async () => {
    if (button.dataset.action === "revise-failed") return revise(state.run.current, $("#failed-feedback").value);
    await api(`${basePath()}/resume`, {method:"POST"});
    await loadRun(state.run.id);
  });
});
$("#refresh").addEventListener("click", () => action(async () => {
  await loadHistory();
  if (state.run) await loadRun(state.run.id);
}));
$("#close-dialog").addEventListener("click", () => $("#checkpoint-dialog").close());

async function poll() {
  try {
    if (!state.actionPending && !document.hidden) {
      await loadHistory();
      if (state.run) await loadRun(state.run.id);
    }
  } catch (error) { alertMessage(error.message); }
  state.pollTimer = setTimeout(poll, 1800);
}
async function init() {
  icons();
  renderStages(null);
  try {
    const data = await api("/api/channels");
    state.channels = data.channels;
    $("#channel-count").textContent = data.channels.length;
    $("#channel").innerHTML = data.channels.length ? data.channels.map((channel) => `<option value="${esc(channel.id)}">${esc(channel.name)}</option>`).join("") : '<option value="">Nenhum canal configurado</option>';
    if (data.errors.length) {
      $("#config-errors").hidden = false;
      $("#config-errors").textContent = data.errors.map((error) => `${error.path}: ${error.error}`).join(" · ");
    }
    const initial = data.channels.find((channel) => channel.id === stored("darklab-channel"))?.id || data.channels[0]?.id;
    if (initial) { $("#channel").value = initial; await chooseChannel(initial); }
    else renderChannel();
  } catch (error) { alertMessage(error.message); renderChannel(); }
  state.pollTimer = setTimeout(poll, 1800);
}
init();
