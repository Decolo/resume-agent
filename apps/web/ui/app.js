const API_BASE = "/api/v1";
const WORKFLOW_STATES = [
  "draft",
  "resume_uploaded",
  "jd_provided",
  "gap_analyzed",
  "rewrite_applied",
  "exported",
];

const state = {
  sessionId: null,
  workflowState: "draft",
  runId: null,
  selectedFile: null,
  autoApprove: false,
  baselineByPath: {},
};

const el = {
  sessionBadge: document.getElementById("session-badge"),
  newSessionBtn: document.getElementById("new-session-btn"),
  workflowList: document.getElementById("workflow-list"),
  resumeInput: document.getElementById("resume-input"),
  uploadResumeBtn: document.getElementById("upload-resume-btn"),
  jdText: document.getElementById("jd-text"),
  jdUrl: document.getElementById("jd-url"),
  submitJdBtn: document.getElementById("submit-jd-btn"),
  autoApproveToggle: document.getElementById("auto-approve-toggle"),
  approvalsContainer: document.getElementById("approvals-container"),
  exportBtn: document.getElementById("export-btn"),
  exportLink: document.getElementById("export-link"),
  interruptBtn: document.getElementById("interrupt-btn"),
  timeline: document.getElementById("timeline"),
  chatForm: document.getElementById("chat-form"),
  chatInput: document.getElementById("chat-input"),
  sendBtn: document.getElementById("send-btn"),
  fileUploadInput: document.getElementById("file-upload-input"),
  uploadFileBtn: document.getElementById("upload-file-btn"),
  fileList: document.getElementById("file-list"),
  previewTab: document.getElementById("preview-tab"),
  diffTab: document.getElementById("diff-tab"),
  filePreview: document.getElementById("file-preview"),
  fileDiff: document.getElementById("file-diff"),
  toast: document.getElementById("toast"),
};

let assistantNode = null;
let approvalPollTimer = null;

function showToast(text) {
  el.toast.textContent = text;
  el.toast.classList.remove("hidden");
  window.setTimeout(() => el.toast.classList.add("hidden"), 2600);
}

function addMessage(role, text) {
  const box = document.createElement("div");
  box.className = `msg msg-${role}`;
  box.textContent = text;
  el.timeline.appendChild(box);
  el.timeline.scrollTop = el.timeline.scrollHeight;
  return box;
}

function renderWorkflow() {
  el.workflowList.innerHTML = "";
  const activeIndex = WORKFLOW_STATES.indexOf(state.workflowState);

  WORKFLOW_STATES.forEach((name, idx) => {
    const li = document.createElement("li");
    li.className = "workflow-item";
    if (idx < activeIndex) {
      li.classList.add("done");
    }
    if (idx === activeIndex) {
      li.classList.add("active");
    }
    li.textContent = `${idx + 1}. ${name.replaceAll("_", " ")}`;
    el.workflowList.appendChild(li);
  });
}

function updateSessionBadge() {
  el.sessionBadge.textContent = `Session: ${state.sessionId || "-"}`;
}

function encodeFilePath(path) {
  return path.split("/").map((seg) => encodeURIComponent(seg)).join("/");
}

function baselineKey() {
  return `resume_agent_web_baseline_${state.sessionId}`;
}

function saveBaseline() {
  if (!state.sessionId) {
    return;
  }
  localStorage.setItem(baselineKey(), JSON.stringify(state.baselineByPath));
}

function loadBaseline() {
  if (!state.sessionId) {
    state.baselineByPath = {};
    return;
  }
  const raw = localStorage.getItem(baselineKey());
  if (!raw) {
    state.baselineByPath = {};
    return;
  }

  try {
    state.baselineByPath = JSON.parse(raw);
  } catch (_err) {
    state.baselineByPath = {};
  }
}

