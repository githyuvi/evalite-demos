const API_BASE = "http://localhost:8000";

// A reload should always start a fresh conversation — never resume from a
// past page load.
localStorage.removeItem("conversation_id");
let conversationId = null;

const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("chat-input");
const newChatBtn = document.getElementById("new-chat-btn");

function addMessage(role, content) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = content;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

// Parses the backend's SSE stream. Each event is JSON-encoded so multi-line
// step-by-step solutions never break the "one event per data: line" framing.
async function streamQuery(message) {
  const resp = await fetch(`${API_BASE}/api/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });

  const assistantEl = addMessage("assistant", "");
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop();

    for (const raw of events) {
      let eventType = "message";
      let dataLine = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        if (line.startsWith("data:")) dataLine = line.slice(5).trim();
      }
      if (!dataLine) continue;
      const data = JSON.parse(dataLine);

      if (eventType === "start") {
        conversationId = data.conversation_id;
        localStorage.setItem("conversation_id", conversationId);
      } else if (eventType === "done") {
        // stream finished, nothing to do
      } else {
        assistantEl.textContent += data.text;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }
  }
}

formEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  addMessage("user", text);

  try {
    await streamQuery(text);
  } catch (err) {
    addMessage("assistant", `Error: ${err.message}`);
  }
});

newChatBtn.addEventListener("click", () => {
  localStorage.removeItem("conversation_id");
  conversationId = null;
  messagesEl.innerHTML = "";
});
