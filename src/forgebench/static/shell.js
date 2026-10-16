/* ForgeBench · shell — section routing + ⌘K jump palette.
   Keeps the single-page app's behaviour; adds the navigation the views imply. */
(function () {
  "use strict";

  var VIEW_KEY = "fb-view";

  var views = Array.prototype.slice.call(document.querySelectorAll(".view[data-view]"));
  var links = Array.prototype.slice.call(document.querySelectorAll(".rail-link[data-view]"));
  var main = document.getElementById("workspace");

  if (!views.length) return;

  var known = views.map(function (v) {
    return v.dataset.view;
  });

  /* ---------- Section routing ---------- */

  function activate(id, opts) {
    if (known.indexOf(id) === -1) id = known[0];

    views.forEach(function (v) {
      v.classList.toggle("is-active", v.dataset.view === id);
    });

    links.forEach(function (l) {
      var on = l.dataset.view === id;
      l.classList.toggle("is-active", on);
      if (on) {
        l.setAttribute("aria-current", "page");
      } else {
        l.removeAttribute("aria-current");
      }
    });

    try {
      localStorage.setItem(VIEW_KEY, id);
    } catch (e) {
      /* storage unavailable — routing still works for this session */
    }

    if (window.history && history.replaceState) {
      history.replaceState(null, "", "#" + id);
    }

    if (opts && opts.focus && main) {
      main.setAttribute("tabindex", "-1");
      main.focus({ preventScroll: true });
      main.scrollIntoView({ block: "start" });
    }
  }

  function fromHash() {
    var id = (location.hash || "").replace(/^#/, "");
    return known.indexOf(id) !== -1 ? id : null;
  }

  function initialView() {
    var stored = null;
    try {
      stored = localStorage.getItem(VIEW_KEY);
    } catch (e) {
      stored = null;
    }
    return fromHash() || (known.indexOf(stored) !== -1 ? stored : null) || known[0];
  }

  links.forEach(function (link) {
    link.addEventListener("click", function () {
      activate(link.dataset.view, { focus: true });
    });
  });

  window.addEventListener("hashchange", function () {
    var id = fromHash();
    if (id) activate(id);
  });

  activate(initialView());

  /* ---------- Command palette (⌘K) ---------- */

  var palette = document.getElementById("palette");
  var input = document.getElementById("palette-input");
  var list = document.getElementById("palette-list");
  var trigger = document.getElementById("btn-palette");

  var items = links.map(function (l) {
    return {
      id: l.dataset.view,
      label: l.dataset.label || l.textContent.trim(),
      num: (l.querySelector(".rail-num") || {}).textContent || "",
      run: function () {
        activate(l.dataset.view, { focus: true });
      },
    };
  });

  items.push({
    id: "docs",
    label: "Open API docs",
    num: "↗",
    run: function () {
      window.open("/docs", "_blank", "noopener");
    },
  });

  var visible = items.slice();
  var activeIndex = 0;
  var lastFocus = null;

  function render(filter) {
    var q = (filter || "").trim().toLowerCase();
    visible = !q
      ? items.slice()
      : items.filter(function (it) {
          return (it.label + " " + it.id + " " + it.num).toLowerCase().indexOf(q) !== -1;
        });
    if (activeIndex >= visible.length) activeIndex = Math.max(0, visible.length - 1);

    if (!visible.length) {
      list.innerHTML = '<li class="pal-empty">No matches</li>';
      return;
    }

    list.innerHTML = visible
      .map(function (it, i) {
        return (
          '<li class="pal-item' +
          (i === activeIndex ? " is-active" : "") +
          '" role="option" aria-selected="' +
          (i === activeIndex) +
          '" data-view="' +
          it.id +
          '" data-index="' +
          i +
          '"><span class="pal-num">' +
          it.num +
          "</span><span>" +
          it.label +
          "</span></li>"
        );
      })
      .join("");
  }

  function move(delta) {
    if (!visible.length) return;
    activeIndex = (activeIndex + delta + visible.length) % visible.length;
    render(input.value);
  }

  function choose() {
    var it = visible[activeIndex];
    if (!it) return;
    close();
    it.run();
  }

  function open() {
    lastFocus = document.activeElement;
    palette.hidden = false;
    input.value = "";
    activeIndex = 0;
    render("");
    input.focus();
  }

  function close() {
    if (palette.hidden) return;
    palette.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  if (palette && input && list) {
    if (trigger) trigger.addEventListener("click", open);

    input.addEventListener("input", function () {
      activeIndex = 0;
      render(input.value);
    });

    list.addEventListener("mousemove", function (e) {
      var li = e.target.closest(".pal-item");
      if (!li) return;
      var i = Number(li.dataset.index);
      if (i !== activeIndex) {
        activeIndex = i;
        render(input.value);
      }
    });

    list.addEventListener("click", function (e) {
      var li = e.target.closest(".pal-item");
      if (!li) return;
      activeIndex = Number(li.dataset.index);
      choose();
    });

    palette.addEventListener("mousedown", function (e) {
      if (e.target.hasAttribute("data-palette-close")) close();
    });

    document.addEventListener("keydown", function (e) {
      var key = e.key ? e.key.toLowerCase() : "";
      if ((e.metaKey || e.ctrlKey) && key === "k") {
        e.preventDefault();
        palette.hidden ? open() : close();
        return;
      }
      if (palette.hidden) return;
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        move(1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        move(-1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        choose();
      }
    });
  }

  /* ---------- Live status mirror ---------- */

  var statusKey = document.getElementById("status-key");
  var statusModel = document.getElementById("status-model");
  var chipKey = document.getElementById("chip-key");
  var chipModel = document.getElementById("chip-model");
  var dot = document.getElementById("rail-dot");
  var dotLabel = document.getElementById("rail-dot-label");

  function mirror() {
    var keyText = statusKey ? statusKey.textContent.trim() : "";
    var set = keyText && keyText !== "—" && keyText.indexOf("(not set)") === -1;

    if (chipKey) {
      chipKey.textContent = keyText || "—";
      chipKey.hidden = !set;
    }
    if (chipModel) {
      chipModel.textContent = statusModel ? statusModel.textContent.trim() : "—";
      chipModel.hidden = !statusModel;
    }
    if (dot) dot.dataset.state = set ? "set" : "none";
    if (dotLabel) dotLabel.textContent = set ? "key set" : "key not set";
  }

  if (statusKey || statusModel) {
    if (window.MutationObserver) {
      var obs = new MutationObserver(mirror);
      [statusKey, statusModel].forEach(function (el) {
        if (el) obs.observe(el, { childList: true, characterData: true, subtree: true });
      });
    }
    mirror();
    setTimeout(mirror, 600);
  }
})();
