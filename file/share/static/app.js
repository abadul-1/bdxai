(() => {
  "use strict";

  const chatEl = document.getElementById("chat");
  const form = document.getElementById("composer");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const clearBtn = document.getElementById("clear");
  const modelEl = document.getElementById("model");

  const WELCOME =
    "Welcome to BDX AI. Your local ethical cybersecurity learning assistant.\n\n" +
    "Ask me about:\n" +
    "• Python\n" +
    "• Linux / Termux\n" +
    "• Web security concepts\n" +
    "• Networking\n" +
    "• Secure coding\n" +
    "• CTF-style educational problems\n" +
    "• Cybersecurity fundamentals";

  /** @type {{role:'user'|'assistant',content:string}[]} */
  let history = [];
  let busy = false;

  // ---------- rendering ----------
  function addMessage(role, text, opts = {}) {
    const el = document.createElement("div");
    el.className = "msg " + (role === "user" ? "user" : "ai") + (opts.error ? " err" : "");
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "user" ? "YOU" : "BDX AI";
    const body = document.createElement("div");
    body.textContent = text;
    el.appendChild(who);
    el.appendChild(body);
    chatEl.appendChild(el);
    chatEl.scrollTop = chatEl.scrollHeight;
    return el;
  }

  function addTyping() {
    const el = document.createElement("div");
    el.className = "msg ai typing-wrap";
    el.innerHTML =
      '<span class="who">BDX AI</span>' +
      '<div class="typing"><i></i><i></i><i></i></div>';
    chatEl.appendChild(el);
    chatEl.scrollTop = chatEl.scrollHeight;
    return el;
  }

  function clearChat() {
    history = [];
    chatEl.innerHTML = "";
    addMessage("assistant", WELCOME);
  }

  function setBusy(b) {
    busy = b;
    sendBtn.disabled = b;
  }

  // ---------- server ----------
  async function send(messages) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    let data;
    try {
      data = await res.json();
    } catch {
      throw new Error("Invalid server response.");
    }
    if (!res.ok && !data.error) {
      throw new Error("Server error " + res.status);
    }
    if (data.error) throw new Error(data.error);
    return data.reply || "(empty response)";
  }

  // ---------- events ----------
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;

    input.value = "";
    input.style.height = "auto";

    addMessage("user", text);
    history.push({ role: "user", content: text });

    setBusy(true);
    const typing = addTyping();

    try {
      const reply = await send(history);
      typing.remove();
      addMessage("assistant", reply);
      history.push({ role: "assistant", content: reply });
    } catch (err) {
      typing.remove();
      addMessage("assistant", "⚠ " + (err && err.message ? err.message : "Unknown error"), {
        error: true,
      });
      // Pop the last user message from history so retries stay consistent
      history.pop();
    } finally {
      setBusy(false);
      input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  clearBtn.addEventListener("click", clearChat);

  // ---------- boot ----------
  clearChat();
  fetch("/health")
    .then((r) => r.json())
    .then((d) => {
      if (d && d.model) modelEl.textContent = d.model;
    })
    .catch(() => {});
})();
