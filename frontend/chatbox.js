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
  // Estilos de validación (inyectados)
  // =======================
  function injectValidationStyles() {
    if (document.getElementById("ecolite-validation-styles")) return;

    var css = `
    /* === Estados inválidos para el formulario del chat === */
    #leadForm input.invalid,
    #leadForm select.invalid,
    #leadForm textarea.invalid {
      border-color: #DC2626 !important;
      box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.15);
      transition: border-color .15s ease, box-shadow .15s ease;
    }
    #leadForm input.invalid:focus,
    #leadForm select.invalid:focus,
    #leadForm textarea.invalid:focus {
      outline: 2px solid #DC2626;
      outline-offset: 2px;
    }
    #leadForm .field-error {
      color: #DC2626;
      font-size: 12px;
      margin-top: 4px;
      line-height: 1.25;
    }
    /* Efecto sutil al marcar error */
    #leadForm input.invalid,
    #leadForm select.invalid,
    #leadForm textarea.invalid {
      animation: ecoliteInvalid .15s ease-in;
    }
    @keyframes ecoliteInvalid {
      from { transform: translateY(-1px); }
      to   { transform: translateY(0); }
    }`;

    var style = document.createElement("style");
    style.id = "ecolite-validation-styles";
    style.type = "text/css";
    style.appendChild(document.createTextNode(css));
    document.head.appendChild(style);
  }

  // =======================
  // Boot
  // =======================
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  function init() {
    injectValidationStyles(); // ← inyecta estilos para .invalid y .field-error

    wireRefs();
    wireOpenClose();
    wireChat();

    if (refs.typing) refs.typing.classList.add('is-hidden');

    // Mensaje de bienvenida
    if (refs.stream && !refs.stream.children.length) {
      appendBot(
        "👋 Bienvenido a Ecolite. Te ayudamos a elegir la iluminación LED ideal para tus proyectos. ¿Qué espacio deseas iluminar? (oficina, piscina, bodega…)\n" +
        "Ver página: " + CATALOG_URL
      );
    }

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
      // Validaciones & constraints
      setupLeadValidation();

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

    // Mostrar SIEMPRE el overlay al abrir
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

  // =======================
  // WhatsApp helpers
  // =======================
  function getLeadName() {
    try { return (localStorage.getItem("ecolite_lead_name") || "").trim(); }
    catch (_) { return ""; }
  }

  function normalizePhone(raw) {
    return String(raw || "").replace(/[^\d]/g, ""); // deja solo dígitos
  }
  function extractPhoneFromUrl(u) {
    // wa.me/<phone>
    if (/wa\.me$/i.test(u.hostname)) {
      var seg = (u.pathname || "").split("/").filter(Boolean);
      if (seg.length) return normalizePhone(seg[0]);
    }
    // api.whatsapp.com/send?phone=<phone> | phoneNumber=
    var p = new URLSearchParams(u.search);
    if (p.get("phone")) return normalizePhone(p.get("phone"));
    if (p.get("phoneNumber")) return normalizePhone(p.get("phoneNumber"));
    return "";
  }
  function isWhatsAppHost(host) {
    return /(^|\.)(wa\.me|whatsapp\.com)$/.test(String(host || "").toLowerCase());
  }
  function isAndroid() { return /Android/i.test(navigator.userAgent || ""); }
  function isIOS() { return /iPhone|iPad|iPod/i.test(navigator.userAgent || ""); }

  // =======================
  // Decorador de URLs → WA con nombre + mensaje
  // =======================
function maybeDecorateWhatsApp(link) {
  const name = getLeadName();
  // último texto que escribió el usuario (ya lo guardas aquí):
  // window.__ecoliteLastQuery se setea después de cada respuesta del backend
  // (no toques eso)
  let last = (window.__ecoliteLastQuery || "").trim().toLowerCase();

  // 1) Limpia saludos/política al inicio
  //    ej: "hola,", "buenas tardes:", "por favor ..."
  last = last
    .replace(/^\s*(hola|buenas(?:\s+(tardes|noches|d[ií]as))?|buenos\s+d[ií]as)\s*[,;:\-]?\s*/i, "")
    .replace(/^\s*(por\s+favor|porfa|porfis)\s*[,;:\-]?\s*/i, "")
    .trim();

  // 2) Si arranca con "sugiereme / recomiéndame", quítalo
  last = last
    .replace(/^\s*(sugiereme|sugiéreme|recomiendame|recomiéndame)\b\s*/i, "")
    .trim();

  // 3) Decide la forma natural del "topic"
  let topic;
  if (!last) {
    topic = "quiero cotizar";
  } else if (/^(quiero|necesito|busco|me\s+gustar[ií]a|deseo|quisiera)\b/i.test(last)) {
    // El usuario ya dijo "quiero/necesito/busco..."
    topic = last;
  } else if (/^(estoy|soy)\s+interesad[ao]\s+en\b/i.test(last)) {
    // Ya viene con "estoy interesado en ..."
    topic = last;
  } else {
    topic = "estoy interesado en " + last;
  }

  // 4) Mensaje final (evita dobles "Hola")
  let text = name ? ("Hola, soy " + name + ". " + topic) : ("Hola, " + topic);

  // 5) Adjunta el ?text= al link (base debe ser wa.me/NUMERO)
  const encoded = encodeURIComponent(text);
  if (link.includes("?")) link += "&text=" + encoded;
  else link += "?text=" + encoded;
  return link;
}




  function linkify(s) {
    return (s || "").replace(/(https?:\/\/[^\s)]+)|(\bwww\.[^\s)]+)/gi, function (m) {
      var url = m.startsWith("http") ? m : ("https://" + m);
      url = maybeDecorateWhatsApp(url);
var target = "_blank";
      return '<a class="cb-link" href="' + url + '" target="' + target + '" rel="noopener">' + m + '</a>';
    });
  }

  function renderRichBotText(s) {
    var anchors = [];
    var raw = String(s || "");

    raw = raw.replace(/\[\[a\|([^|]+)\|([^\]]+)\]\]/gi, function (_, label, url) {
      var cleanUrl = (url || "").trim();
      if (!/^https?:\/\//i.test(cleanUrl)) cleanUrl = "https://" + cleanUrl;
      cleanUrl = maybeDecorateWhatsApp(cleanUrl); 

      var target = "_blank";
      try {
        var H = new URL(cleanUrl).hostname;
        var target = "_blank"; 
      } catch (_) {}

      var html = '<a class="cb-link" href="' + escapeHtml(cleanUrl) + '" target="' + target + '" rel="noopener">' +
                 escapeHtml(label) + '</a>';
      var idx = anchors.push(html) - 1;
      return "__A" + idx + "__"; 
    });

    var safe = linkify(escapeHtml(raw));

    safe = safe.replace(/__A(\d+)__/g, function (_, i) { return anchors[+i] || ""; });

    return safe;
  }

  function buildWhatsAppLinksFromHref(href) {
    try {
      var u = new URL(href);
      if (!isWhatsAppHost(u.hostname)) return null;

      var web = maybeDecorateWhatsApp(href);
      var U = new URL(web);
      var phone = extractPhoneFromUrl(U);
      var params = new URLSearchParams(U.search);
      var text = params.get("text") || "";

      var deep = phone
        ? ("whatsapp://send?phone=" + phone + "&text=" + encodeURIComponent(text))
        : ("whatsapp://send?text=" + encodeURIComponent(text));

      // Intent (Android)
      var androidIntent = phone
        ? ("intent://send?phone=" + phone + "&text=" + encodeURIComponent(text) + "#Intent;scheme=whatsapp;package=com.whatsapp;end")
        : ("intent://send?text=" + encodeURIComponent(text) + "#Intent;scheme=whatsapp;package=com.whatsapp;end");

      return { deep: deep, web: web, intent: androidIntent, phone: phone };
    } catch {
      return null;
    }
  }

  function tryOpenWhatsApp(links) {
    if (!links) return;

    var opened = false;
    var onVis = function () { opened = true; cleanup(); };
    function cleanup() {
      clearTimeout(tid);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pagehide", onVis);
      window.removeEventListener("blur", onVis);
    }
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("pagehide", onVis);
    window.addEventListener("blur", onVis);

  if (isAndroid()) {
    window.location.href = links.intent; 
  } else if (isIOS()) {
    window.open(links.web, "_blank");
  } else {
    window.open(links.web, "_blank");
  }


    var tid = setTimeout(function () {
      if (!opened) window.open(links.web, "_blank"); 
      cleanup();
    }, 1200);
  }

  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest && e.target.closest("a.cb-link");
    if (!a) return;

    var href = a.getAttribute("href");
    try {
      var host = new URL(href).hostname;
      if (!isWhatsAppHost(host)) return;
    } catch (_) { return; }

    e.preventDefault();
    var links = buildWhatsAppLinksFromHref(href);
    tryOpenWhatsApp(links);
  }, true);

  function setupLeadValidation() {
    var f = refs.leadForm;
    if (!f) return;

    f.setAttribute('novalidate', 'novalidate');

    var name = f.elements.namedItem("name");
    var email = f.elements.namedItem("email");
    var phone = f.elements.namedItem("phone");
    var profession = f.elements.namedItem("profession");
    var city = f.elements.namedItem("city");

if (name) {
  name.required = true;
  name.maxLength = 60;
  name.inputMode = "text";
  name.pattern = "[A-Za-zÁÉÍÓÚáéíóúÑñÜü.\\-\\s]{2,60}";
  name.autocapitalize = "words";
  name.placeholder = name.placeholder || "Nombre y apellido";

  name.addEventListener("input", function () {
    var v = this.value;
    v = v.replace(/[^A-Za-zÁÉÍÓÚáéíóúÑñÜü.\-\s]/g, ""); 
    v = v.replace(/\s+/g, " ").replace(/^[\s-]+/, ""); 
    this.value = v;
    clearFieldError(this);
  });

  name.addEventListener("blur", function(){ validateField("name"); });
}

    if (email) {
      email.required = true;
      email.inputMode = "email";
      email.placeholder = email.placeholder || "correo@ejemplo.com";
      email.addEventListener("input", function(){ clearFieldError(this); });
      email.addEventListener("blur", function(){ validateField("email"); });
    }
    if (phone) {
      phone.required = true;
      phone.inputMode = "numeric";
      phone.pattern = "\\d*";
      phone.maxLength = 13; 
      phone.placeholder = phone.placeholder || "Celular (10 dígitos)";
      phone.addEventListener("input", function () {
        var digits = this.value.replace(/\D+/g, "");
        if (digits.length > 13) digits = digits.slice(0, 13);
        this.value = digits;
        clearFieldError(this);
      });
      phone.addEventListener("blur", function(){ validateField("phone"); });
    }
    if (profession) {
      profession.required = true;
      profession.maxLength = 60;
      profession.autocapitalize = "words";
      profession.addEventListener("input", function () {
        this.value = this.value.replace(/\s+/g, " ").replace(/^[\s-]+/, "");
        clearFieldError(this);
      });
      profession.addEventListener("blur", function(){ validateField("profession"); });
    }
if (city) {
  city.required = true;
  city.maxLength = 60;
  city.inputMode = "text";
  city.pattern = "[A-Za-zÁÉÍÓÚáéíóúÑñÜü.\\-\\s]{2,60}";
  city.autocapitalize = "words";

  city.addEventListener("input", function () {
    var v = this.value;
    v = v.replace(/[^A-Za-zÁÉÍÓÚáéíóúÑñÜü.\-\s]/g, ""); 
    v = v.replace(/\s+/g, " ").replace(/^[\s-]+/, ""); 
    this.value = v;
    clearFieldError(this);
  });

  city.addEventListener("blur", function(){ validateField("city"); });
}

  }

  function fieldEl(name) {
    return refs.leadForm && refs.leadForm.elements.namedItem(name);
  }

  function getOrCreateErrorNode(el) {
    if (!el) return null;
    var next = el.nextElementSibling;
    if (next && next.classList && next.classList.contains("field-error")) return next;
    var div = document.createElement("div");
    div.className = "field-error";
    div.style.color = "#DC2626";
    div.style.fontSize = "12px";
    div.style.marginTop = "4px";
    el.parentNode.insertBefore(div, el.nextSibling);
    return div;
  }

  function showFieldError(el, msg) {
    if (!el) return;
    el.classList.add("invalid");
    el.setAttribute("aria-invalid", "true");
    var node = getOrCreateErrorNode(el);
    if (node) node.textContent = msg || "Campo inválido";
  }

  function clearFieldError(el) {
    if (!el) return;
    el.classList.remove("invalid");
    el.removeAttribute("aria-invalid");
    var next = el.nextElementSibling;
    if (next && next.classList && next.classList.contains("field-error")) {
      next.textContent = "";
    }
  }

  function clearAllErrors() {
    if (!refs.leadForm) return;
    ["name","email","phone","profession","city"].forEach(function(n){
      clearFieldError(fieldEl(n));
    });
  }

  function validateField(name) {
    var el = fieldEl(name);
    if (!el) return true;

    var v = (el.value || "").trim();
    var onlyLetters = /^[A-Za-zÁÉÍÓÚáéíóúÑñÜü.\-\s]{2,60}$/;
    var emailRx = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
    var phoneRx = /^\d{10}$/;

    if (name === "name") {
      if (!onlyLetters.test(v)) { showFieldError(el, "Usa solo letras y mínimo 2 caracteres."); return false; }
      return true;
    }
    if (name === "email") {
      if (!emailRx.test(v)) { showFieldError(el, "Email no válido."); return false; }
      return true;
    }
    if (name === "phone") {
      if (!phoneRx.test(v)) { showFieldError(el, "Debe tener 10 dígitos numéricos."); return false; }
      return true;
    }
    if (name === "profession") {
      if (!onlyLetters.test(v)) { showFieldError(el, "Usa solo letras (mínimo 2)."); return false; }
      return true;
    }
    if (name === "city") {
      if (!onlyLetters.test(v)) { showFieldError(el, "Usa solo letras (mínimo 2)."); return false; }
      return true;
    }
    return true;
  }

  function validateLeadForm() {
    clearAllErrors();
    var ok = true;
    ["name","email","phone","profession","city"].forEach(function(n){
      if (!validateField(n)) ok = false;
    });
    if (!ok) {
      for (var i=0;i<5;i++){
        var nm = ["name","email","phone","profession","city"][i];
        var el = fieldEl(nm);
        var err = el && el.nextElementSibling && el.nextElementSibling.classList.contains("field-error") && el.nextElementSibling.textContent;
        if (err) { try { el.focus(); } catch(_){} break; }
      }
    }
    return ok;
  }

  function showLeadOverlay() {
    if (!refs.leadOverlay) return;
    refs.leadOverlay.hidden = false;
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

    // Validación
    if (!validateLeadForm()) {
      return;
    }

    var data = {
      session_id: getSessionId(),
      name: (refs.leadForm.elements.namedItem("name").value || "").trim(),
      email: (refs.leadForm.elements.namedItem("email").value || "").trim(),
      phone: (refs.leadForm.elements.namedItem("phone").value || "").trim(),
      profession: (refs.leadForm.elements.namedItem("profession").value || "").trim(),
      city: (refs.leadForm.elements.namedItem("city").value || "").trim(),
    };

    try { localStorage.setItem("ecolite_lead_name", data.name || ""); } catch (_e) {}

    var btn = refs.leadForm.querySelector(".lead-submit");
    if (btn) btn.disabled = true;

    fetch(LEADS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json(); })
      .then(function () {
        appendBot("✅ Gracias, tus datos fueron guardados.");
        hideLeadOverlay();
      })
      .catch(function (err) {
        if (btn) btn.disabled = false;
        appendSystem("⚠️ No pude guardar tus datos: " + (err && err.message ? err.message : "error"));
      });
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

  // =======================
  // Red / API
  // =======================
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

  // =======================
  // Chat / Lógica
  // =======================
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
      window.__ecoliteLastQuery = lastQuery; // opcional para WA

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
