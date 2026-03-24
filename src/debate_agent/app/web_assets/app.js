const state = {
  sessions: [],
  currentSession: null,
  currentOpeningFramework: null,
  lastOpeningResult: null,
  lastTurnResult: null,
  lastCoachResult: null,
  lastClosingResult: null,
  theme: "light",
  openingRevealTimer: null,
  openingRevealBriefId: null,
  frameworkRevealRequestId: 0,
  openingStreamAbortController: null,
  openingStreamRequestId: 0,
  openingStreamLastPaintAt: 0,
};

const THEME_STORAGE_KEY = "debate-project-theme";

const elements = {
  homeScreen: document.getElementById("homeScreen"),
  workspaceScreen: document.getElementById("workspaceScreen"),
  openingWorkbench: document.getElementById("openingWorkbench"),
  debateWorkbench: document.getElementById("debateWorkbench"),
  introView: document.getElementById("introView"),
  launchView: document.getElementById("launchView"),
  themeToggleBtn: document.getElementById("themeToggleBtn"),
  healthBadge: document.getElementById("healthBadge"),
  startTrainingBtn: document.getElementById("startTrainingBtn"),
  backToIntroBtn: document.getElementById("backToIntroBtn"),
  newSessionForm: document.getElementById("newSessionForm"),
  topicInput: document.getElementById("topicInput"),
  userSideInput: document.getElementById("userSideInput"),
  agentSideInput: document.getElementById("agentSideInput"),
  coachModeInput: document.getElementById("coachModeInput"),
  closingSideInput: document.getElementById("closingSideInput"),
  webSearchInput: document.getElementById("webSearchInput"),
  sessionList: document.getElementById("sessionList"),
  refreshSessionsBtn: document.getElementById("refreshSessionsBtn"),
  backHomeBtn: document.getElementById("backHomeBtn"),
  workspaceModeTitle: document.getElementById("workspaceModeTitle"),
  workspaceModeDescription: document.getElementById("workspaceModeDescription"),
  enterDebateBtn: document.getElementById("enterDebateBtn"),
  returnOpeningBtn: document.getElementById("returnOpeningBtn"),
  sessionTitle: document.getElementById("sessionTitle"),
  sessionMeta: document.getElementById("sessionMeta"),
  sessionTopicInput: document.getElementById("sessionTopicInput"),
  sessionUserSideInput: document.getElementById("sessionUserSideInput"),
  sessionAgentSideInput: document.getElementById("sessionAgentSideInput"),
  updateMetadataBtn: document.getElementById("updateMetadataBtn"),
  openingBriefInput: document.getElementById("openingBriefInput"),
  openingBriefLabel: document.getElementById("openingBriefLabel"),
  openingDiagnosticPanel: document.getElementById("openingDiagnosticPanel"),
  openingStatus: document.getElementById("openingStatus"),
  openingDurationSelect: document.getElementById("openingDurationSelect"),
  generateFrameworkBtn: document.getElementById("generateFrameworkBtn"),
  generateOpeningBtn: document.getElementById("generateOpeningBtn"),
  saveOpeningBtn: document.getElementById("saveOpeningBtn"),
  coachOpeningBtn: document.getElementById("coachOpeningBtn"),
  turnInput: document.getElementById("turnInput"),
  sendTurnBtn: document.getElementById("sendTurnBtn"),
  coachBtn: document.getElementById("coachBtn"),
  closingMeBtn: document.getElementById("closingMeBtn"),
  closingOpponentBtn: document.getElementById("closingOpponentBtn"),
  coachModeBadge: document.getElementById("coachModeBadge"),
  webSearchBadge: document.getElementById("webSearchBadge"),
  turnCountLabel: document.getElementById("turnCountLabel"),
  timeline: document.getElementById("timeline"),
  coachModeSelect: document.getElementById("coachModeSelect"),
  defaultClosingSelect: document.getElementById("defaultClosingSelect"),
  webSearchToggle: document.getElementById("webSearchToggle"),
  updateOptionsBtn: document.getElementById("updateOptionsBtn"),
  clashBoard: document.getElementById("clashBoard"),
  coachOutput: document.getElementById("coachOutput"),
  closingOutput: document.getElementById("closingOutput"),
  evidenceOutput: document.getElementById("evidenceOutput"),
  toast: document.getElementById("toast"),
};

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    let message = "请求失败";
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch (_error) {
      message = response.statusText || message;
    }
    throw new Error(message);
  }
  return response.json();
}

async function consumeEventStream(url, options, onEvent) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(options?.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    let message = "请求失败";
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch (_error) {
      message = response.statusText || message;
    }
    throw new Error(message);
  }
  if (!response.body) {
    throw new Error("当前浏览器不支持流式响应读取。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const dispatchRawEvent = async (rawEvent) => {
    const normalizedEvent = String(rawEvent || "").trim();
    if (!normalizedEvent || normalizedEvent.startsWith(":")) {
      return;
    }

    let eventName = "message";
    const dataLines = [];
    normalizedEvent.split("\n").forEach((line) => {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
        return;
      }
      if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    });

    const payloadText = dataLines.join("\n");
    if (!payloadText) {
      await onEvent(eventName, {});
      return;
    }

    let payload = {};
    try {
      payload = JSON.parse(payloadText);
    } catch (_error) {
      throw new Error("收到无法解析的流式事件。\n请检查后端 SSE 数据格式。");
    }
    await onEvent(eventName, payload);
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      await dispatchRawEvent(rawEvent);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) {
      if (buffer.trim()) {
        await dispatchRawEvent(buffer);
      }
      break;
    }
  }
}

