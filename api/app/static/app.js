const messagesElement = document.querySelector("#messages");
const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const fitForm = document.querySelector("#fit-form");
const jobDescription = document.querySelector("#job-description");
const fitButton = document.querySelector("#fit-button");
const themeToggle = document.querySelector("#theme-toggle");
const askInvitation = document.querySelector("#ask-invitation");
const history = [];
let busy = false;

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const isDark = theme === "dark";
  const label = isDark ? "Switch to light theme" : "Switch to dark theme";
  themeToggle.setAttribute("aria-label", label);
  themeToggle.title = label;
  themeToggle.querySelector(".theme-icon").textContent = isDark ? "☀" : "☾";
  themeToggle.querySelector(".theme-label").textContent = isDark ? "Light mode" : "Dark mode";
  document.querySelector('meta[name="theme-color"]').content = isDark ? "#0d1524" : "#f3f2ef";
}

applyTheme(document.documentElement.dataset.theme || "light");
themeToggle.addEventListener("click", () => {
  const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(nextTheme);
  try {
    localStorage.setItem("askme-theme", nextTheme);
  } catch {
    // The selected theme remains active for this page even if storage is unavailable.
  }
});

askInvitation.addEventListener("click", () => {
  document.querySelector("#chat-form").scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    block: "center",
  });
  messageInput.focus({ preventScroll: true });
});

function createChatbotIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.classList.add("chatbot-icon");
  icon.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#chatbot-icon");
  icon.append(use);
  return icon;
}

function addMessage(role, content, options = {}) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;

  const avatar = document.createElement("div");
  avatar.className = `message-avatar ${role === "user" ? "" : "assistant-avatar"}`.trim();
  avatar.setAttribute("aria-hidden", "true");
  if (role === "user") {
    avatar.textContent = "You";
  } else {
    avatar.append(createChatbotIcon());
  }

  const body = document.createElement("div");
  body.className = "message-body";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const name = document.createElement("strong");
  name.textContent = role === "user" ? "You" : "Akhil Mukesh Assistant";
  const description = document.createElement("span");
  description.textContent = role === "user"
    ? "Recruiter"
    : "“I speak fluent Java—and promise not to make you debug me.”";
  if (role !== "user") meta.classList.add("assistant-identity");
  meta.append(name, description);

  const message = document.createElement("div");
  message.className = "message-content";
  if (options.typing) {
    const indicator = document.createElement("span");
    indicator.className = "typing-indicator";
    indicator.setAttribute("aria-label", "Preparing an answer");
    for (let index = 0; index < 3; index += 1) {
      indicator.append(document.createElement("span"));
    }
    message.append(indicator);
  } else {
    message.textContent = content;
  }

  body.append(meta, message);
  article.append(avatar, body);
  messagesElement.append(article);
  messagesElement.scrollTop = messagesElement.scrollHeight;
  return article;
}

function renderStreamEvent(eventData, output, state) {
  const event = JSON.parse(eventData);
  if (event.type === "token") {
    state.answer += event.content;
    output.textContent = state.answer;
    messagesElement.scrollTop = messagesElement.scrollHeight;
  } else if (event.type === "error") {
    state.error = event.detail;
  } else if (event.type === "done") {
    state.completed = true;
    formatStructuredAnswer(output, state.answer);
  }
}

function appendInlineMarkdown(element, text) {
  const emphasis = /(\*\*([^*]+)\*\*|\*([^*]+)\*)/g;
  let lastIndex = 0;
  let match = emphasis.exec(text);
  while (match) {
    element.append(document.createTextNode(text.slice(lastIndex, match.index)));
    const formatted = document.createElement(match[2] ? "strong" : "em");
    formatted.textContent = match[2] || match[3];
    element.append(formatted);
    lastIndex = emphasis.lastIndex;
    match = emphasis.exec(text);
  }
  element.append(document.createTextNode(text.slice(lastIndex)));
}

