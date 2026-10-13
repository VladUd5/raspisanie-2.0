// Подсказки поиска, дни недели на телефоне, подробности занятия, недавние и закреплённые страницы.
// Без JS сайт работает: поиск — обычная форма, дни — ссылки, подробности — <details>.
(function () {
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function load(key) { try { return JSON.parse(localStorage.getItem(key) || "[]"); } catch (e) { return []; } }
  function save(key, list) { try { localStorage.setItem(key, JSON.stringify(list)); } catch (e) {} }

  // ── подсказки поиска
  document.querySelectorAll("input[data-suggest]").forEach(function (input) {
    var box = document.createElement("ul"); box.className = "suggest"; box.hidden = true;
    box.setAttribute("role", "listbox");
    input.parentNode.appendChild(box);
    var timer, active = -1;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { box.hidden = true; return; }
      timer = setTimeout(function () {
        fetch("/api/search?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (items) {
          active = -1;
          box.innerHTML = items.map(function (e) {
            return '<li><a href="' + esc(e.url) + '"><b>' + esc(e.label) + "</b><span>" + esc(e.kind) + (e.hint ? " · " + esc(e.hint) : "") + "</span></a></li>";
          }).join("");
          box.hidden = !items.length;
        }).catch(function () { box.hidden = true; });
      }, 120);
    });
    input.addEventListener("keydown", function (ev) {
      var links = box.querySelectorAll("a");
      if (box.hidden || !links.length) return;
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        active = (active + (ev.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
        links.forEach(function (a, i) { a.classList.toggle("active", i === active); });
      } else if (ev.key === "Enter" && active >= 0) { ev.preventDefault(); location.href = links[active].href; }
      else if (ev.key === "Escape") { box.hidden = true; }
    });
    document.addEventListener("click", function (ev) { if (!box.contains(ev.target) && ev.target !== input) box.hidden = true; });
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "/" || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
    var input = document.querySelector("input[data-suggest]");
    if (input) { ev.preventDefault(); input.focus(); }
  });

  // ── дни недели на телефоне: переключаем без перезагрузки
  var wk = document.querySelector("[data-wk]");
  if (wk) {
    wk.querySelectorAll(".wk-day").forEach(function (a) {
      a.addEventListener("click", function (ev) {
        if (!window.matchMedia("(max-width: 900px)").matches) return;
        ev.preventDefault();
        wk.setAttribute("data-show", a.getAttribute("data-day"));
        wk.querySelectorAll(".wk-day").forEach(function (x) { x.removeAttribute("aria-current"); });
        a.setAttribute("aria-current", "true");
        history.replaceState(null, "", a.getAttribute("href").split("#")[0]);
      });
    });
  }

  // ── подробности занятия: открыта одна, закрываются по Esc и щелчку мимо
  var lessons = document.querySelectorAll("details.ls");
  lessons.forEach(function (d) {
    d.addEventListener("toggle", function () {
      if (d.open) lessons.forEach(function (o) { if (o !== d) o.open = false; });
    });
  });
  document.addEventListener("click", function (ev) {
    if (!ev.target.closest("details.ls")) lessons.forEach(function (o) { o.open = false; });
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") lessons.forEach(function (o) { if (o.open) { o.open = false; o.querySelector("summary").focus(); } });
  });

  // ── недавние и закреплённые
  var head = document.querySelector("[data-recent]");
  var me = null;
  if (head) {
    var p = head.getAttribute("data-recent").split("|");
    me = { title: p[0], url: p[1], hint: p[2] };
    var recent = load("recent-pages").filter(function (x) { return x.url !== me.url; });
    recent.unshift(me);
    save("recent-pages", recent.slice(0, 8));
    var star = document.querySelector("[data-star]");
    if (star) {
      var pinned = function () { return load("pinned-pages").some(function (x) { return x.url === me.url; }); };
      star.hidden = false;
      star.setAttribute("aria-pressed", pinned() ? "true" : "false");
      star.addEventListener("click", function () {
        var list = load("pinned-pages").filter(function (x) { return x.url !== me.url; });
        if (!pinned()) list.unshift(me);
        save("pinned-pages", list.slice(0, 12));
        star.setAttribute("aria-pressed", pinned() ? "true" : "false");
      });
    }
  }
  function tiles(id, items) {
    var box = document.getElementById(id);
    if (!box || !items.length) return;
    document.getElementById(id + "-list").innerHTML = items.map(function (x) {
      return '<a href="' + esc(x.url) + '"><b>' + esc(x.title) + "</b><span>" + esc(x.hint || "") + "</span></a>";
    }).join("");
    box.hidden = false;
  }
  var pins = load("pinned-pages");
  tiles("pinned", pins);
  tiles("recent", load("recent-pages").filter(function (x) { return !pins.some(function (p) { return p.url === x.url; }); }).slice(0, 6));
})();
