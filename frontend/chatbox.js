(function () {
  'use strict';

  // =======================
  // Config
  // =======================
  var API_URL = "/chat/";
  var LEADS_URL = "/leads/";
  var CATALOG_URL = "https://ecolite.com.co/";
  var PAGE_SIZE = 5;

  // =======================
  // Estado / Refs
  // =======================
  function $id(x) { return document.getElementById(x); }
  var refs = {
    fab: null, panel: null, close: null, stream: null, input: null, send: null,
    tplShowMore: null, typing: null, leadOverlay: null, leadForm: null, leadSkip: null
  };
  var lastQuery = "";
  var page = 0;
  var __pending = 0;

  // =======================
  // Boot
  // =======================
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  function init() {
    wireRefs();
    wireOpenClose();
    wireChat();

    if (refs.typing) refs.typing.classList.add('is-hidden');

    // Mensaje de bienvenida (no abre overlay aún)
    if (refs.stream && !refs.stream.children.length) {
      appendBot(
        "👋 Bienvenido a Ecolite. Te ayudamos a elegir la iluminación LED ideal para tus proyectos. ¿Qué espacio deseas iluminar? (oficina, piscina, bodega…)\n" +
        "Ver página: " + CATALOG_URL
      );
    }

    // Mostrar overlay al cargar la página (si el panel ya está abierto)
    // y siempre al abrir el chat (ver openPanelHard)
    if (isPanelOpen()) showLeadOverlay();
  }

  function wireRefs() {
    refs.fab = $id("cbFab");
    refs.panel = $id("cbPanel");
    refs.close = $id("cbClose");
    refs.stream = $id("cbStream");
    refs.input = $id("cbInput");
    refs.send = $id("cbSend");
    refs.tplShowMore = $id("tplShowMore");
    refs.typing = $id("typing");
    refs.leadOverlay = $id("leadOverlay");
    refs.leadForm = $id("leadForm");
    refs.leadSkip = $id("leadSkip");

    // Observa por si el HTML se inserta tarde
    if (!refs.fab || !refs.panel || !refs.stream) {
      var obs = new MutationObserver(function () {
        refs.fab = refs.fab || $id("cbFab");
        refs.panel = refs.panel || $id("cbPanel");
        refs.stream = refs.stream || $id("cbStream");
        refs.input = refs.input || $id("cbInput");
        refs.send = refs.send || $id("cbSend");
        refs.close = refs.close || $id("cbClose");
        refs.tplShowMore = refs.tplShowMore || $id("tplShowMore");
        refs.typing = refs.typing || $id("typing");
        refs.leadOverlay = refs.leadOverlay || $id("leadOverlay");
        refs.leadForm = refs.leadForm || $id("leadForm");
        refs.leadSkip = refs.leadSkip || $id("leadSkip");
        if (refs.fab && refs.panel && refs.stream) {
          obs.disconnect();
          wireOpenClose();
        }
      });
      obs.observe(document.documentElement || document.body, { childList: true, subtree: true });
    }

    // Wire del overlay
    if (refs.leadForm) {
      refs.leadForm.addEventListener("submit", onLeadSubmit, { passive: false });
    }
    if (refs.leadSkip) {
      refs.leadSkip.addEventListener("click", function (e) {
        e.preventDefault();
        hideLeadOverlay();
      });
    }
  }

  // =======================
  // Abrir / Cerrar
  // =======================
  function hoistPanel() {
    if (refs.panel && refs.panel.parentElement !== document.body) {
      document.body.appendChild(refs.panel);
    }
  }
  function isPanelOpen() {
    return !!(refs.panel && refs.panel.classList.contains("open"));
  }

  function openPanelHard() {
    if (!refs.panel) return;
    hoistPanel();
    if (refs.fab) { refs.fab.style.zIndex = '2147483647'; }

    refs.panel.style.display = 'flex';
    refs.panel.classList.add("open");

    refs.panel.style.zIndex = '2147483647';
    refs.panel.style.opacity = '1';
    refs.panel.style.pointerEvents = 'auto';
    refs.panel.style.transform = 'translateY(0) scale(1)';
    refs.panel.style.position = 'fixed';
    refs.panel.style.right = '22px';
    refs.panel.style.bottom = '92px';

    setTimeout(function () { try { refs.input && refs.input.focus(); } catch (_) { } }, 60);

    // Mostrar SIEMPRE el overlay al abrir el chat
    showLeadOverlay();
  }

  function closePanel() {
    if (!refs.panel) return;
    refs.panel.classList.remove("open");
    if (refs.typing) refs.typing.classList.add('is-hidden');
    __pending = 0;
    refs.panel.style.opacity = '';
    refs.panel.style.pointerEvents = '';
    refs.panel.style.transform = '';
    refs.panel.style.position = '';
    refs.panel.style.right = '';
    refs.panel.style.bottom = '';
    refs.panel.style.zIndex = '';
    refs.panel.style.display = '';
  }

  function wireOpenClose() {
    if (refs.fab) refs.fab.onclick = function (e) { if (e) e.preventDefault(); openPanelHard(); };
    if (refs.close) refs.close.onclick = function (e) { if (e) e.preventDefault(); closePanel(); };

    if (refs.fab) {
      refs.fab.addEventListener("click", function (e) { e.preventDefault(); openPanelHard(); });
      refs.fab.addEventListener("touchstart", function (e) { e.preventDefault(); openPanelHard(); }, { passive: false });
    }
    if (refs.close) {
      refs.close.addEventListener("click", function (e) { e.preventDefault(); closePanel(); });
      refs.close.addEventListener("touchstart", function (e) { e.preventDefault(); closePanel(); }, { passive: false });
    }

    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || typeof t.closest !== "function") return;
      if (t.closest("#cbFab")) { e.preventDefault(); openPanelHard(); return; }
      if (t.closest("#cbClose")) { e.preventDefault(); closePanel(); return; }
    }, true);

    window.__ecoliteOpen = openPanelHard;
    window.__ecoliteClose = closePanel;
  }

  // =======================
  // Chat
  // =======================
  function wireChat() {
    if (refs.send && refs.input) {
      refs.send.addEventListener("click", function () { sendMessage(refs.input.value); });
      refs.send.addEventListener("touchstart", function (e) { e.preventDefault(); sendMessage(refs.input.value); }, { passive: false });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && document.activeElement === refs.input) {
        e.preventDefault();
        sendMessage(refs.input.value);
      }
    });
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || typeof t.closest !== "function") return;
      if (t.closest(".cb-cta")) { e.preventDefault(); sendMessage("más"); } // Ver más
    });
  }

  // ---------- UI utils ----------
  function showTyping() {
    __pending += 1;
    if (refs.typing) refs.typing.classList.remove('is-hidden');
  }
  function hideTyping() {
    __pending = Math.max(0, __pending - 1);
    if (__pending === 0 && refs.typing) refs.typing.classList.add('is-hidden');
  }
  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, function (m) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[m]; });
  }
  function linkify(s) {
    return (s || "").replace(/(https?:\/\/[^\s)]+)|(\bwww\.[^\s)]+)/gi, function (m) {
      var url = m.startsWith("http") ? m : ("https://" + m);
      return '<a class="cb-link" href="' + url + '" target="_blank" rel="noopener">' + m + '</a>';
    });
  }
