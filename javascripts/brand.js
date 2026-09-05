/* calcofi.io brand bridge (https://calcofi.io/brand/v2/) for mkdocs-material.
   theme.js resolves the cross-site theme and stamps data-md-color-scheme on
   <html>; material keys its css on the same attribute on <body> and stores the
   choice in localStorage "<site root>.__palette". this keeps the two agreeing:
   material's toggle is the radio inputs named __palette (one per palette entry). */
(function () {
  "use strict";
  var root = document.documentElement;
  function schemeOf(t) { return t === "dark" ? "slate" : "default"; }
  function themeOf(s) { return s === "slate" ? "dark" : "light"; }

  // brand -> material: select the palette entry matching the theme; clicking the
  // radio is what material listens for (it then sets <body> and writes __palette)
  function pushToMaterial(t) {
    var s = schemeOf(t);
    if (document.body.getAttribute("data-md-color-scheme") === s) return;
    var input = document.querySelector('input[name="__palette"][data-md-color-scheme="' + s + '"]');
    if (input) input.click(); else document.body.setAttribute("data-md-color-scheme", s);
  }

  // (a) on load the resolved theme wins (a ?theme= link, the cross-site cookie)
  pushToMaterial(root.dataset.theme === "dark" ? "dark" : "light");

  // (b) material's toggle -> brand: cookie, <html> attributes, cc:theme event
  document.querySelectorAll('input[name="__palette"]').forEach(function (input) {
    input.addEventListener("change", function () {
      var t = themeOf(input.getAttribute("data-md-color-scheme"));
      if (window.ccTheme && ccTheme.get() !== t) ccTheme.set(t);
    });
  });

  // (c) a brand toggle -> material, if a page ever adds one
  document.addEventListener("cc:theme", function (e) { pushToMaterial(e.detail.theme); });
})();