function parseAnswerHeading(line) {
  const candidate = line.trim().replace(/^#{1,6}\s*/, "").replace(/^\d+[.)]\s*/, "").replace(/\*\*/g, "");
  const headings = [
    ["answer", /^(?:answer|short answer|summary)\b/i],
    ["evidence", /^(?:evidence from my profile|profile evidence|supporting evidence|relevant evidence)\b/i],
    ["missing", /^(?:not specified in my profile|not specified|what is not specified|gaps|not shown in profile)\b/i],
    ["follow-up", /^(?:suggested follow[- ]?up|follow[- ]?up|next step)\b/i],
  ];
  for (const [section, pattern] of headings) {
    const match = candidate.match(pattern);
    if (match) {
      const remainder = candidate.slice(match[0].length).replace(/^\s*:\s*/, "").trim();
      return { section, content: remainder };
    }
  }
  return null;
}

function appendAnswerContent(container, lines) {
  let currentList = null;
  lines.forEach((line) => {
    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    if (bullet) {
      if (!currentList) {
        currentList = document.createElement("ul");
        container.append(currentList);
      }
      const item = document.createElement("li");
      appendInlineMarkdown(item, bullet[1]);
      currentList.append(item);
      return;
    }

    if (!line.trim()) return;
    currentList = null;
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, line.replace(/^\s+/, ""));
    container.append(paragraph);
  });
}

function formatStructuredAnswer(output, answer) {
  const sections = new Map([
    ["answer", []],
    ["evidence", []],
    ["missing", []],
    ["follow-up", []],
  ]);
  let currentSection = null;
  let foundHeadings = false;

  answer.split(/\r?\n/).forEach((line) => {
    const heading = parseAnswerHeading(line);
    if (heading) {
      currentSection = heading.section;
      foundHeadings = true;
      if (heading.content) sections.get(currentSection).push(heading.content);
      return;
    }

    if (currentSection) {
      sections.get(currentSection).push(line);
    } else if (!foundHeadings && line.trim()) {
      sections.get("answer").push(line);
    }
  });

  const labels = [
    ["answer", "Answer"],
    ["evidence", "Evidence from my profile"],
    ["missing", "Not specified in my profile"],
    ["follow-up", "Suggested follow-up"],
  ];
  const fragment = document.createDocumentFragment();
  const structuredAnswer = document.createElement("div");
  structuredAnswer.className = "structured-answer";

  labels.forEach(([key, label]) => {
    const section = document.createElement("section");
    section.className = `answer-section answer-section-${key}`;
    const heading = document.createElement("h3");
    heading.textContent = label;
    const content = document.createElement("div");
    content.className = "answer-section-content";
    const lines = sections.get(key).filter((line) => line.trim());

    if (!lines.length) {
      const fallback = document.createElement("p");
      fallback.className = "answer-section-empty";
      fallback.textContent = key === "evidence"
        ? "No profile evidence was separated in the response."
        : key === "missing"
          ? "No additional details were specified."
          : key === "follow-up"
            ? "No follow-up suggested."
            : "No answer was provided.";
      content.append(fallback);
    } else {
      appendAnswerContent(content, lines);
    }

    section.append(heading, content);
    structuredAnswer.append(section);
  });

  if (!foundHeadings) {
    const notice = document.createElement("p");
    notice.className = "answer-format-note";
    notice.textContent = "This answer was provided without separate profile evidence.";
    structuredAnswer.prepend(notice);
  }

  fragment.append(structuredAnswer);
  output.replaceChildren(fragment);
}

function setBusy(value) {
  busy = value;
  sendButton.disabled = value;
  fitButton.disabled = value;
  sendButton.querySelector("span:first-child").textContent = value ? "Thinking…" : "Send message";
}

async function submitQuestion(question) {
  const trimmed = question.trim();
  if (!trimmed || busy) return;

  addMessage("user", trimmed);
  const typingMessage = addMessage("assistant", "", { typing: true });
  const output = typingMessage.querySelector(".message-content");
  const conversation = history.slice();
  let retainedLength = conversation.reduce((total, item) => total + item.content.length, 0);
  while (conversation.length && retainedLength + trimmed.length > 11000) {
    retainedLength -= conversation.shift().content.length;
  }

  setBusy(true);
  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: trimmed, history: conversation.slice(-20) }),
    });
    if (!response.ok) {
      const result = await response.json();
      const detail = typeof result.detail === "string" ? result.detail : "The request could not be completed.";
      throw new Error(detail);
    }
    if (!response.headers.get("content-type")?.includes("text/event-stream") || !response.body) {
      throw new Error("The chat service returned an unsupported response.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const state = { answer: "", completed: false, error: "" };
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const eventBlock = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const eventData = eventBlock
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (eventData) renderStreamEvent(eventData, output, state);
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const eventData = buffer
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (eventData) renderStreamEvent(eventData, output, state);
    }
    if (state.error) {
      output.textContent = state.answer
        ? `${state.answer}\n\n${state.error}`
        : `I couldn’t complete that request. ${state.error}`;
    } else if (!state.completed || !state.answer) {
      throw new Error("The chat stream ended before a complete answer was received.");
    } else {
      history.push({ role: "user", content: trimmed }, { role: "assistant", content: state.answer });
    }
    while (history.length > 20) history.shift();
  } catch (error) {
    output.textContent = `I couldn’t complete that request. ${error.message}`;
  } finally {
    setBusy(false);
    messageInput.focus();
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = messageInput.value;
  if (!question.trim() || busy) return;
  messageInput.value = "";
  submitQuestion(question);
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => {
    submitQuestion(button.dataset.prompt);
  });
});

fitForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const description = jobDescription.value.trim();
  if (!description || busy) return;
  const question = `Assess my fit for this role based only on my profile. Summarize the relevant matches, evidence, gaps or qualifications not shown, and useful follow-up questions for the recruiter. Do not infer missing information.\n\nJob description:\n${description}`;
  submitQuestion(question);
  document.querySelector("#conversation").scrollIntoView({ behavior: "smooth", block: "start" });
});

jobDescription.addEventListener("input", () => {
  document.querySelector("#job-count").textContent = `${jobDescription.value.length.toLocaleString()} / 3,500`;
});

document.querySelector("#new-chat").addEventListener("click", () => {
  if (busy) return;
  history.length = 0;
  messagesElement.replaceChildren();
  addMessage("assistant", "Hi! I can help you learn about this candidate’s background and skills. Ask me anything, or share a job description for a fit assessment.");
  messageInput.focus();
});

function addTextLink(container, label, href, iconId = "") {
  const link = document.createElement("a");
  link.className = "profile-link";
  if (iconId) {
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.classList.add("profile-link-icon");
    icon.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#${iconId}`);
    icon.append(use);
    link.append(icon);
  }
  const linkLabel = document.createElement("span");
  linkLabel.textContent = label;
  link.append(linkLabel);
  link.href = href;
  if (href.startsWith("http")) {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  }
  container.append(link);
}

function showProfile(profile) {
  const name = typeof profile.name === "string" && profile.name.trim() ? profile.name.trim() : "Candidate profile";
  document.querySelector("#candidate-name").textContent = name;
  document.querySelector("#resume-download").hidden = profile.resume_available !== true;
  document.querySelector("#cover-letter-download").hidden =
    profile.cover_letter_available !== true;

  if (typeof profile.title === "string" && profile.title.trim()) {
    document.querySelector("#candidate-title").textContent = profile.title;
  }
  if (typeof profile.location === "string" && profile.location.trim()) {
    document.querySelector("#candidate-location").textContent = profile.location;
  }
  if (typeof profile.bio === "string" && profile.bio.trim()) {
    document.querySelector("#candidate-bio").textContent = profile.bio;
  }

  const links = document.querySelector("#profile-links");
  if (typeof profile.public_contact_email === "string" && profile.public_contact_email.trim()) {
    addTextLink(
      links,
      profile.public_contact_email,
      `mailto:${profile.public_contact_email}`,
      "gmail-icon",
    );
  }
  if (typeof profile.public_phone === "string" && profile.public_phone.trim()) {
    const telephone = profile.public_phone.replace(/[^\d+]/g, "");
    if (telephone) {
      addTextLink(links, profile.public_phone, `tel:${telephone}`, "phone-icon");
    }
  }
  if (profile.links && typeof profile.links === "object" && !Array.isArray(profile.links)) {
    Object.entries(profile.links).forEach(([label, href]) => {
      if (typeof href !== "string" || !href.trim()) return;
      try {
        const url = new URL(href, window.location.origin);
        if (url.protocol === "http:" || url.protocol === "https:") {
          const iconId = label.toLowerCase() === "linkedin"
            ? "linkedin-icon"
            : label.toLowerCase() === "github"
              ? "github-icon"
              : "";
          addTextLink(links, label, url.href, iconId);
        }
      } catch {
        return;
      }
    });
  }
}

fetch("/api/profile")
  .then(async (response) => {
    if (!response.ok) throw new Error("Candidate details are temporarily unavailable.");
    showProfile(await response.json());
  })
  .catch(() => {
    document.querySelector("#candidate-name").textContent = "Candidate profile";
    document.querySelector("#candidate-bio").textContent = "Candidate details couldn’t be loaded. You can still try the chat or reload the page.";
  });
