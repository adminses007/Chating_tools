(() => {
  const STORAGE_KEYS = {
    server: "chat_server_url",
    access: "chat_access_token",
    refresh: "chat_refresh_token",
    user: "chat_user",
    theme: "chat_theme",
    rememberUser: "chat_remember_user",
    rememberPass: "chat_remember_pass",
    savedUsername: "chat_saved_username",
    savedPassword: "chat_saved_password",
    collapseUsers: "chat_collapse_users",
    collapseConvs: "chat_collapse_convs",
  };

  /** Desktop pywebview uses local :8765; mobile/browser on Server uses same origin. */
  function isDesktopLocalShell() {
    return location.port === "8765";
  }

  function detectServerUrl() {
    if (!isDesktopLocalShell()) {
      return location.origin;
    }
    return localStorage.getItem(STORAGE_KEYS.server) || "http://127.0.0.1:8000";
  }

  const state = {
    serverUrl: detectServerUrl(),
    accessToken: localStorage.getItem(STORAGE_KEYS.access) || "",
    refreshToken: localStorage.getItem(STORAGE_KEYS.refresh) || "",
    user: JSON.parse(localStorage.getItem(STORAGE_KEYS.user) || "null"),
    ws: null,
    connState: "disconnected",
    reconnectTimer: null,
    pingTimer: null,
    users: [],
    conversations: [],
    activeConversationId: null,
    messages: [],
    pending: new Map(),
    embedded: !isDesktopLocalShell(),
  };

  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const t = (key, vars) => (window.I18N ? window.I18N.t(key, vars) : key);

  function setConnStatus(status) {
    state.connState = status;
    const labels = {
      disconnected: t("connDisconnected"),
      connecting: t("connConnecting"),
      connected: t("connConnected"),
      reconnecting: t("connReconnecting"),
    };
    ["setup-status", "conn-status"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.className = `status-pill ${status}`;
      el.textContent = labels[status] || status;
    });
  }

  function showView(name) {
    $("view-setup").classList.toggle("hidden", name !== "setup");
    $("view-chat").classList.toggle("hidden", name !== "chat");
  }

  function persistAuth() {
    localStorage.setItem(STORAGE_KEYS.server, state.serverUrl);
    localStorage.setItem(STORAGE_KEYS.access, state.accessToken);
    localStorage.setItem(STORAGE_KEYS.refresh, state.refreshToken);
    localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(state.user));
  }

  function clearAuth() {
    state.accessToken = "";
    state.refreshToken = "";
    state.user = null;
    localStorage.removeItem(STORAGE_KEYS.access);
    localStorage.removeItem(STORAGE_KEYS.refresh);
    localStorage.removeItem(STORAGE_KEYS.user);
  }

  async function api(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (!(opts.body instanceof FormData)) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
    }
    if (state.accessToken) headers.Authorization = `Bearer ${state.accessToken}`;
    let res = await fetch(`${state.serverUrl}${path}`, { ...opts, headers });
    if (res.status === 401 && state.refreshToken && path !== "/api/auth/refresh") {
      const ok = await refreshTokens();
      if (ok) {
        headers.Authorization = `Bearer ${state.accessToken}`;
        res = await fetch(`${state.serverUrl}${path}`, { ...opts, headers });
      }
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || res.statusText);
      throw new Error(detail);
    }
    return data;
  }

  async function refreshTokens() {
    try {
      const res = await fetch(`${state.serverUrl}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: state.refreshToken }),
      });
      const data = await res.json();
      if (!res.ok) return false;
      state.accessToken = data.access_token;
      state.refreshToken = data.refresh_token;
      state.user = data.user;
      persistAuth();
      return true;
    } catch {
      return false;
    }
  }

  function wsUrl() {
    const base = state.serverUrl.replace(/^http/, "ws");
    return `${base}/ws?token=${encodeURIComponent(state.accessToken)}`;
  }

  function connectWs() {
    closeWs(false);
    setConnStatus(state.connState === "connected" ? "reconnecting" : "connecting");
    let ws;
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      scheduleReconnect();
      return;
    }
    state.ws = ws;

    ws.onopen = () => {
      setConnStatus("connected");
      startPing();
      ws.send(JSON.stringify({ type: "sync.request", payload: {} }));
      loadUsers();
      loadConversations();
    };

    ws.onmessage = (ev) => {
      try {
        handleWsEvent(JSON.parse(ev.data));
      } catch (e) {
        console.error(e);
      }
    };

    ws.onclose = () => {
      stopPing();
      if (!state.accessToken) {
        setConnStatus("disconnected");
        return;
      }
      setConnStatus("reconnecting");
      scheduleReconnect();
    };

    ws.onerror = () => {
      try { ws.close(); } catch {}
    };
  }

  function closeWs(clearTimers = true) {
    stopPing();
    if (clearTimers && state.reconnectTimer) {
      clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
    if (state.ws) {
      try { state.ws.onclose = null; state.ws.close(); } catch {}
      state.ws = null;
    }
  }

  function scheduleReconnect() {
    if (state.reconnectTimer) return;
    state.reconnectTimer = setTimeout(() => {
      state.reconnectTimer = null;
      if (state.accessToken) connectWs();
    }, 2000);
  }

  function startPing() {
    stopPing();
    state.pingTimer = setInterval(() => {
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: "ping", payload: {} }));
      }
    }, 25000);
  }

  function stopPing() {
    if (state.pingTimer) {
      clearInterval(state.pingTimer);
      state.pingTimer = null;
    }
  }

  function sameConversation(a, b) {
    return Number(a) === Number(b);
  }

  function totalUnread() {
    return state.conversations.reduce((sum, c) => sum + (Number(c.unread_count) || 0), 0);
  }

  function updateTitleBadge() {
    const n = totalUnread();
    document.title = n > 0 ? `(${n}) LAN Chat` : "LAN Chat";
  }

  function playNotifySound() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      const ctx = new Ctx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 880;
      gain.gain.value = 0.0001;
      osc.connect(gain);
      gain.connect(ctx.destination);
      const now = ctx.currentTime;
      gain.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);
      osc.start(now);
      osc.stop(now + 0.3);
      setTimeout(() => ctx.close().catch(() => {}), 400);
    } catch {}
  }

  function showToast(title, body, conversationId) {
    const host = $("toast-host");
    if (!host) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = `<span class="toast-dot"></span><div><div class="toast-title">${esc(title)}</div><div class="toast-body">${esc(body)}</div></div>`;
    el.onclick = () => {
      el.remove();
      if (conversationId) {
        openConversation(Number(conversationId)).catch(() => {});
      }
    };
    host.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

  function unreadForUser(userId) {
    const uid = Number(userId);
    const direct = state.conversations.find((c) => {
      if (c.type !== "direct") return false;
      return (c.members || []).some((m) => Number(m.id) === uid);
    });
    return Number(direct?.unread_count) || 0;
  }

  function updateSectionBadges() {
    const total = totalUnread();
    const convBadge = $("convs-unread-badge");
    if (convBadge) {
      if (total > 0) {
        convBadge.textContent = total > 99 ? "99+" : String(total);
        convBadge.classList.remove("hidden");
      } else {
        convBadge.classList.add("hidden");
      }
    }
    const usersUnread = state.users.reduce((sum, u) => sum + unreadForUser(u.id), 0);
    const userBadge = $("users-unread-badge");
    if (userBadge) {
      if (usersUnread > 0) {
        userBadge.textContent = usersUnread > 99 ? "99+" : String(usersUnread);
        userBadge.classList.remove("hidden");
      } else {
        userBadge.classList.add("hidden");
      }
    }
  }

  function previewText(msg) {
    if (!msg) return "";
    if (msg.message_type === "image") return t("image");
    if (msg.message_type === "video") return t("video");
    if (msg.message_type === "audio") return t("audio");
    if (msg.message_type === "file") return t("file");
    return String(msg.content || "").slice(0, 80);
  }

  function notifyNewMessage(msg) {
    if (!msg || msg.sender_id === state.user?.id) return;
    // 全局提示：右上角 Toast + 声音，不再强制展开「最近聊天」
    playNotifySound();

    const conv = state.conversations.find((c) => sameConversation(c.id, msg.conversation_id));
    const name = msg.sender_name || conv?.title || t("newMessage");
    const preview = previewText(msg);
    showToast(t("newMessageFrom", { name }), preview || t("newMessage"), msg.conversation_id);

    if (document.hidden && "Notification" in window && Notification.permission === "granted") {
      try {
        const n = new Notification(t("newMessageFrom", { name }), {
          body: preview || t("newMessage"),
          tag: `conv-${msg.conversation_id}`,
        });
        n.onclick = () => {
          window.focus();
          openConversation(Number(msg.conversation_id)).catch(() => {});
          n.close();
        };
      } catch {}
    }
  }

  function handleWsEvent(evt) {
    const { type, payload } = evt;
    if (type === "pong") return;

    if (type === "message.ack" && payload.message) {
      upsertMessage(payload.message, true);
      loadConversations().then(() => {
        updateTitleBadge();
        renderUsers();
        updateSectionBadges();
      });
      return;
    }

    if (type === "message.new") {
      const viewing = sameConversation(state.activeConversationId, payload.conversation_id);
      upsertMessage(payload, false);
      (async () => {
        if (viewing) {
          // 先标记已读，再刷新列表，避免角标被旧未读数据写回来
          await markRead(payload.conversation_id, payload.id);
        } else {
          notifyNewMessage(payload);
          await loadConversations();
          renderUsers();
          updateSectionBadges();
          updateTitleBadge();
          const row = document.querySelector(`.list-item[data-cid="${payload.conversation_id}"]`);
          if (row) {
            row.classList.add("has-new");
            setTimeout(() => row.classList.remove("has-new"), 2500);
          }
          const userRow = document.querySelector(`.list-item[data-user="${payload.sender_id}"]`);
          if (userRow) {
            userRow.classList.add("has-new");
            setTimeout(() => userRow.classList.remove("has-new"), 2500);
          }
        }
      })().catch((e) => console.warn(e));
      return;
    }

    if (type === "message.status") {
      const msg = state.messages.find((m) => m.id === payload.message_id);
      if (msg) {
        msg._status = payload.status;
        if (sameConversation(state.activeConversationId, payload.conversation_id)) renderMessages();
      }
      return;
    }

    if (type === "presence.update") {
      const u = state.users.find((x) => x.id === payload.user_id);
      if (u) {
        u.online = !!payload.online;
        renderUsers();
      }
      if (state.activeConversationId) updateChatHeader();
      return;
    }

    if (type === "sync.unread") {
      loadConversations().then(updateTitleBadge);
      return;
    }

    if (type === "error") {
      console.warn("ws error", payload);
    }
  }

  function upsertMessage(msg, fromAck) {
    if (!sameConversation(msg.conversation_id, state.activeConversationId) && !fromAck) {
      return;
    }
    const idx = state.messages.findIndex(
      (m) => m.id === msg.id || (msg.client_msg_id && m.client_msg_id === msg.client_msg_id)
    );
    if (idx >= 0) state.messages[idx] = { ...state.messages[idx], ...msg, _status: fromAck ? "sent" : msg._status };
    else if (sameConversation(msg.conversation_id, state.activeConversationId)) {
      state.messages.push({ ...msg, _status: fromAck ? "sent" : "delivered" });
    }
    if (sameConversation(msg.conversation_id, state.activeConversationId)) renderMessages(true);
  }

  async function loadUsers() {
    state.users = await api("/api/users");
    renderUsers();
  }

  let _convLoadSeq = 0;
  async function loadConversations() {
    const seq = ++_convLoadSeq;
    const data = await api("/api/conversations");
    // 忽略过期的并发请求，避免旧未读数据把角标写回来
    if (seq !== _convLoadSeq) return;
    state.conversations = data;
    // 正在查看的会话一律视为已读（防 markRead / 刷新竞态）
    if (state.activeConversationId) {
      const active = state.conversations.find((c) =>
        sameConversation(c.id, state.activeConversationId)
      );
      if (active) active.unread_count = 0;
    }
    renderConversations();
  }

  function initials(name) {
    const s = String(name || "?").trim();
    if (!s) return "?";
    const parts = s.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return s.slice(0, 2).toUpperCase();
  }

  function avatarColor(seed) {
    const colors = ["#7360f2", "#e85d75", "#34b3a0", "#f0a202", "#5c7cfa", "#cc5de8", "#20c997", "#ff6b6b"];
    let h = 0;
    const str = String(seed || "");
    for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
    return colors[h % colors.length];
  }

  function avatarHtml(name, opts = {}) {
    const online = opts.online;
    const size = opts.sm ? " sm" : "";
    const presence =
      typeof online === "boolean"
        ? `<span class="presence ${online ? "on" : ""}"></span>`
        : "";
    return `<div class="avatar${size}" style="background:linear-gradient(145deg, ${avatarColor(name)}cc, ${avatarColor(name)})">${esc(
      initials(name)
    )}${presence}</div>`;
  }

  function shortTime(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      const now = new Date();
      const sameDay = d.toDateString() === now.toDateString();
      return sameDay
        ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : d.toLocaleDateString([], { month: "short", day: "numeric" });
    } catch {
      return "";
    }
  }

  function setMeChrome() {
    if (!state.user) return;
    $("me-name").textContent = state.user.display_name;
    const av = $("me-avatar");
    if (av) {
      av.style.background = `linear-gradient(145deg, ${avatarColor(state.user.display_name)}cc, ${avatarColor(state.user.display_name)})`;
      av.textContent = initials(state.user.display_name);
    }
  }

  function renderUsers() {
    $("user-list").innerHTML = state.users
      .map((u) => {
        const unread = unreadForUser(u.id);
        return `
      <div class="list-item ${unread ? "has-unread" : ""}" data-user="${u.id}">
        ${avatarHtml(u.display_name, { online: !!u.online, sm: true })}
        <div class="body">
          <div class="name"><span>${esc(u.display_name)}</span></div>
          <div class="meta">${u.online ? t("online") : "@" + esc(u.username)}</div>
        </div>
        ${unread ? `<span class="badge">${unread > 99 ? "99+" : unread}</span>` : ""}
      </div>`;
      })
      .join("");
    $("user-list").querySelectorAll(".list-item").forEach((el) => {
      el.onclick = () => {
        openDirect(Number(el.dataset.user)).catch((err) => {
          console.error(err);
          alert(err.message || String(err));
        });
      };
    });
    updateSectionBadges();
  }

  function renderConversations() {
    $("conv-list").innerHTML = state.conversations
      .map((c) => {
        const preview = c.last_message
          ? c.last_message.message_type === "text"
            ? c.last_message.content
            : c.last_message.message_type === "image"
              ? t("image")
              : c.last_message.message_type === "video"
                ? t("video")
                : c.last_message.message_type === "audio"
                  ? t("audio")
                  : c.last_message.message_type === "file"
                    ? t("file")
                    : `[${c.last_message.message_type}]`
          : t("noMessages");
        const timeLabel = shortTime(c.last_message?.created_at || c.updated_at);
        const active = sameConversation(c.id, state.activeConversationId);
        const unread = Number(c.unread_count) || 0;
        return `
        <div class="list-item ${active ? "active" : ""} ${unread ? "has-unread" : ""}" data-cid="${c.id}">
          ${avatarHtml(c.title || "Chat", { sm: true })}
          <div class="body">
            <div class="name"><span>${esc(c.title || "Chat")}</span><span class="time">${esc(timeLabel)}</span></div>
            <div class="meta">${esc(preview)}</div>
          </div>
          ${unread ? `<span class="badge">${unread > 99 ? "99+" : unread}</span>` : ""}
        </div>`;
      })
      .join("");
    $("conv-list").querySelectorAll(".list-item").forEach((el) => {
      el.onclick = () => {
        openConversation(Number(el.dataset.cid)).catch((err) => {
          console.error(err);
          alert(err.message || String(err));
        });
      };
    });
    updateTitleBadge();
    updateSectionBadges();
  }

  async function openDirect(userId) {
    try {
      // 先切换到聊天面板，避免窄屏下仍停在侧栏看不见聊天框
      $("chat-empty").classList.add("hidden");
      $("chat-active").classList.remove("hidden");
      showChatPane();
      $("chat-title").textContent = "…";
      $("chat-sub").textContent = "";
      $("message-list").innerHTML = "";

      const conv = await api("/api/conversations/direct", {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
      await loadConversations();
      await openConversation(conv.id);
    } catch (e) {
      console.error(e);
      alert(e.message || String(e));
      $("chat-active").classList.add("hidden");
      $("chat-empty").classList.remove("hidden");
    }
  }

  function showSidebar() {
    const layout = $("main-layout");
    if (layout) {
      layout.classList.add("show-sidebar");
      layout.classList.remove("show-chat");
    }
  }

  function showChatPane() {
    const layout = $("main-layout");
    if (layout) {
      layout.classList.remove("show-sidebar");
      layout.classList.add("show-chat");
    }
    // 确保聊天区可见（防止被侧栏状态或缓存样式挡住）
    const chat = document.querySelector(".chat");
    if (chat) chat.style.display = "";
  }

  function currentConversation() {
    const id = Number(state.activeConversationId);
    return state.conversations.find((c) => Number(c.id) === id);
  }

  function updateChatHeader() {
    const c = currentConversation();
    if (!c) return;
    $("chat-title").textContent = c.title || "Chat";
    const peerAv = $("chat-peer-avatar");
    if (peerAv) {
      peerAv.style.background = `linear-gradient(145deg, ${avatarColor(c.title)}cc, ${avatarColor(c.title)})`;
      peerAv.textContent = initials(c.title || "C");
      peerAv.querySelector(".presence")?.remove();
    }
    const sub = $("chat-sub");
    if (c.type === "direct") {
      const other = (c.members || []).find((m) => m.id !== state.user.id);
      const online = state.users.find((u) => u.id === other?.id)?.online;
      sub.textContent = online ? t("online") : t("offline");
      sub.classList.toggle("online", !!online);
      if (peerAv && typeof online === "boolean") {
        const dot = document.createElement("span");
        dot.className = `presence ${online ? "on" : ""}`;
        peerAv.appendChild(dot);
      }
      $("chat-actions").innerHTML = "";
    } else {
      sub.textContent = t("groupMeta", { n: (c.members || []).length });
      sub.classList.remove("online");
      $("chat-actions").innerHTML = `<button class="ghost" type="button" id="btn-leave-group">${esc(t("leaveGroup"))}</button>`;
      const leave = $("btn-leave-group");
      if (leave) {
        leave.onclick = async () => {
          await api(`/api/groups/${c.id}/leave`, { method: "POST" });
          state.activeConversationId = null;
          $("chat-active").classList.add("hidden");
          $("chat-empty").classList.remove("hidden");
          showSidebar();
          loadConversations();
        };
      }
    }
  }

  function mediaUrl(fileId) {
    return `${state.serverUrl}/api/files/${fileId}/download?token=${encodeURIComponent(state.accessToken)}`;
  }

  function isVideoMsg(m) {
    if (m.message_type === "video") return true;
    const mime = (m.file_mime || "").toLowerCase();
    const name = (m.file_name || m.content || "").toLowerCase();
    return mime.startsWith("video/") || /\.(mp4|webm|mov|mkv|avi|m4v|3gp|wmv|flv|mpeg|mpg|ogv)$/i.test(name);
  }

  function isAudioMsg(m) {
    if (m.message_type === "audio") return true;
    const mime = (m.file_mime || "").toLowerCase();
    const name = (m.file_name || m.content || "").toLowerCase();
    return mime.startsWith("audio/") || /\.(mp3|wav|aac|flac|ogg|m4a|wma|opus)$/i.test(name);
  }

  function isImageMsg(m) {
    if (m.message_type === "image") return true;
    const mime = (m.file_mime || "").toLowerCase();
    const name = (m.file_name || m.content || "").toLowerCase();
    return mime.startsWith("image/") || /\.(jpg|jpeg|png|gif|webp|bmp|heic|svg|tif|tiff)$/i.test(name);
  }

  function renderMessages(scrollBottom = false) {
    const box = $("message-list");
    box.innerHTML = state.messages
      .map((m) => {
        if (m.message_type === "system") {
          return `<div class="bubble system">${esc(m.content)}</div>`;
        }
        const mine = m.sender_id === state.user.id;
        let body = "";
        if (m.file_id && isImageMsg(m)) {
          body = `<img class="preview" src="${mediaUrl(m.file_id)}" alt="${esc(m.file_name || "image")}" loading="lazy" />`;
        } else if (m.file_id && isVideoMsg(m)) {
          body = `<div class="media-wrap">
            <video class="video-player" controls preload="metadata" playsinline src="${mediaUrl(m.file_id)}"></video>
            <div class="file-card compact">
              <div><div>${esc(m.file_name || m.content || "video")}</div><div class="meta">${formatSize(m.file_size || 0)}</div></div>
              <a href="${mediaUrl(m.file_id)}" data-download="${m.file_id}" download>${esc(t("download"))}</a>
            </div>
          </div>`;
        } else if (m.file_id && isAudioMsg(m)) {
          body = `<div class="media-wrap">
            <audio class="audio-player" controls preload="metadata" src="${mediaUrl(m.file_id)}"></audio>
            <div class="file-card compact">
              <div><div>${esc(m.file_name || m.content || "audio")}</div><div class="meta">${formatSize(m.file_size || 0)}</div></div>
              <a href="${mediaUrl(m.file_id)}" data-download="${m.file_id}" download>${esc(t("download"))}</a>
            </div>
          </div>`;
        } else if (m.file_id) {
          body = `<div class="file-card">
            <div class="file-icon">📄</div>
            <div class="file-info">
              <div class="file-name">${esc(m.file_name || m.content || "file")}</div>
              <div class="meta">${formatSize(m.file_size || 0)} · ${esc((m.file_mime || "file").split(";")[0])}</div>
            </div>
            <a class="file-dl" href="${mediaUrl(m.file_id)}" data-download="${m.file_id}" download>${esc(t("download"))}</a>
          </div>`;
        } else {
          body = `<div class="body">${esc(m.content || "")}</div>`;
        }
        const tickClass = m._status === "read" ? "ticks read" : "ticks";
        const status = mine ? `<span class="${tickClass}">${statusLabel(m._status || "sent")}</span>` : "";
        return `<div class="bubble ${mine ? "mine" : ""}">
          ${mine || cIsDirect() ? "" : `<div class="sender">${esc(m.sender_name || "")}</div>`}
          ${body}
          <div class="meta"><span>${esc(shortTime(m.created_at))}</span>${status}</div>
        </div>`;
      })
      .join("");

    box.querySelectorAll("a[data-download]").forEach((a) => {
      a.onclick = async (e) => {
        e.preventDefault();
        const id = a.getAttribute("data-download");
        try {
          const res = await fetch(mediaUrl(id));
          if (!res.ok) throw new Error(t("downloadFail"));
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download =
            a.closest(".file-card")?.querySelector(".file-name, div div")?.textContent || "file";
          link.click();
          URL.revokeObjectURL(url);
        } catch (err) {
          alert(err.message || t("downloadFail"));
        }
      };
    });

    if (scrollBottom) box.scrollTop = box.scrollHeight;
  }

  function cIsDirect() {
    return currentConversation()?.type === "direct";
  }

  function statusLabel(s) {
    if (s === "read" || s === "delivered") return "✓✓";
    if (s === "sent") return "✓";
    if (s === "sending") return "…";
    return "";
  }

  function formatTime(iso) {
    return shortTime(iso);
  }

  function formatSize(n) {
    if (!n) return "";
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1048576).toFixed(1)} MB`;
  }

  function uuid() {
    return crypto.randomUUID ? crypto.randomUUID() : `c-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function sendMessage() {
    const text = $("msg-input").value.trim();
    if (!text || !state.activeConversationId) return;
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
      $("setup-error").textContent = t("notConnected");
      return;
    }
    const clientMsgId = uuid();
    const optimistic = {
      id: `tmp-${clientMsgId}`,
      conversation_id: state.activeConversationId,
      sender_id: state.user.id,
      sender_name: state.user.display_name,
      message_type: "text",
      content: text,
      client_msg_id: clientMsgId,
      created_at: new Date().toISOString(),
      _status: "sending",
    };
    state.messages.push(optimistic);
    renderMessages(true);
    $("msg-input").value = "";
    state.ws.send(
      JSON.stringify({
        type: "message.send",
        request_id: clientMsgId,
        payload: {
          conversation_id: state.activeConversationId,
          content: text,
          message_type: "text",
          client_msg_id: clientMsgId,
        },
      })
    );
  }

  function clearLocalUnread(conversationId) {
    const cid = Number(conversationId);
    let changed = false;
    state.conversations.forEach((c) => {
      if (Number(c.id) === cid && Number(c.unread_count) > 0) {
        c.unread_count = 0;
        changed = true;
      }
    });
    if (changed) {
      renderConversations();
      renderUsers();
    } else {
      updateTitleBadge();
      updateSectionBadges();
    }
  }

  async function markRead(conversationId, lastId) {
    if (!conversationId || !lastId) return;
    // 先本地清掉角标，避免已读接口返回前仍显示未读
    clearLocalUnread(conversationId);
    try {
      await api(`/api/conversations/${conversationId}/read`, {
        method: "POST",
        body: JSON.stringify({ last_read_message_id: Number(lastId) }),
      });
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(
          JSON.stringify({
            type: "message.read",
            payload: {
              conversation_id: Number(conversationId),
              last_read_message_id: Number(lastId),
            },
          })
        );
      }
      // 再拉一次服务端状态，确保角标与服务器一致
      await loadConversations();
      renderUsers();
      updateSectionBadges();
      updateTitleBadge();
    } catch (e) {
      console.warn("markRead failed", e);
    }
  }

  async function openConversation(cid) {
    state.activeConversationId = Number(cid);
    $("chat-empty").classList.add("hidden");
    $("chat-active").classList.remove("hidden");
    showChatPane();
    // 一点击就先去掉本地未读，避免角标残留
    clearLocalUnread(state.activeConversationId);
    updateChatHeader();
    try {
      state.messages = await api(`/api/conversations/${state.activeConversationId}/messages?limit=80`);
      state.messages.forEach((m) => {
        if (m.sender_id === state.user.id) {
          m._status = m.read_at ? "read" : m.delivered_at ? "delivered" : "sent";
        }
      });
      renderMessages(true);
      const lastId =
        state.messages.length > 0
          ? state.messages[state.messages.length - 1].id
          : currentConversation()?.last_message?.id;
      if (lastId) {
        await markRead(state.activeConversationId, lastId);
      } else {
        await loadConversations();
        renderUsers();
        updateSectionBadges();
        updateTitleBadge();
      }
    } catch (e) {
      console.error(e);
      $("message-list").innerHTML = `<div class="bubble system">${esc(e.message || String(e))}</div>`;
    }
  }

  async function uploadFile(file) {
    if (!state.activeConversationId || !file) return;
    const maxHint = 500 * 1024 * 1024;
    if (file.size > maxHint) {
      alert(t("fileTooLarge", { size: formatSize(file.size) }));
      return;
    }
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("conversation_id", String(state.activeConversationId));
    form.append("client_msg_id", uuid());
    $("upload-progress").classList.remove("hidden");
    $("upload-bar").style.width = "0%";

    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${state.serverUrl}/api/files/upload`);
      xhr.setRequestHeader("Authorization", `Bearer ${state.accessToken}`);
      xhr.timeout = 30 * 60 * 1000; // large video uploads
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          $("upload-bar").style.width = `${Math.round((e.loaded / e.total) * 100)}%`;
        }
      };
      xhr.onload = () => {
        $("upload-progress").classList.add("hidden");
        let data = {};
        try {
          data = JSON.parse(xhr.responseText || "{}");
        } catch {}
        if (xhr.status >= 200 && xhr.status < 300) {
          if (data.message) upsertMessage(data.message, true);
          loadConversations();
          resolve();
        } else {
          const detail =
            typeof data.detail === "string"
              ? data.detail
              : Array.isArray(data.detail)
                ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
                : xhr.statusText || "Upload failed";
          reject(new Error(detail));
        }
      };
      xhr.ontimeout = () => {
        $("upload-progress").classList.add("hidden");
        reject(new Error(t("uploadTimeout")));
      };
      xhr.onerror = () => {
        $("upload-progress").classList.add("hidden");
        reject(new Error(t("uploadNetwork")));
      };
      xhr.send(form);
    });
  }

  async function enterChat(auth) {
    state.accessToken = auth.access_token;
    state.refreshToken = auth.refresh_token;
    state.user = auth.user;
    persistAuth();
    setMeChrome();
    showView("chat");
    connectWs();
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
  }

  function refreshSectionGrow() {
    const users = $("section-users");
    const convs = $("section-convs");
    if (!users || !convs) return;
    const usersOpen = !users.classList.contains("collapsed");
    const convsOpen = !convs.classList.contains("collapsed");
    users.classList.toggle("grow", usersOpen && !convsOpen);
    convs.classList.toggle("grow", convsOpen);
  }

  function setSectionCollapsed(sectionId, toggleId, collapsed, storageKey) {
    const section = $(sectionId);
    const toggle = $(toggleId);
    if (!section || !toggle) return;
    section.classList.toggle("collapsed", collapsed);
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    if (storageKey) localStorage.setItem(storageKey, collapsed ? "1" : "0");
    refreshSectionGrow();
  }

  function bindSectionToggle(sectionId, toggleId, storageKey) {
    const toggle = $(toggleId);
    if (!toggle) return;
    const saved = localStorage.getItem(storageKey) === "1";
    setSectionCollapsed(sectionId, toggleId, saved, storageKey);
    toggle.onclick = () => {
      const next = !$(sectionId).classList.contains("collapsed");
      setSectionCollapsed(sectionId, toggleId, next, storageKey);
    };
  }

  // Setup UI bindings
  $("server-url").value = state.serverUrl;
  if (state.embedded) {
    $("server-config-block").classList.add("hidden");
    $("server-embedded-hint").classList.remove("hidden");
    $("server-embedded-hint").textContent = t("connectedHint", { url: state.serverUrl });
  }

  bindSectionToggle("section-users", "toggle-users", STORAGE_KEYS.collapseUsers);
  bindSectionToggle("section-convs", "toggle-convs", STORAGE_KEYS.collapseConvs);

  document.querySelectorAll(".lang-switch button[data-lang]").forEach((btn) => {
    btn.onclick = () => {
      if (window.I18N) window.I18N.setLang(btn.dataset.lang);
      setConnStatus(state.connState || "disconnected");
      if (state.user) {
        const meSub = document.querySelector(".me-sub");
        if (meSub) meSub.textContent = t("online");
        renderUsers();
        renderConversations();
        if (state.activeConversationId) {
          updateChatHeader();
          renderMessages();
        }
      }
    };
  });

  window.addEventListener("langchange", () => {
    setConnStatus(state.connState || "disconnected");
  });

  if (window.I18N) window.I18N.apply();

  const btnToggle = $("btn-toggle-sidebar");
  if (btnToggle) {
    btnToggle.onclick = () => {
      const layout = $("main-layout");
      if (!layout) return;
      if (layout.classList.contains("show-sidebar")) showChatPane();
      else showSidebar();
    };
  }
  const btnBack = $("btn-back-list");
  if (btnBack) {
    btnBack.onclick = () => {
      showSidebar();
    };
  }

  document.querySelectorAll(".tabs-mini button").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".tabs-mini button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.auth;
      $("auth-login").classList.toggle("hidden", mode !== "login");
      $("auth-register").classList.toggle("hidden", mode !== "register");
    };
  });

  $("btn-check").onclick = async () => {
    try {
      $("setup-error").textContent = "";
      state.serverUrl = $("server-url").value.trim().replace(/\/$/, "");
      localStorage.setItem(STORAGE_KEYS.server, state.serverUrl);
      setConnStatus("connecting");
      const res = await fetch(`${state.serverUrl}/health`);
      const data = await res.json();
      if (!res.ok) throw new Error("Health check failed");
      setConnStatus("connected");
      $("setup-error").textContent = `OK · v${data.version}`;
      setTimeout(() => setConnStatus("disconnected"), 1500);
    } catch (e) {
      setConnStatus("disconnected");
      $("setup-error").textContent = e.message;
    }
  };

  function loadRememberedLogin() {
    const rememberUser = localStorage.getItem(STORAGE_KEYS.rememberUser) === "1";
    const rememberPass = localStorage.getItem(STORAGE_KEYS.rememberPass) === "1";
    const ru = $("remember-user");
    const rp = $("remember-pass");
    if (ru) ru.checked = rememberUser;
    if (rp) rp.checked = rememberPass;
    if (rememberUser) {
      $("login-user").value = localStorage.getItem(STORAGE_KEYS.savedUsername) || "";
    }
    if (rememberPass) {
      $("login-pass").value = localStorage.getItem(STORAGE_KEYS.savedPassword) || "";
    }
  }

  function saveRememberedLogin(username, password) {
    const rememberUser = !!$("remember-user")?.checked;
    const rememberPass = !!$("remember-pass")?.checked;
    localStorage.setItem(STORAGE_KEYS.rememberUser, rememberUser ? "1" : "0");
    localStorage.setItem(STORAGE_KEYS.rememberPass, rememberPass ? "1" : "0");
    if (rememberUser) {
      localStorage.setItem(STORAGE_KEYS.savedUsername, username);
    } else {
      localStorage.removeItem(STORAGE_KEYS.savedUsername);
    }
    if (rememberPass) {
      localStorage.setItem(STORAGE_KEYS.savedPassword, password);
      // 勾选记住密码时，一并记住用户名更符合使用习惯
      if (!rememberUser) {
        localStorage.setItem(STORAGE_KEYS.rememberUser, "1");
        localStorage.setItem(STORAGE_KEYS.savedUsername, username);
        if ($("remember-user")) $("remember-user").checked = true;
      }
    } else {
      localStorage.removeItem(STORAGE_KEYS.savedPassword);
    }
  }

  $("btn-login").onclick = async () => {
    try {
      $("setup-error").textContent = "";
      state.serverUrl = $("server-url").value.trim().replace(/\/$/, "");
      const username = $("login-user").value.trim();
      const password = $("login-pass").value;
      const auth = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      saveRememberedLogin(username, password);
      await enterChat(auth);
    } catch (e) {
      $("setup-error").textContent = e.message;
    }
  };

  $("btn-register").onclick = async () => {
    try {
      $("setup-error").textContent = "";
      state.serverUrl = $("server-url").value.trim().replace(/\/$/, "");
      const auth = await api("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          username: $("reg-user").value.trim(),
          password: $("reg-pass").value,
          display_name: $("reg-name").value.trim(),
          invite_code: $("reg-invite").value,
        }),
      });
      await enterChat(auth);
    } catch (e) {
      $("setup-error").textContent = e.message;
    }
  };

  $("btn-logout").onclick = async () => {
    try {
      if (state.refreshToken) {
        await api("/api/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh_token: state.refreshToken }),
        });
      }
    } catch {}
    closeWs();
    clearAuth();
    showView("setup");
    setConnStatus("disconnected");
  };

  $("btn-send").onclick = sendMessage;
  $("msg-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  $("btn-attach").onclick = () => $("file-input").click();
  $("file-input").onchange = async () => {
    const file = $("file-input").files?.[0];
    $("file-input").value = "";
    if (!file) return;
    try {
      await uploadFile(file);
    } catch (e) {
      alert(e.message);
    }
  };

  $("btn-theme").onclick = () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(STORAGE_KEYS.theme, next);
  };

  $("btn-new-group").onclick = () => {
    const box = $("group-members");
    box.innerHTML = state.users
      .map(
        (u) => `<label><input type="checkbox" value="${u.id}" /> ${esc(u.display_name)} (@${esc(u.username)})</label>`
      )
      .join("");
    $("group-name").value = "";
    $("group-dialog").showModal();
  };

  $("group-form").onsubmit = async (e) => {
    if (e.submitter && e.submitter.value === "cancel") return;
    e.preventDefault();
    const name = $("group-name").value.trim();
    const member_ids = [...$("group-members").querySelectorAll("input:checked")].map((i) => Number(i.value));
    try {
      const conv = await api("/api/groups", {
        method: "POST",
        body: JSON.stringify({ group_name: name, member_ids }),
      });
      $("group-dialog").close();
      await loadConversations();
      await openConversation(conv.id);
    } catch (err) {
      alert(err.message);
    }
  };

  // Theme bootstrap
  const theme = localStorage.getItem(STORAGE_KEYS.theme) || "light";
  document.documentElement.setAttribute("data-theme", theme);
  loadRememberedLogin();

  // Auto resume session
  (async () => {
    if (state.accessToken && state.user) {
      try {
        const me = await api("/api/users/me");
        state.user = me;
        setMeChrome();
        showView("chat");
        connectWs();
      } catch {
        clearAuth();
        showView("setup");
      }
    } else {
      showView("setup");
      setConnStatus("disconnected");
    }
  })();
})();