function setButtonBusy(button, busyText, isBusy) {
  if (!button) {
    return;
  }
  if (!button.dataset.idleText) {
    button.dataset.idleText = button.textContent || "";
  }
  button.disabled = isBusy;
  button.textContent = isBusy ? busyText : button.dataset.idleText;
}

function summarizeArgumentCard(card, index) {
  const text = String(card?.claim || "").trim();
  if (!text) {
    return `论点 ${index + 1}`;
  }
  return text.length > 18 ? `${text.slice(0, 18)}…` : text;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, 2600);
}

function formatRole(role) {
  if (role === "user") return "你";
  if (role === "opponent") return "对手";
  return role || "未知";
}

function formatCoachMode(mode) {
  return mode === "auto" ? "自动" : "按需";
}

function formatSwitch(enabled) {
  return enabled ? "开启" : "关闭";
}

function getWorkspacePhase(session) {
  return session?.current_phase || "opening";
}

function isOpeningPhase(session) {
  return getWorkspacePhase(session) === "opening";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function lastItem(items) {
  return Array.isArray(items) && items.length ? items[items.length - 1] : null;
}

function setOpeningStatus(message, mode = "pending") {
  if (!message) {
    elements.openingStatus.textContent = "";
    elements.openingStatus.className = "opening-status hidden";
    return;
  }
  elements.openingStatus.textContent = message;
  elements.openingStatus.className = `opening-status ${mode}`;
}

function clearOpeningReveal() {
  if (state.openingRevealTimer) {
    window.clearInterval(state.openingRevealTimer);
    state.openingRevealTimer = null;
  }
  state.openingRevealBriefId = null;
}

function cancelFrameworkReveal() {
  state.frameworkRevealRequestId += 1;
}

function resetTransientResults() {
  state.lastOpeningResult = null;
  state.lastTurnResult = null;
  state.lastCoachResult = null;
  state.lastClosingResult = null;
}

function abortOpeningStream() {
  if (state.openingStreamAbortController) {
    state.openingStreamAbortController.abort();
    state.openingStreamAbortController = null;
  }
  state.openingStreamRequestId += 1;
  state.openingStreamLastPaintAt = 0;
}

function isAbortError(error) {
  return error?.name === "AbortError";
}

function waitForNextPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
}

function waitForDelay(delayMs) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, delayMs);
  });
}

async function flushOpeningStream(force = false) {
  const openingBrief = state.lastOpeningResult?.opening_brief;
  if (!openingBrief) {
    return;
  }

  const now = window.performance.now();
  if (!force && now - state.openingStreamLastPaintAt < 32) {
    return;
  }

  elements.openingBriefInput.value = openingBrief.spoken_text || "";
  elements.openingBriefInput.scrollTop = elements.openingBriefInput.scrollHeight;
  state.openingStreamLastPaintAt = now;
  await waitForNextPaint();
}

function animateOpeningReveal(openingBrief) {
  clearOpeningReveal();
  const fullText = String(openingBrief?.spoken_text || "");
  if (!fullText) {
    elements.openingBriefInput.value = "";
    return;
  }

  const briefId = openingBrief.brief_id;
  state.openingRevealBriefId = briefId;
  elements.openingBriefInput.value = "";
  let currentIndex = 0;
  const step = Math.max(18, Math.floor(fullText.length / 55));
  state.openingRevealTimer = window.setInterval(() => {
    if (state.openingRevealBriefId !== briefId) {
      clearOpeningReveal();
      return;
    }
    currentIndex = Math.min(fullText.length, currentIndex + step);
    elements.openingBriefInput.value = fullText.slice(0, currentIndex);
    if (currentIndex >= fullText.length) {
      clearOpeningReveal();
      setOpeningStatus(`一辩稿已生成完成，当前为 ${openingBrief.target_duration_minutes || 3} 分钟成稿。`, "success");
    }
  }, 28);
}

function buildEmptyFramework() {
  return {
    judge_standard: "",
    framework_summary: "",
    argument_cards: Array.from({ length: 3 }, () => ({
      claim: "",
      data_support: "",
      academic_support: "",
      scenario_support: "",
    })),
  };
}

function normalizeFrameworkForEditor(framework) {
  const base = framework || buildEmptyFramework();
  const cards = Array.isArray(base.argument_cards) ? [...base.argument_cards] : [];
  while (cards.length < 3) {
    cards.push({
      claim: "",
      data_support: "",
      academic_support: "",
      scenario_support: "",
    });
  }
  return {
    judge_standard: base.judge_standard || "",
    framework_summary: base.framework_summary || "",
    argument_cards: cards,
  };
}

