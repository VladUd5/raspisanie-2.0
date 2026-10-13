// Подсказки в поиске и «недавно открытые». Без JS сайт работает: поиск — обычная форма.
(function () {
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  document.querySelectorAll("input[data-suggest]").forEach(function (input) {
    var box = document.createElement("ul"); box.className = "suggest"; box.hidden = true;
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
            return '<li><a href="' + esc(e.url) + '"><b>' + esc(e.label) + '</b> <span class="muted small">' + esc(e.kind) + (e.hint ? " · " + esc(e.hint) : "") + "</span></a></li>";
          }).join("");
          box.hidden = !items.length;
        }).catch(function () { box.hidden = true; });
      }, 150);
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

  var KEY = "recent-pages";
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } }
  var head = document.querySelector("[data-recent]");
  if (head) {
    var p = head.getAttribute("data-recent").split("|");
    var list = load().filter(function (x) { return x.url !== p[1]; });
    list.unshift({ title: p[0], url: p[1], hint: p[2] });
    try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, 6))); } catch (e) {}
  }
  var recent = document.getElementById("recent");
  if (recent) {
    var items = load();
    if (items.length) {
      document.getElementById("recent-list").innerHTML = items.map(function (x) {
        return '<li><a href="' + esc(x.url) + '"><b>' + esc(x.title) + '</b> <span class="muted small">' + esc(x.hint || "") + "</span></a></li>";
      }).join("");
      recent.hidden = false;
    }
  }
  var today = document.getElementById("today");
  if (today && !location.search) today.scrollIntoView({ block: "start" });
})();