function computeDiff(beforeText, afterText) {
  const before = beforeText.split("\n");
  const after = afterText.split("\n");
  const lines = [];
  const maxLen = Math.max(before.length, after.length);

  for (let i = 0; i < maxLen; i += 1) {
    const left = before[i] ?? "";
    const right = after[i] ?? "";
    if (left === right) {
      lines.push(`  ${left}`);
    } else {
      if (left) {
        lines.push(`- ${left}`);
      }
      if (right) {
        lines.push(`+ ${right}`);
      }
    }
  }
  return lines.join("\n");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body.error?.message) {
        detail = body.error.message;
      }
    } catch (_err) {
      // ignore
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

async function ensureSession() {
  const cached = localStorage.getItem("resume_agent_web_session_id");
  if (cached) {
    try {
      state.sessionId = cached;
      loadBaseline();
      await refreshSession();
      addMessage("system", "Resumed previous session after refresh.");
      return;
    } catch (_err) {
      localStorage.removeItem("resume_agent_web_session_id");
    }
  }

  const created = await fetchJson(`${API_BASE}/sessions`, {
    method: "POST",
    body: JSON.stringify({ workspace_name: "web-ui", auto_approve: false }),
  });

  state.sessionId = created.session_id;
  state.workflowState = created.workflow_state;
  state.autoApprove = Boolean(created.settings?.auto_approve);
  state.baselineByPath = {};
  localStorage.setItem("resume_agent_web_session_id", state.sessionId);
  saveBaseline();
  updateSessionBadge();
  renderWorkflow();
}

async function refreshSession() {
  if (!state.sessionId) {
    return;
  }
  const session = await fetchJson(`${API_BASE}/sessions/${state.sessionId}`);
  state.workflowState = session.workflow_state;
  state.autoApprove = Boolean(session.settings?.auto_approve);
  el.autoApproveToggle.checked = state.autoApprove;
  if (session.jd_text && !el.jdText.value) {
    el.jdText.value = session.jd_text;
  }
  if (session.jd_url && !el.jdUrl.value) {
    el.jdUrl.value = session.jd_url;
  }
  if (session.latest_export_path) {
    const encodedPath = encodeFilePath(session.latest_export_path);
    el.exportLink.href = `${API_BASE}/sessions/${state.sessionId}/files/${encodedPath}`;
    el.exportLink.textContent = session.latest_export_path;
  }
  renderWorkflow();
  updateSessionBadge();
}

async function refreshFiles() {
  if (!state.sessionId) {
    return;
  }
  const payload = await fetchJson(`${API_BASE}/sessions/${state.sessionId}/files`);
  const files = payload.files || [];
  el.fileList.innerHTML = "";

  if (!files.length) {
    const empty = document.createElement("li");
    empty.className = "file-item";
    empty.textContent = "No files uploaded yet.";
    el.fileList.appendChild(empty);
    return;
  }

  files.forEach((item) => {
    const li = document.createElement("li");
    li.className = "file-item";
    if (state.selectedFile === item.path) {
      li.classList.add("active");
    }
    li.textContent = `${item.path} (${item.size}b)`;
    li.addEventListener("click", () => openFile(item.path));
    el.fileList.appendChild(li);
  });

  if (!state.selectedFile) {
    state.selectedFile = files[0].path;
  }

  if (state.selectedFile) {
    await openFile(state.selectedFile);
  }
}

async function openFile(path) {
  state.selectedFile = path;
  const encodedPath = encodeFilePath(path);
  const response = await fetch(`${API_BASE}/sessions/${state.sessionId}/files/${encodedPath}`);
  if (!response.ok) {
    showToast(`Open file failed: ${response.status}`);
    return;
  }
  const text = await response.text();
  el.filePreview.textContent = text;

  if (!state.baselineByPath[path]) {
    state.baselineByPath[path] = text;
    saveBaseline();
  }

  el.fileDiff.textContent = computeDiff(state.baselineByPath[path], text);
  await refreshFilesListHighlight();
}

async function refreshFilesListHighlight() {
  Array.from(el.fileList.querySelectorAll(".file-item")).forEach((node) => {
    if (node.textContent?.startsWith(state.selectedFile)) {
      node.classList.add("active");
    } else {
      node.classList.remove("active");
    }
  });
}

async function refreshApprovals() {
  if (!state.sessionId) {
    return;
  }
  const payload = await fetchJson(`${API_BASE}/sessions/${state.sessionId}/approvals`);
  const items = payload.items || [];
  el.approvalsContainer.innerHTML = "";

  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = "No pending approvals.";
    empty.className = "msg msg-system";
    el.approvalsContainer.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "approval-item";

    const body = document.createElement("div");
    body.textContent = `${item.tool_name} -> ${item.args.path || "(no path)"}`;

    const actions = document.createElement("div");
    actions.className = "approval-actions";

    const approveBtn = document.createElement("button");
    approveBtn.textContent = "Approve";
    approveBtn.addEventListener("click", async () => {
      await decideApproval(item.approval_id, false, false);
    });

    const approveAllBtn = document.createElement("button");
    approveAllBtn.textContent = "Approve+Auto";
    approveAllBtn.addEventListener("click", async () => {
      await decideApproval(item.approval_id, true, false);
    });

    const rejectBtn = document.createElement("button");
    rejectBtn.textContent = "Reject";
    rejectBtn.className = "reject";
    rejectBtn.addEventListener("click", async () => {
      await decideApproval(item.approval_id, false, true);
    });

    actions.appendChild(approveBtn);
    actions.appendChild(approveAllBtn);
    actions.appendChild(rejectBtn);
    card.appendChild(body);
    card.appendChild(actions);
    el.approvalsContainer.appendChild(card);
  });
}