function renderOpeningFramework(framework, openingBrief = null) {
  const normalizedFramework = normalizeFrameworkForEditor(framework);
  const cards = normalizedFramework.argument_cards
    .map(
      (card, index) => `
        <article class="opening-framework-card">
          <div class="opening-framework-head">
            <strong>论点 ${index + 1}</strong>
          </div>
          <label class="framework-editor-field">
            <span>论点内容</span>
            <textarea data-framework-card="${index}" data-framework-field="claim" rows="3" placeholder="用一句完整命题说明本论点到底证明什么。">${escapeHtml(card.claim || "")}</textarea>
          </label>
          <div class="framework-editor-inline">
            <label class="framework-editor-field">
              <span>数据</span>
              <textarea data-framework-card="${index}" data-framework-field="data_support" rows="4" placeholder="优先放可量化证据；没有就明确写证据缺口。">${escapeHtml(card.data_support || "")}</textarea>
            </label>
            <label class="framework-editor-field">
              <span>学理</span>
              <textarea data-framework-card="${index}" data-framework-field="academic_support" rows="4" placeholder="解释机制链条、理论依据和因果关系。">${escapeHtml(card.academic_support || "")}</textarea>
            </label>
          </div>
          <label class="framework-editor-field">
            <span>情景</span>
            <textarea data-framework-card="${index}" data-framework-field="scenario_support" rows="4" placeholder="给出具体、可感的生活或制度场景。">${escapeHtml(card.scenario_support || "")}</textarea>
          </label>
        </article>
      `,
    )
    .join("");

  elements.openingDiagnosticPanel.innerHTML = `
    <div class="opening-framework-editor">
      <article class="opening-framework-summary">
        <label class="framework-editor-field">
          <span>判断标准</span>
          <textarea data-framework-field="judge_standard" rows="4" placeholder="先写本题专属判断标准，不要把它写成论点一。">${escapeHtml(normalizedFramework.judge_standard || "")}</textarea>
        </label>
        <label class="framework-editor-field">
          <span>胜利路径</span>
          <textarea data-framework-field="framework_summary" rows="3" placeholder="概括本方如何通过 2 到 3 个内容论点赢下比赛。">${escapeHtml(normalizedFramework.framework_summary || "")}</textarea>
        </label>
      </article>
      <div class="opening-framework-cards">
        ${cards}
      </div>
    </div>
  `;
}

async function revealFrameworkField(selector, value, requestId) {
  const target = elements.openingDiagnosticPanel.querySelector(selector);
  if (!target) {
    return requestId === state.frameworkRevealRequestId;
  }

  const text = String(value || "");
  target.value = "";
  if (!text) {
    await waitForNextPaint();
    return requestId === state.frameworkRevealRequestId;
  }

  let currentIndex = 0;
  const step = Math.max(6, Math.ceil(text.length / 24));
  while (currentIndex < text.length) {
    if (requestId !== state.frameworkRevealRequestId) {
      return false;
    }
    currentIndex = Math.min(text.length, currentIndex + step);
    target.value = text.slice(0, currentIndex);
    target.scrollTop = target.scrollHeight;
    await waitForNextPaint();
    await waitForDelay(14);
  }
  return requestId === state.frameworkRevealRequestId;
}

async function streamFrameworkIntoEditor(framework, requestId) {
  const normalizedFramework = normalizeFrameworkForEditor(framework);
  renderOpeningFramework(buildEmptyFramework(), null);
  await waitForNextPaint();

  const summaryReady = await revealFrameworkField('[data-framework-field="judge_standard"]', normalizedFramework.judge_standard, requestId);
  if (!summaryReady) {
    return false;
  }

  const pathReady = await revealFrameworkField('[data-framework-field="framework_summary"]', normalizedFramework.framework_summary, requestId);
  if (!pathReady) {
    return false;
  }

  for (let index = 0; index < normalizedFramework.argument_cards.length; index += 1) {
    const card = normalizedFramework.argument_cards[index];
    const claimReady = await revealFrameworkField(`[data-framework-card="${index}"][data-framework-field="claim"]`, card.claim, requestId);
    if (!claimReady) {
      return false;
    }
    const dataReady = await revealFrameworkField(`[data-framework-card="${index}"][data-framework-field="data_support"]`, card.data_support, requestId);
    if (!dataReady) {
      return false;
    }
    const academicReady = await revealFrameworkField(`[data-framework-card="${index}"][data-framework-field="academic_support"]`, card.academic_support, requestId);
    if (!academicReady) {
      return false;
    }
    const scenarioReady = await revealFrameworkField(`[data-framework-card="${index}"][data-framework-field="scenario_support"]`, card.scenario_support, requestId);
    if (!scenarioReady) {
      return false;
    }
  }

  return requestId === state.frameworkRevealRequestId;
}

function collectOpeningFramework() {
  const judgeStandardInput = elements.openingDiagnosticPanel.querySelector('[data-framework-field="judge_standard"]');
  const summaryInput = elements.openingDiagnosticPanel.querySelector('[data-framework-field="framework_summary"]');
  const judgeStandard = judgeStandardInput ? judgeStandardInput.value.trim() : "";
  const frameworkSummary = summaryInput ? summaryInput.value.trim() : "";
  const cards = Array.from(elements.openingDiagnosticPanel.querySelectorAll('[data-framework-card]'))
    .reduce((result, field) => {
      const index = Number.parseInt(field.dataset.frameworkCard || "0", 10);
      const key = field.dataset.frameworkField;
      if (!result[index]) {
        result[index] = {
          claim: "",
          data_support: "",
          academic_support: "",
          scenario_support: "",
        };
      }
      if (key) {
        result[index][key] = field.value.trim();
      }
      return result;
    }, [])
    .filter((card) => card && Object.values(card).some((value) => String(value || "").trim()));

  if (!judgeStandard && !frameworkSummary && !cards.length) {
    return null;
  }

  return {
    judge_standard: judgeStandard,
    framework_summary: frameworkSummary,
    argument_cards: cards,
  };
}

function formatDate(timestamp) {
  if (!timestamp) return "未知时间";
  return new Date(timestamp * 1000).toLocaleString("zh-CN");
}

