const docs = {
  zh: {
    spec: "../openapi/dist/openapi.zh.yaml",
    guide: "../openapi/intro.zh.md",
    title: "小红书接口层 API 文档",
    subtitle: "默认中文，可切换 English",
    guideLabel: "接口说明",
    loadingLabel: "正在加载接口说明...",
    loadingError: "接口说明加载失败",
    htmlLang: "zh-CN",
  },
  en: {
    spec: "../openapi/dist/openapi.en.yaml",
    guide: "../openapi/intro.en.md",
    title: "XHS Interface Layer API Docs",
    subtitle: "English view. Switch back to Chinese anytime.",
    guideLabel: "Intro",
    loadingLabel: "Loading intro...",
    loadingError: "Failed to load intro",
    htmlLang: "en",
  },
};

function readLang() {
  const value = new URLSearchParams(window.location.search).get("lang");
  return value === "en" ? "en" : "zh";
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function inlineMarkdown(value) {
  return escapeHtml(value).replace(/`([^`]+)`/g, "<code>$1</code>");
}

function flushParagraph(lines, html) {
  if (lines.length === 0) return;
  html.push(`<p>${inlineMarkdown(lines.join(" "))}</p>`);
  lines.length = 0;
}

function renderMarkdown(markdown) {
  const html = [];
  const paragraph = [];
  let listOpen = false;
  let codeOpen = false;

  for (const line of markdown.split(/\r?\n/)) {
    if (line.startsWith("```")) {
      flushParagraph(paragraph, html);
      if (listOpen) html.push("</ul>");
      listOpen = false;
      html.push(codeOpen ? "</code></pre>" : "<pre><code>");
      codeOpen = !codeOpen;
      continue;
    }

    if (codeOpen) {
      html.push(`${escapeHtml(line)}\n`);
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph(paragraph, html);
      if (listOpen) html.push("</ul>");
      listOpen = false;
      html.push(`<h${heading[1].length}>${inlineMarkdown(heading[2])}</h${heading[1].length}>`);
      continue;
    }

    const listItem = line.match(/^\s*-\s+(.+)$/);
    if (listItem) {
      flushParagraph(paragraph, html);
      if (!listOpen) html.push("<ul>");
      listOpen = true;
      html.push(`<li>${inlineMarkdown(listItem[1])}</li>`);
      continue;
    }

    if (line.trim() === "") {
      flushParagraph(paragraph, html);
      if (listOpen) html.push("</ul>");
      listOpen = false;
      continue;
    }

    paragraph.push(line.trim());
  }

  flushParagraph(paragraph, html);
  if (listOpen) html.push("</ul>");
  if (codeOpen) html.push("</code></pre>");
  return html.join("\n");
}

function waitForElement(selector, root = document, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const existing = root.querySelector(selector);
    if (existing) {
      resolve(existing);
      return;
    }

    const observer = new MutationObserver(() => {
      const found = root.querySelector(selector);
      if (!found) return;
      observer.disconnect();
      clearTimeout(timer);
      resolve(found);
    });
    const timer = setTimeout(() => {
      observer.disconnect();
      reject(new Error(`timeout waiting for ${selector}`));
    }, timeoutMs);
    observer.observe(root, { childList: true, subtree: true });
  });
}

function scrollToGuide() {
  document.getElementById("api-intro")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function mountGuideMenu(cfg) {
  const menu = document.querySelector('[role="menu"]');
  const firstItem = menu?.querySelector('li[data-item-id^="tag/"]');
  if (!menu || !firstItem || document.querySelector('[data-item-id="tag/ApiIntro"]')) return;

  const item = document.createElement("li");
  item.className = `${firstItem.className} guide-menu-item`;
  item.dataset.itemId = "tag/ApiIntro";
  item.tabIndex = 0;
  item.setAttribute("role", "menuitem");
  item.setAttribute("aria-label", cfg.guideLabel);

  const label = firstItem.querySelector("label")?.cloneNode(false) || document.createElement("label");
  const span = firstItem.querySelector("span")?.cloneNode(false) || document.createElement("span");
  span.textContent = cfg.guideLabel;
  span.title = cfg.guideLabel;
  label.appendChild(span);
  item.appendChild(label);
  item.addEventListener("click", scrollToGuide);
  item.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") scrollToGuide();
  });
  menu.prepend(item);
}

async function mountGuide(cfg) {
  const redoc = document.getElementById("redoc");
  const apiContent = await waitForElement(".api-content", redoc);
  const response = await fetch(cfg.guide, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  document.getElementById("api-intro")?.remove();
  const guide = document.createElement("section");
  guide.id = "api-intro";
  guide.className = "intro";
  guide.setAttribute("aria-label", cfg.guideLabel);
  guide.innerHTML = renderMarkdown(await response.text());

  const overview = apiContent.firstElementChild;
  if (overview?.nextSibling) apiContent.insertBefore(guide, overview.nextSibling);
  else apiContent.appendChild(guide);
  mountGuideMenu(cfg);
}

function setLang(lang) {
  const cfg = docs[lang] || docs.zh;
  document.documentElement.lang = cfg.htmlLang;
  document.title = cfg.title;
  document.getElementById("page-title").textContent = cfg.title;
  document.getElementById("page-subtitle").textContent = cfg.subtitle;

  for (const button of document.querySelectorAll(".lang-button")) {
    button.setAttribute("aria-pressed", String(button.dataset.lang === lang));
  }

  const redoc = document.getElementById("redoc");
  redoc.innerHTML = "";
  Redoc.init(
    cfg.spec,
    {
      hideDownloadButton: false,
      nativeScrollbars: true,
      pathInMiddlePanel: true,
      scrollYOffset: 58,
    },
    redoc,
    () => mountGuide(cfg).catch((error) => console.error(`${cfg.loadingError}:`, error)),
  );
}

for (const button of document.querySelectorAll(".lang-button")) {
  button.addEventListener("click", () => {
    const lang = button.dataset.lang;
    const url = new URL(window.location.href);
    if (lang === "zh") url.searchParams.delete("lang");
    else url.searchParams.set("lang", lang);
    window.history.replaceState({}, "", url);
    setLang(lang);
  });
}

setLang(readLang());