async function decideApproval(approvalId, applyToFuture, reject) {
  const suffix = reject ? "reject" : "approve";
  const body = reject ? undefined : JSON.stringify({ apply_to_future: applyToFuture });
  await fetchJson(`${API_BASE}/sessions/${state.sessionId}/approvals/${approvalId}/${suffix}`, {
    method: "POST",
    body,
  });

  if (!reject && applyToFuture) {
    state.autoApprove = true;
    el.autoApproveToggle.checked = true;
  }

  showToast(reject ? "Rejected pending write." : "Approval submitted.");
  await refreshApprovals();
  await refreshSession();
}

async function uploadResume() {
  const file = el.resumeInput.files?.[0];
  if (!file) {
    showToast("Select a resume file first.");
    return;
  }

  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/sessions/${state.sessionId}/resume`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    showToast("Resume upload failed.");
    return;
  }

  await refreshSession();
  await refreshFiles();
  showToast("Resume uploaded.");
}

async function uploadGenericFile() {
  const file = el.fileUploadInput.files?.[0];
  if (!file) {
    showToast("Choose a file first.");
    return;
  }

  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/sessions/${state.sessionId}/files/upload`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    showToast("File upload failed.");
    return;
  }

  await refreshFiles();
  showToast("File uploaded.");
}

async function submitJD() {
  await fetchJson(`${API_BASE}/sessions/${state.sessionId}/jd`, {
    method: "POST",
    body: JSON.stringify({ text: el.jdText.value, url: el.jdUrl.value }),
  });
  await refreshSession();
  showToast("JD submitted.");
}