function getPreferredTheme() {
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  if (storedTheme === "light" || storedTheme === "dark") {
    return storedTheme;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  document.body.dataset.theme = theme;
  window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  elements.themeToggleBtn.textContent = theme === "dark" ? "切换亮色" : "切换暗色";
  elements.themeToggleBtn.setAttribute("aria-label", elements.themeToggleBtn.textContent);
}

function toggleTheme() {
  applyTheme(state.theme === "dark" ? "light" : "dark");
}

function showHomeScreen() {
  elements.homeScreen.classList.remove("hidden");
  elements.workspaceScreen.classList.add("hidden");
}

function showWorkspaceScreen() {
  elements.homeScreen.classList.add("hidden");
  elements.workspaceScreen.classList.remove("hidden");
}

function showIntroView() {
  elements.introView.classList.remove("hidden");
  elements.launchView.classList.add("hidden");
}

function showLaunchView() {
  elements.introView.classList.add("hidden");
  elements.launchView.classList.remove("hidden");
}

function renderSessionList() {
  if (!state.sessions.length) {
    elements.sessionList.innerHTML = '<div class="empty-state">还没有历史会话，先从上面的辩题入口开始。</div>';
    return;
  }

  elements.sessionList.innerHTML = state.sessions
    .map((session) => {
      const isActive = state.currentSession && state.currentSession.session_id === session.session_id;
      return `
        <article class="session-item ${isActive ? "active" : ""}" data-session-id="${session.session_id}">
          <button class="session-open" type="button" data-session-id="${session.session_id}">
            <strong>${escapeHtml(session.topic)}</strong>
            <p>${escapeHtml(session.user_side)} vs ${escapeHtml(session.agent_side)}</p>
            <div class="session-item-meta">
              <span class="badge">${session.turn_count} 回合</span>
              <span class="badge">教练：${formatCoachMode(session.coach_mode)}</span>
              <span class="badge">检索：${formatSwitch(session.web_search_enabled)}</span>
            </div>
            <p class="muted">点击进入工作台 · 更新于 ${formatDate(session.updated_at)}</p>
          </button>
          <button class="session-delete" type="button" data-session-id="${session.session_id}">删除</button>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll(".session-open").forEach((button) => {
    button.addEventListener("click", async () => {
      await loadSession(button.dataset.sessionId);
    });
  });
  document.querySelectorAll(".session-delete").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteSession(button.dataset.sessionId);
    });
  });
}

function renderTimeline(session) {
  if (!session.turns.length) {
    elements.timeline.innerHTML = '<div class="empty-state">输入你的第一轮发言，时间线会在这里展开。</div>';
    return;
  }

  elements.timeline.innerHTML = session.turns
    .map(
      (turn) => `
        <article class="timeline-item ${turn.speaker_role}">
          <div class="role">${formatRole(turn.speaker_role)}</div>
          <p>${escapeHtml(turn.raw_text)}</p>
        </article>
      `,
    )
    .join("");
}

function renderClashBoard(session) {
  if (!session.clash_points.length) {
    elements.clashBoard.innerHTML = '<div class="empty-state">当前还没有 clash。</div>';
    return;
  }
  elements.clashBoard.innerHTML = session.clash_points
    .map(
      (clash) => `
        <article class="stack-card">
          <strong>${escapeHtml(clash.topic_label)}</strong>
          <p>${escapeHtml(clash.summary)}</p>
          <p class="muted">待追问：${escapeHtml((clash.open_questions || []).join("；") || "暂无")}</p>
        </article>
      `,
    )
    .join("");
}

function renderCoach(session) {
  const report = state.lastCoachResult?.coach_report || lastItem(session.coach_reports);
  if (!report) {
    elements.coachOutput.innerHTML = '<div class="empty-state">需要时点击“生成教练反馈”。</div>';
    return;
  }
  elements.coachOutput.innerHTML = `
    <article class="stack-card">
      <strong>${escapeHtml(report.round_verdict)}</strong>
      <p>改进动作：${escapeHtml((report.improvement_actions || []).join("；") || "暂无")}</p>
      <p class="muted">逻辑问题：${escapeHtml((report.logical_fallacies || []).join("；") || "暂无")}</p>
    </article>
  `;
}

function renderOpeningBrief(session) {
  const openingBrief = state.lastOpeningResult?.opening_brief || lastItem(session.opening_briefs);
  const framework = state.currentOpeningFramework || session.current_opening_framework || openingBrief?.framework || null;
  if (!openingBrief && !framework) {
    clearOpeningReveal();
    elements.openingBriefInput.value = "";
    elements.openingBriefLabel.textContent = "当前未设置";
    renderOpeningFramework(null, null);
    setOpeningStatus("", "pending");
    return;
  }
  state.currentOpeningFramework = framework;
  if (!openingBrief) {
    clearOpeningReveal();
    elements.openingBriefInput.value = "";
    elements.openingBriefLabel.textContent = "已生成框架稿，待扩写成稿";
    renderOpeningFramework(framework, null);
    setOpeningStatus("当前已有独立框架稿，可以直接按时长扩写一辩稿。", "success");
    return;
  }
  elements.openingBriefLabel.textContent = `${openingBrief.speaker_side} · ${openingBrief.source_mode === "manual" ? "手动注入" : "系统生成"}`;
  elements.openingDurationSelect.value = String(openingBrief.target_duration_minutes || 3);
  renderOpeningFramework(framework, openingBrief);

  if (state.openingRevealBriefId && state.openingRevealBriefId === openingBrief.brief_id) {
    return;
  }
  clearOpeningReveal();
  elements.openingBriefInput.value = openingBrief.spoken_text || "";
}

function renderClosing(session) {
  const closing = state.lastClosingResult?.closing_output || lastItem(session.closing_outputs);
  if (!closing) {
    elements.closingOutput.innerHTML = '<div class="empty-state">这里会显示最近生成的陈词稿。</div>';
    return;
  }
  elements.closingOutput.innerHTML = `
    <article class="stack-card">
      <strong>${escapeHtml(closing.speaker_side)} 陈词</strong>
      <p>${escapeHtml(closing.spoken_text)}</p>
      <p class="muted">策略：${escapeHtml(closing.strategy_summary)}</p>
    </article>
  `;
}

function renderEvidence() {
  const evidenceRecords = state.lastTurnResult?.evidence_records || state.lastClosingResult?.evidence_records || [];
  const researchQuery = state.lastTurnResult?.research_query || state.lastClosingResult?.research_query;
  if (!evidenceRecords.length) {
    elements.evidenceOutput.innerHTML = '<div class="empty-state">发送一轮后，这里会展示本轮调用的证据。</div>';
    return;
  }
  const cards = evidenceRecords
    .map(
      (record) => `
        <article class="stack-card">
          <strong>${escapeHtml(record.title)}</strong>
          <p>${escapeHtml(record.snippet)}</p>
          <p class="muted">${escapeHtml(record.source_type)} · ${escapeHtml(record.source_ref)}</p>
        </article>
      `,
    )
    .join("");
  elements.evidenceOutput.innerHTML = `
    ${researchQuery ? `<article class="stack-card"><strong>研究查询</strong><p>${escapeHtml(researchQuery)}</p></article>` : ""}
    ${cards}
  `;
}

function syncSessionHeader(session) {
  elements.sessionTitle.textContent = session.topic;
  elements.sessionMeta.textContent = `${session.user_side} vs ${session.agent_side} · ${session.summary.turn_count} 回合 · 最近更新 ${formatDate(session.summary.updated_at)}`;
  elements.coachModeBadge.textContent = `教练：${formatCoachMode(session.options.coach_feedback_mode)}`;
  elements.webSearchBadge.textContent = `检索：${formatSwitch(session.options.web_search_enabled)}`;
  elements.turnCountLabel.textContent = `${session.turns.length} 条发言`;
  elements.coachModeSelect.value = session.options.coach_feedback_mode;
  elements.defaultClosingSelect.value = session.options.default_closing_side;
  elements.webSearchToggle.checked = session.options.web_search_enabled;
  elements.sessionTopicInput.value = session.topic || "";
  elements.sessionUserSideInput.value = session.user_side || "";
  elements.sessionAgentSideInput.value = session.agent_side || "";
}

function syncWorkspaceMode(session) {
  const openingPhase = isOpeningPhase(session);
  elements.openingWorkbench.classList.toggle("hidden", !openingPhase);
  elements.debateWorkbench.classList.toggle("hidden", openingPhase);
  elements.enterDebateBtn.classList.toggle("hidden", !openingPhase);
  elements.returnOpeningBtn.classList.toggle("hidden", openingPhase);

  if (openingPhase) {
    elements.workspaceModeTitle.textContent = "立论打磨";
    elements.workspaceModeDescription.textContent = "当前页面只负责框架稿与一辩成稿。确认无误后，再进入对辩检验。";
    const openingBrief = state.lastOpeningResult?.opening_brief || lastItem(session?.opening_briefs || []);
    elements.enterDebateBtn.disabled = !openingBrief?.spoken_text?.trim();
    return;
  }

  elements.workspaceModeTitle.textContent = "对辩检验";
  elements.workspaceModeDescription.textContent = "这里才进入对辩 agent、教练反馈、陈词与证据检视。";
  elements.enterDebateBtn.disabled = false;
}

function renderCurrentSession() {
  const session = state.currentSession;
  if (!session) {
    showHomeScreen();
    showIntroView();
    clearOpeningReveal();
    elements.sessionTitle.textContent = "还没有选中会话";
    elements.sessionMeta.textContent = "创建一个会话，或者从首页恢复已有记录。";
    elements.timeline.innerHTML = '<div class="empty-state">当前没有会话。</div>';
    elements.clashBoard.innerHTML = '<div class="empty-state">当前还没有 clash。</div>';
    elements.sessionTopicInput.value = "";
    elements.sessionUserSideInput.value = "";
    elements.sessionAgentSideInput.value = "";
    elements.openingBriefInput.value = "";
    elements.openingBriefLabel.textContent = "当前未设置";
    renderOpeningFramework(null);
    state.currentOpeningFramework = null;
    elements.workspaceModeTitle.textContent = "立论打磨";
    elements.workspaceModeDescription.textContent = "当前页面只负责框架稿与一辩成稿。确认无误后，再进入对辩检验。";
    elements.enterDebateBtn.disabled = true;
    elements.openingWorkbench.classList.remove("hidden");
    elements.debateWorkbench.classList.add("hidden");
    elements.enterDebateBtn.classList.remove("hidden");
    elements.returnOpeningBtn.classList.add("hidden");
    setOpeningStatus("", "pending");
    renderCoach({ coach_reports: [] });
    renderClosing({ closing_outputs: [] });
    renderEvidence();
    return;
  }

  showWorkspaceScreen();
  syncSessionHeader(session);
  syncWorkspaceMode(session);
  renderTimeline(session);
  renderClashBoard(session);
  renderOpeningBrief(session);
  renderCoach(session);
  renderClosing(session);
  renderEvidence();
}

async function loadHealth() {
  const payload = await apiFetch("/api/health");
  elements.healthBadge.textContent = payload.llm_enabled ? `LLM: ${payload.model}` : "LLM: fallback";
}

async function loadSessions() {
  state.sessions = await apiFetch("/api/sessions");
  renderSessionList();
}

async function loadSession(sessionId) {
  abortOpeningStream();
  cancelFrameworkReveal();
  state.currentSession = await apiFetch(`/api/sessions/${sessionId}`);
  clearOpeningReveal();
  state.currentOpeningFramework = state.currentSession.current_opening_framework || null;
  resetTransientResults();
  renderSessionList();
  renderCurrentSession();
}

async function createSession(event) {
  event.preventDefault();
  const payload = {
    topic: elements.topicInput.value.trim(),
    user_side: elements.userSideInput.value.trim() || "正方",
    agent_side: elements.agentSideInput.value.trim() || "反方",
    coach_feedback_mode: elements.coachModeInput.value,
    web_search_enabled: elements.webSearchInput.checked,
    default_closing_side: elements.closingSideInput.value,
  };
  if (!payload.topic) {
    showToast("请先填写辩题。");
    return;
  }
  const session = await apiFetch("/api/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  abortOpeningStream();
  cancelFrameworkReveal();
  state.currentSession = session;
  clearOpeningReveal();
  state.currentOpeningFramework = session.current_opening_framework || null;
  resetTransientResults();
  elements.turnInput.value = "";
  await loadSessions();
  renderCurrentSession();
  showToast("已进入大辩工作台。");
}

async function deleteSession(sessionId) {
  const session = state.sessions.find((item) => item.session_id === sessionId);
  const label = session ? `《${session.topic}》` : "该会话";
  const confirmed = window.confirm(`确定删除${label}吗？删除后无法恢复。`);
  if (!confirmed) {
    return;
  }
  await apiFetch(`/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (state.currentSession && state.currentSession.session_id === sessionId) {
    abortOpeningStream();
    cancelFrameworkReveal();
    state.currentSession = null;
    clearOpeningReveal();
    state.currentOpeningFramework = null;
    resetTransientResults();
  }
  await loadSessions();
  renderCurrentSession();
  showToast("会话已删除。");
}

async function updateMetadata() {
  if (!state.currentSession) {
    showToast("请先选择一个会话。");
    return;
  }
  const payload = {
    topic: elements.sessionTopicInput.value.trim(),
    user_side: elements.sessionUserSideInput.value.trim(),
    agent_side: elements.sessionAgentSideInput.value.trim(),
  };
  if (!payload.topic) {
    showToast("辩题不能为空。");
    return;
  }
  const result = await apiFetch(`/api/sessions/${state.currentSession.session_id}/metadata`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.currentSession = result.session;
  await loadSessions();
  renderCurrentSession();
  showToast("辩题与立场已更新。");
}

async function updatePhase(phase, successMessage) {
  if (!state.currentSession) {
    showToast("请先选择一个会话。");
    return;
  }
  const result = await apiFetch(`/api/sessions/${state.currentSession.session_id}/phase`, {
    method: "PATCH",
    body: JSON.stringify({ phase }),
  });
  state.currentSession = result.session;
  renderCurrentSession();
  if (successMessage) {
    showToast(successMessage);
  }
}

async function generateOpeningBrief() {
  if (!state.currentSession) {
    showToast("请先创建或选择一个会话。");
    return;
  }
  const framework = collectOpeningFramework() || state.currentOpeningFramework || state.currentSession.current_opening_framework;
  if (!framework) {
    showToast("请先生成或填写框架稿。")
    return;
  }
  const targetDurationMinutes = Number.parseInt(elements.openingDurationSelect.value, 10) || 3;
  const targetWordCount = targetDurationMinutes * 300;
  abortOpeningStream();
  cancelFrameworkReveal();
  clearOpeningReveal();
  state.currentOpeningFramework = framework;
  const requestId = state.openingStreamRequestId;
  const abortController = new AbortController();
  state.openingStreamAbortController = abortController;
  state.lastOpeningResult = {
    opening_brief: {
      brief_id: `streaming-${Date.now()}`,
      speaker_side: state.currentSession.user_side,
      source_mode: "generated",
      spoken_text: "",
      framework,
      strategy_summary: framework.framework_summary || "",
      outline: Array.isArray(framework.argument_cards) ? framework.argument_cards.map((item, index) => summarizeArgumentCard(item, index)) : [],
      evidence_citations: [],
      confidence_notes: [],
      target_duration_minutes: targetDurationMinutes,
      target_word_count: targetWordCount,
    },
  };
  elements.openingBriefInput.value = "";
  state.openingStreamLastPaintAt = 0;
  elements.openingBriefLabel.textContent = `${state.currentSession.user_side} · 正在生成`;
  renderOpeningFramework(framework, state.lastOpeningResult.opening_brief);
  setOpeningStatus(`正在基于当前框架流式生成 ${targetDurationMinutes} 分钟一辩稿…`, "pending");
  setButtonBusy(elements.generateOpeningBtn, "生成中...", true);
  setButtonBusy(elements.generateFrameworkBtn, "生成中...", true);

  try {
    await consumeEventStream(`/api/sessions/${state.currentSession.session_id}/opening-briefs/stream`, {
      method: "POST",
      signal: abortController.signal,
      body: JSON.stringify({ speaker_side: "user", target_duration_minutes: targetDurationMinutes, framework }),
    }, async (eventName, payload) => {
      if (requestId !== state.openingStreamRequestId) {
        return;
      }

      if (eventName === "stage" || eventName === "research_ready" || eventName === "metadata") {
        setOpeningStatus(payload.message || "后端正在生成中…", "pending");
        return;
      }

      if (eventName === "framework_ready") {
        state.currentOpeningFramework = payload.framework || null;
        state.lastOpeningResult.opening_brief.framework = payload.framework || null;
        state.lastOpeningResult.opening_brief.strategy_summary = payload.framework?.framework_summary || "";
        state.lastOpeningResult.opening_brief.outline = Array.isArray(payload.framework?.argument_cards)
          ? payload.framework.argument_cards.map((item, index) => summarizeArgumentCard(item, index))
          : [];
        renderOpeningBrief(state.currentSession);
        setOpeningStatus(payload.message || "框架稿已生成，正在写成稿。", "pending");
        return;
      }

      if (eventName === "opening_chunk") {
        state.lastOpeningResult.opening_brief.spoken_text += payload.chunk || "";
        await flushOpeningStream();
        setOpeningStatus(`正在流式生成中，已输出 ${state.lastOpeningResult.opening_brief.spoken_text.length} 字...`, "pending");
        return;
      }

      if (eventName === "opening_reset") {
        state.lastOpeningResult.opening_brief.spoken_text = "";
        elements.openingBriefInput.value = "";
        state.openingStreamLastPaintAt = 0;
        await waitForNextPaint();
        setOpeningStatus(payload.message || "正在重新组织成稿。", "pending");
        return;
      }

      if (eventName === "completed") {
        await flushOpeningStream(true);
        state.currentSession = payload.session;
        state.currentOpeningFramework = payload.session.current_opening_framework || payload.opening_result?.opening_brief?.framework || null;
        state.lastOpeningResult = payload.opening_result;
        state.lastCoachResult = null;
        state.openingStreamAbortController = null;
        await loadSessions();
        renderCurrentSession();
        setOpeningStatus(`一辩稿已生成完成，当前为 ${payload.opening_result.opening_brief.target_duration_minutes || targetDurationMinutes} 分钟成稿。`, "success");
        showToast("一辩稿已流式生成完成。");
        return;
      }

      if (eventName === "error") {
        throw new Error(payload.message || "流式生成失败");
      }
    });
  } catch (error) {
    if (isAbortError(error) || requestId !== state.openingStreamRequestId) {
      return;
    }
    setOpeningStatus(error.message || "流式生成失败。", "pending");
    throw error;
  } finally {
    if (state.openingStreamAbortController === abortController) {
      state.openingStreamAbortController = null;
    }
    setButtonBusy(elements.generateOpeningBtn, "生成中...", false);
    setButtonBusy(elements.generateFrameworkBtn, "生成中...", false);
  }
}

async function saveOpeningBrief() {
  if (!state.currentSession) {
    showToast("请先创建或选择一个会话。");
    return;
  }
  const spokenText = elements.openingBriefInput.value.trim();
  const framework = collectOpeningFramework();
  if (!spokenText) {
    showToast("请先输入或生成一辩稿内容。");
    return;
  }
  abortOpeningStream();
  cancelFrameworkReveal();
  const outline = framework?.argument_cards
    ?.map((card, index) => summarizeArgumentCard(card, index))
    .filter((item) => item.trim()) || undefined;
  const payload = await apiFetch(`/api/sessions/${state.currentSession.session_id}/opening-briefs/import`, {
    method: "POST",
    body: JSON.stringify({
      speaker_side: "user",
      spoken_text: spokenText,
      strategy_summary: framework?.framework_summary || undefined,
      outline,
      framework,
      target_duration_minutes: Number.parseInt(elements.openingDurationSelect.value, 10) || 3,
    }),
  });
  clearOpeningReveal();
  setOpeningStatus("已保存当前框架与一辩稿。", "success");
  state.currentSession = payload.session;
  state.currentOpeningFramework = payload.session.current_opening_framework || framework || null;
  state.lastOpeningResult = { opening_brief: payload.opening_brief };
  await loadSessions();
  renderCurrentSession();
  showToast("当前框架与一辩稿已保存。");
}

async function generateOpeningFramework() {
  if (!state.currentSession) {
    showToast("请先创建或选择一个会话。");
    return;
  }
  abortOpeningStream();
  cancelFrameworkReveal();
  const requestId = state.frameworkRevealRequestId;
  setButtonBusy(elements.generateFrameworkBtn, "生成中...", true);
  setButtonBusy(elements.generateOpeningBtn, "生成中...", true);
  clearOpeningReveal();
  elements.openingBriefInput.value = "";
  elements.openingBriefLabel.textContent = "框架稿生成中";
  state.lastOpeningResult = null;
  state.currentOpeningFramework = null;
  renderOpeningFramework(buildEmptyFramework(), null);
  setOpeningStatus("正在独立生成框架稿…", "pending");
  try {
    const payload = await apiFetch(`/api/sessions/${state.currentSession.session_id}/opening-framework/generate`, {
      method: "POST",
      body: JSON.stringify({ speaker_side: "user" }),
    });
    if (requestId !== state.frameworkRevealRequestId) {
      return;
    }
    state.currentSession = payload.session;
    state.currentOpeningFramework = payload.framework_result.framework || null;
    state.lastOpeningResult = null;
    elements.openingBriefInput.value = "";
    const revealCompleted = await streamFrameworkIntoEditor(state.currentOpeningFramework, requestId);
    if (!revealCompleted) {
      return;
    }
    await loadSessions();
    renderCurrentSession();
    setOpeningStatus("框架稿已生成，可以继续修改后再扩写一辩稿。", "success");
    showToast("框架稿已生成。");
  } finally {
    setButtonBusy(elements.generateFrameworkBtn, "生成中...", false);
    setButtonBusy(elements.generateOpeningBtn, "生成中...", false);
  }
}

async function requestOpeningCoach() {
  if (!state.currentSession) {
    showToast("请先选择一个会话。");
    return;
  }
  const payload = await apiFetch(`/api/sessions/${state.currentSession.session_id}/opening-briefs/coach`, {
    method: "POST",
  });
  state.currentSession = payload.session;
  state.lastCoachResult = payload.coach_result;
  await loadSessions();
  renderCurrentSession();
  showToast(payload.coach_result.used_cached ? "已读取当前一辩稿教练反馈。" : "一辩稿教练反馈已生成。");
}

async function submitTurn() {
  if (!state.currentSession) {
    showToast("请先创建或选择一个会话。");
    return;
  }
  const userText = elements.turnInput.value.trim();
  if (!userText) {
    showToast("请输入本轮发言。");
    return;
  }
  const payload = await apiFetch(`/api/sessions/${state.currentSession.session_id}/turns`, {
    method: "POST",
    body: JSON.stringify({ user_text: userText }),
  });
  state.currentSession = payload.session;
  state.lastTurnResult = payload.turn_result;
  state.lastCoachResult = null;
  state.lastClosingResult = null;
  elements.turnInput.value = "";
  await loadSessions();
  renderCurrentSession();
  showToast("本轮已发送。");
}

async function requestCoach() {
  if (!state.currentSession) {
    showToast("请先选择一个会话。");
    return;
  }
  const payload = await apiFetch(`/api/sessions/${state.currentSession.session_id}/coach`, {
    method: "POST",
  });
  state.currentSession = payload.session;
  state.lastCoachResult = payload.coach_result;
  await loadSessions();
  renderCurrentSession();
  showToast(payload.coach_result.used_cached ? "已读取当前回合教练反馈。" : "教练反馈已生成。");
}

async function requestClosing(speakerSide) {
  if (!state.currentSession) {
    showToast("请先选择一个会话。");
    return;
  }
  const payload = await apiFetch(`/api/sessions/${state.currentSession.session_id}/closing`, {
    method: "POST",
    body: JSON.stringify({ speaker_side: speakerSide }),
  });
  state.currentSession = payload.session;
  state.lastClosingResult = payload.closing_result;
  await loadSessions();
  renderCurrentSession();
  showToast("陈词稿已生成。");
}

async function updateOptions() {
  if (!state.currentSession) {
    showToast("请先选择一个会话。");
    return;
  }
  const payload = await apiFetch(`/api/sessions/${state.currentSession.session_id}/options`, {
    method: "PATCH",
    body: JSON.stringify({
      coach_feedback_mode: elements.coachModeSelect.value,
      web_search_enabled: elements.webSearchToggle.checked,
      default_closing_side: elements.defaultClosingSelect.value,
    }),
  });
  state.currentSession = payload.session;
  await loadSessions();
  renderCurrentSession();
  showToast("会话选项已更新。");
}

function registerEvents() {
  elements.themeToggleBtn.addEventListener("click", () => {
    toggleTheme();
  });
  elements.startTrainingBtn.addEventListener("click", () => {
    showLaunchView();
  });
  elements.backToIntroBtn.addEventListener("click", () => {
    showIntroView();
  });
  elements.newSessionForm.addEventListener("submit", (event) => {
    createSession(event).catch((error) => showToast(error.message));
  });
  elements.generateFrameworkBtn.addEventListener("click", () => {
    generateOpeningFramework().catch((error) => showToast(error.message));
  });
  elements.generateOpeningBtn.addEventListener("click", () => {
    generateOpeningBrief().catch((error) => showToast(error.message));
  });
  elements.saveOpeningBtn.addEventListener("click", () => {
    saveOpeningBrief().catch((error) => showToast(error.message));
  });
  elements.coachOpeningBtn.addEventListener("click", () => {
    requestOpeningCoach().catch((error) => showToast(error.message));
  });
  elements.refreshSessionsBtn.addEventListener("click", () => {
    loadSessions().catch((error) => showToast(error.message));
  });
  elements.sendTurnBtn.addEventListener("click", () => {
    submitTurn().catch((error) => showToast(error.message));
  });
  elements.coachBtn.addEventListener("click", () => {
    requestCoach().catch((error) => showToast(error.message));
  });
  elements.closingMeBtn.addEventListener("click", () => {
    requestClosing("user").catch((error) => showToast(error.message));
  });
  elements.closingOpponentBtn.addEventListener("click", () => {
    requestClosing("opponent").catch((error) => showToast(error.message));
  });
  elements.updateOptionsBtn.addEventListener("click", () => {
    updateOptions().catch((error) => showToast(error.message));
  });
  elements.updateMetadataBtn.addEventListener("click", () => {
    updateMetadata().catch((error) => showToast(error.message));
  });
  elements.enterDebateBtn.addEventListener("click", () => {
    updatePhase("crossfire", "已进入对辩检验。").catch((error) => showToast(error.message));
  });
  elements.returnOpeningBtn.addEventListener("click", () => {
    updatePhase("opening", "已返回立论打磨。").catch((error) => showToast(error.message));
  });
  elements.backHomeBtn.addEventListener("click", () => {
    abortOpeningStream();
    cancelFrameworkReveal();
    state.currentSession = null;
    state.currentOpeningFramework = null;
    resetTransientResults();
    renderSessionList();
    renderCurrentSession();
  });
}

async function bootstrap() {
  applyTheme(getPreferredTheme());
  registerEvents();
  try {
    await Promise.all([loadHealth(), loadSessions()]);
    showHomeScreen();
    showIntroView();
    renderCurrentSession();
  } catch (error) {
    showToast(error.message);
  }
}

bootstrap();