function renderRichBotText(s) {
  var anchors = [];
  var raw = String(s || "");

  // 1) Detecta tokens [[a|Texto Visible|URL]] en el string RAW y los guarda como placeholders
  raw = raw.replace(/\[\[a\|([^|]+)\|([^\]]+)\]\]/gi, function (_, label, url) {
    var cleanUrl = (url || "").trim();
    if (!/^https?:\/\//i.test(cleanUrl)) cleanUrl = "https://" + cleanUrl;

    var html = '<a class="cb-link" href="' + escapeHtml(cleanUrl) + '" target="_blank" rel="noopener">' +
               escapeHtml(label) + '</a>';
    var idx = anchors.push(html) - 1;
    return "__A" + idx + "__"; // placeholder temporal
  });

  // 2) Escapar + linkify del resto del texto
  var safe = linkify(escapeHtml(raw));

  // 3) Reinyectar los anchors reales en los placeholders
  safe = safe.replace(/__A(\d+)__/g, function (_, i) { return anchors[+i] || ""; });

  return safe;
}

  function row(cls, htmlOrNode) {
    if (!refs.stream) return;
    var wrap = document.createElement("div");
    wrap.className = "msg " + cls;
    var b = document.createElement("div");
    b.className = "bubble";
    if (typeof htmlOrNode === "string") b.innerHTML = htmlOrNode; else b.appendChild(htmlOrNode);
    wrap.appendChild(b);
    refs.stream.appendChild(wrap);
    refs.stream.scrollTop = refs.stream.scrollHeight;
  }
  function appendUser(t) { row("me", escapeHtml(t)); }
  function appendBot(t) { row("", renderRichBotText(t)); }
  function appendSystem(t) { row("system", escapeHtml(t)); }
  function prettyPrice(v) {
    if (typeof v === "number" && isFinite(v)) {
      try { return new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 }).format(v); }
      catch { return String(v); }
    }
    if (typeof v === "string") return v.trim();
    return "";
  }
  function clearShowMore() {
    if (!refs.stream) return;
    var nodes = refs.stream.querySelectorAll(".cb-cta");
    for (var i = 0; i < nodes.length; i++) {
      var m = nodes[i].closest(".msg");
      if (m) m.remove();
    }
  }
  function renderProductCards(products, hasMore) {
    if (!Array.isArray(products) || !products.length) return;

    var list = document.createElement("div");
    list.className = "prod-inline";

    for (var i = 0; i < products.length; i++) {
      var p = products[i];

      var imgSrc = p.image || p.img_url || p.image_url || p.img || p.thumbnail || p.thumb || "";
      if (!imgSrc) {
        imgSrc = 'data:image/svg+xml;utf8,' + encodeURIComponent(
          '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160">' +
          '<rect width="100%" height="100%" fill="#f3f4f6"/>' +
          '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#9ca3af" font-family="sans-serif" font-size="14">Sin imagen</text>' +
          '</svg>'
        );
      }
      var title = p.title || p.name || "";
      var url = p.url || p.link || "#";
      var price = prettyPrice(p.price);

      var item = document.createElement("div");
      item.className = "prod-item";
      item.innerHTML =
        '<img src="' + imgSrc + '" alt="' + escapeHtml(title) + '"/>' +
        '<div class="prod-body">' +
        '<h4 class="margin:0 !important">' + escapeHtml(title) + '</h4>' +
        (price ? '<div class="prod-price">' + escapeHtml(price) + '</div>' : '') +
        '<a class="prod-link" href="' + url + '" target="_blank" rel="noopener">Ver producto</a>' +
        '</div>';

      list.appendChild(item);
    }

    row("", list);

    clearShowMore();
    if (hasMore && refs.tplShowMore) {
      var clone = refs.tplShowMore.content.cloneNode(true);
      refs.stream.appendChild(clone);
      refs.stream.scrollTop = refs.stream.scrollHeight;
    }
  }

  // ---------- Red / API ----------
  function getSessionId() {
    var KEY = "ecolite_session_id";
    var sid = localStorage.getItem(KEY);
    if (!sid) { sid = "web-" + Math.random().toString(36).slice(2); localStorage.setItem(KEY, sid); }
    return sid;
  }
  function callAPI(message, overridePage, onOk, onErr) {
    var payload = { session_id: getSessionId(), message: message, page: (overridePage == null ? page : overridePage) };
    var xhr = new XMLHttpRequest();

    showTyping();

    xhr.open("POST", API_URL, true);
    xhr.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
    xhr.onreadystatechange = function () {
      if (xhr.readyState === 4) {
        hideTyping();
        if (xhr.status >= 200 && xhr.status < 300) {
          try { onOk && onOk(JSON.parse(xhr.responseText)); }
          catch (e) { onErr && onErr(e); }
        } else {
          onErr && onErr(new Error("HTTP " + xhr.status + " " + (xhr.responseText || "")));
        }
      }
    };
    xhr.onerror = function () { hideTyping(); onErr && onErr(new Error("Network error")); };
    xhr.ontimeout = function () { hideTyping(); onErr && onErr(new Error("Timeout")); };
    try { xhr.send(JSON.stringify(payload)); }
    catch (e) { hideTyping(); onErr && onErr(e); }
  }

  // ---------- Formulario Overlay ----------
  function showLeadOverlay() {
    if (!refs.leadOverlay) return;
    refs.leadOverlay.hidden = false;
    // Foco en el primer input
    var first = refs.leadForm && refs.leadForm.elements.namedItem("name");
    if (first && typeof first.focus === "function") setTimeout(function(){ first.focus(); }, 60);
  }
  function hideLeadOverlay() {
    if (!refs.leadOverlay) return;
    refs.leadOverlay.hidden = true;
  }

  function onLeadSubmit(e) {
    e.preventDefault();
    e.stopPropagation();

    if (!refs.leadForm) return;

    var data = {
      session_id: getSessionId(),
      name: (refs.leadForm.elements.namedItem("name").value || "").trim(),
      email: (refs.leadForm.elements.namedItem("email").value || "").trim(),
      phone: (refs.leadForm.elements.namedItem("phone").value || "").trim(),
      profession: (refs.leadForm.elements.namedItem("profession").value || "").trim(),
      city: (refs.leadForm.elements.namedItem("city").value || "").trim(),
    };

    if (!data.name || !data.email || !data.phone || !data.profession || !data.city) {
      appendSystem("Por favor completa todos los campos.");
      return;
    }

    var btn = refs.leadForm.querySelector(".lead-submit");
    if (btn) btn.disabled = true;

    fetch(LEADS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json(); })
      .then(function (j) {
        appendBot("✅ Gracias, tus datos fueron guardados. ¿Qué necesitas iluminar hoy?");
        hideLeadOverlay(); // Se oculta ahora; volverá a salir la próxima vez que abras la página o el chat
      })
      .catch(function (err) {
        if (btn) btn.disabled = false;
        appendSystem("⚠️ No pude guardar tus datos: " + (err && err.message ? err.message : "error"));
      });
  }

  // ---------- Chat / Lógica ----------
  function sendMessage(text) {
    var msg = (text || "").trim();
    if (!msg) return;
    appendUser(msg);
    if (refs.input) refs.input.value = "";

    if (/^reset$/i.test(msg)) {
      page = 0; lastQuery = ""; clearShowMore();
      appendSystem('Sesión reiniciada. Pide algo como “panel 60x60”, “reflector 100W IP65”, “piscina”, “cintas led”.\nCatálogo: ' + CATALOG_URL);
      return;
    }

    var isMore = /\b(m[aá]s|siguiente|ver\s+m[aá]s|otra(?:s)?)\b/i.test(msg);
    var q = (isMore && lastQuery) ? lastQuery : msg;
    if (!isMore) { page = 0; clearShowMore(); }

    callAPI(q, page, function (data) {
      lastQuery = data.last_query || q;

      if (Array.isArray(data.products) && data.products.length) {
        renderProductCards(data.products, !!data.has_more);
        page += 1;
      } else {
        clearShowMore();
      }

      if (data.content) {
        appendBot(String(data.content));
      } else if (!data.products || !data.products.length) {
        appendBot('No encontré resultados. Prueba con: “panel”, “reflector”, “oficina”, “piscina” o visita ' + CATALOG_URL);
      }
    }, function (err) {
      appendSystem("⚠️ No me pude conectar. " + (err && err.message ? err.message : ""));
    });
  }

  // Exponer para debugging
  window.__ecoliteSend = sendMessage;

})();