async function setAutoApprove(enabled) {
  await fetchJson(`${API_BASE}/sessions/${state.sessionId}/settings/auto-approve`, {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
  state.autoApprove = enabled;
  showToast(enabled ? "Auto approve enabled." : "Auto approve disabled.");
  await refreshSession();
}

async function createRun(message) {
  const run = await fetchJson(`${API_BASE}/sessions/${state.sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
  state.runId = run.run_id;
  return run.run_id;
}

function parseSseBlock(block) {
  const result = { event: null, data: null };
  const dataLines = [];
  block.split("\n").forEach((line) => {
    if (line.startsWith("event: ")) {
      result.event = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6));
    }
  });

  if (dataLines.length) {
    try {
      result.data = JSON.parse(dataLines.join("\n"));
    } catch (_err) {
      result.data = null;
    }
  }
  return result;
}

async function streamRun(runId) {
  const response = await fetch(`${API_BASE}/sessions/${state.sessionId}/runs/${runId}/stream`);
  if (!response.ok || !response.body) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  assistantNode = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    while (buffer.includes("\n\n")) {
      const splitIndex = buffer.indexOf("\n\n");
      const block = buffer.slice(0, splitIndex);
      buffer = buffer.slice(splitIndex + 2);

      const envelope = parseSseBlock(block).data;
      if (!envelope) {
        continue;
      }
      handleEvent(envelope);
    }
  }

  await refreshSession();
  await refreshApprovals();
  await refreshFiles();
}

function handleEvent(evt) {
  switch (evt.type) {
    case "run_started":
      addMessage("system", "Run started.");
      break;
    case "assistant_delta":
      if (!assistantNode) {
        assistantNode = addMessage("assistant", evt.payload?.text || "");
      } else {
        assistantNode.textContent += evt.payload?.text || "";
      }
      break;
    case "tool_call_proposed":
      addMessage("system", `Pending approval for ${evt.payload?.tool_name || "tool"}.`);
      refreshApprovals();
      break;
    case "tool_call_approved":
      addMessage("system", `Approval granted: ${evt.payload?.approval_id || ""}`);
      break;
    case "tool_call_rejected":
      addMessage("system", `Approval rejected: ${evt.payload?.approval_id || ""}`);
      break;
    case "tool_result":
      addMessage("system", evt.payload?.result || "Tool completed.");
      break;
    case "run_interrupted":
      addMessage("system", "Run interrupted.");
      assistantNode = null;
      break;
    case "run_failed":
      addMessage("system", `Run failed: ${evt.payload?.message || "unknown error"}`);
      assistantNode = null;
      break;
    case "run_completed":
      addMessage("system", evt.payload?.final_text || "Run completed.");
      assistantNode = null;
      break;
    default:
      addMessage("system", `Event: ${evt.type}`);
      break;
  }
}

async function runMessageFlow(message) {
  addMessage("user", message);
  const runId = await createRun(message);
  await streamRun(runId);
}

async function interruptRun() {
  if (!state.runId) {
    showToast("No active run to interrupt.");
    return;
  }
  await fetchJson(`${API_BASE}/sessions/${state.sessionId}/runs/${state.runId}/interrupt`, {
    method: "POST",
  });
  showToast("Interrupt requested.");
}

async function exportResume() {
  const response = await fetchJson(`${API_BASE}/sessions/${state.sessionId}/export`, {
    method: "POST",
  });
  const encodedPath = encodeFilePath(response.artifact_path);
  const href = `${API_BASE}/sessions/${state.sessionId}/files/${encodedPath}`;
  el.exportLink.href = href;
  el.exportLink.textContent = response.artifact_path;
  await refreshSession();
  await refreshFiles();
  showToast("Export generated.");
}

function setPreviewTab(mode) {
  const previewMode = mode === "preview";
  el.previewTab.classList.toggle("active", previewMode);
  el.diffTab.classList.toggle("active", !previewMode);
  el.filePreview.classList.toggle("hidden", !previewMode);
  el.fileDiff.classList.toggle("hidden", previewMode);
}

async function startNewSession() {
  localStorage.removeItem("resume_agent_web_session_id");
  state.sessionId = null;
  state.selectedFile = null;
  state.runId = null;
  state.baselineByPath = {};
  el.timeline.innerHTML = "";
  el.exportLink.textContent = "";
  el.exportLink.removeAttribute("href");
  await ensureSession();
  await refreshApprovals();
  await refreshFiles();
  await refreshSession();
  showToast("Started a new session.");
}

async function bootstrap() {
  await ensureSession();
  await refreshApprovals();
  await refreshFiles();
  await refreshSession();

  approvalPollTimer = window.setInterval(() => {
    refreshApprovals().catch(() => {});
  }, 2500);
}

el.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = el.chatInput.value.trim();
  if (!message) {
    return;
  }
  el.chatInput.value = "";
  try {
    await runMessageFlow(message);
  } catch (err) {
    addMessage("system", `Run error: ${err.message}`);
  }
});

el.uploadResumeBtn.addEventListener("click", () => uploadResume().catch((err) => showToast(err.message)));
el.submitJdBtn.addEventListener("click", () => submitJD().catch((err) => showToast(err.message)));
el.uploadFileBtn.addEventListener("click", () => uploadGenericFile().catch((err) => showToast(err.message)));
el.autoApproveToggle.addEventListener("change", (event) => {
  setAutoApprove(Boolean(event.target.checked)).catch((err) => showToast(err.message));
});
el.interruptBtn.addEventListener("click", () => interruptRun().catch((err) => showToast(err.message)));
el.exportBtn.addEventListener("click", () => exportResume().catch((err) => showToast(err.message)));
el.previewTab.addEventListener("click", () => setPreviewTab("preview"));
el.diffTab.addEventListener("click", () => setPreviewTab("diff"));
el.newSessionBtn.addEventListener("click", () => startNewSession().catch((err) => showToast(err.message)));

bootstrap().catch((err) => {
  addMessage("system", `Bootstrap failed: ${err.message}`);
});

window.addEventListener("beforeunload", () => {
  if (approvalPollTimer) {
    window.clearInterval(approvalPollTimer);
  }
});
