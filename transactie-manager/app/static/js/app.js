/* Transactie Manager — schermlogica.
   Geen externe bibliotheken: de toepassing moet ook werken zonder internet,
   bijvoorbeeld als add-on in Home Assistant. */

(function () {
  "use strict";

  /* Basispad; in Home Assistant draait de toepassing achter een ingress-prefix. */
  function basis() {
    return (document.body && document.body.dataset.basis) || "/";
  }

  /* ---------------------------------------------------------- keuzelijsten */
  /* Subcategorieën volgen de gekozen hoofdcategorie. */

  function vulLijst(select, opties, bewaarde) {
    select.innerHTML = "";
    var leeg = document.createElement("option");
    leeg.value = "";
    leeg.textContent = opties.length ? "— kies —" : "— geen —";
    select.appendChild(leeg);
    opties.forEach(function (optie) {
      var el = document.createElement("option");
      el.value = optie.id;
      el.textContent = optie.naam;
      if (String(optie.id) === String(bewaarde)) el.selected = true;
      select.appendChild(el);
    });
    select.disabled = opties.length === 0;
  }

  function haalKinderen(ouderId, klaar) {
    if (!ouderId) { klaar([]); return; }
    fetch(basis() + "api/categorieen?ouder_id=" + encodeURIComponent(ouderId), {
      headers: { "Accept": "application/json" }
    })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(klaar)
      .catch(function () { klaar([]); });
  }

  function koppelKeuzelijsten(wortel) {
    var hoofd = wortel.querySelector("[data-cat-niveau='0']");
    var sub = wortel.querySelector("[data-cat-niveau='1']");
    var subsub = wortel.querySelector("[data-cat-niveau='2']");
    if (!hoofd || !sub) return;

    function ververs(vanaf) {
      if (vanaf <= 0) {
        haalKinderen(hoofd.value, function (opties) {
          vulLijst(sub, opties, sub.dataset.gekozen || "");
          sub.dataset.gekozen = "";
          ververs(1);
        });
        return;
      }
      if (subsub) {
        haalKinderen(sub.value, function (opties) {
          vulLijst(subsub, opties, subsub.dataset.gekozen || "");
          subsub.dataset.gekozen = "";
        });
      }
    }

    hoofd.addEventListener("change", function () { ververs(0); });
    sub.addEventListener("change", function () { ververs(1); });

    // Bij het openen van een bestaand record staan de waarden al ingevuld.
    if (hoofd.value && (!sub.options.length || sub.options.length <= 1)) ververs(0);
  }

  /* Bij het wisselen tussen inkomst en uitgave blijven alleen de passende
     hoofdcategorieën over. */
  function koppelRichtingfilter(wortel) {
    var hoofd = wortel.querySelector("[data-cat-niveau='0']");
    var knoppen = wortel.querySelectorAll("[name='richting']");
    if (!hoofd || !knoppen.length) return;

    var alle = Array.prototype.map.call(hoofd.options, function (o) {
      return { waarde: o.value, tekst: o.textContent, soort: o.dataset.soort || "" };
    });

    function pas() {
      var gekozen = "uit";
      Array.prototype.forEach.call(knoppen, function (k) {
        if (k.type === "radio" ? k.checked : true) gekozen = k.value;
      });
      var huidig = hoofd.value;
      hoofd.innerHTML = "";
      alle.forEach(function (optie) {
        if (optie.waarde && optie.soort && optie.soort !== gekozen && optie.soort !== "beide") return;
        var el = document.createElement("option");
        el.value = optie.waarde;
        el.textContent = optie.tekst;
        el.dataset.soort = optie.soort;
        if (optie.waarde === huidig) el.selected = true;
        hoofd.appendChild(el);
      });
      if (hoofd.value !== huidig) hoofd.dispatchEvent(new Event("change"));
    }

    Array.prototype.forEach.call(knoppen, function (k) {
      k.addEventListener("change", pas);
    });
    pas();
  }

  /* ------------------------------------------------- uitklapbare jaartabel */

  function koppelBoomtabel(tabel) {
    var rijen = Array.prototype.slice.call(tabel.querySelectorAll("tr.boomrij"));

    function zetZichtbaar(sleutel, open) {
      rijen.forEach(function (rij) {
        if (rij.dataset.ouder !== sleutel) return;
        rij.classList.toggle("verborgen", !open);
        if (!open) {
          var knop = rij.querySelector(".uitklap");
          if (knop) {
            knop.textContent = "▸";
            knop.setAttribute("aria-expanded", "false");
          }
          zetZichtbaar(rij.dataset.sleutel, false);
        }
      });
    }

    tabel.addEventListener("click", function (gebeurtenis) {
      var knop = gebeurtenis.target.closest(".uitklap");
      if (!knop) return;
      var rij = knop.closest("tr");
      var open = knop.getAttribute("aria-expanded") !== "true";
      knop.setAttribute("aria-expanded", open ? "true" : "false");
      knop.textContent = open ? "▾" : "▸";
      zetZichtbaar(rij.dataset.sleutel, open);
    });

    // Standaard: alles boven niveau 0 dichtgeklapt.
    rijen.forEach(function (rij) {
      if (rij.dataset.ouder !== "") rij.classList.add("verborgen");
    });
  }

  /* ------------------------------------------------------------- grafieken */

  var PALET = ["#1f4fa8", "#12694a", "#9e2b25", "#a9721a", "#55337f", "#0f7285",
               "#7a5c1e", "#4a5a72", "#8c3f6d", "#356b2f", "#a34a1c", "#2d4c8a"];

  function tekenLijngrafiek(doel) {
    var gegevens = JSON.parse(doel.dataset.reeksen || "{}");
    var labels = gegevens.labels || [];
    var series = gegevens.series || [];
    if (!labels.length || !series.length) return;

    var breedte = 900, hoogte = 380;
    var marge = { boven: 16, rechts: 18, onder: 40, links: 72 };
    var vlakB = breedte - marge.links - marge.rechts;
    var vlakH = hoogte - marge.boven - marge.onder;

    var max = 0;
    series.forEach(function (reeks) {
      reeks.waarden.forEach(function (w) { if (w > max) max = w; });
    });
    if (max <= 0) max = 1;
    var stap = Math.pow(10, Math.floor(Math.log10(max)));
    var bovengrens = Math.ceil(max / stap) * stap;

    function x(i) {
      return marge.links + (labels.length === 1 ? vlakB / 2 : (vlakB * i) / (labels.length - 1));
    }
    function y(waarde) { return marge.boven + vlakH - (vlakH * waarde) / bovengrens; }

    var svg = ['<svg viewBox="0 0 ' + breedte + " " + hoogte +
      '" class="grafiek" role="img" aria-label="Evolutie per categorie">'];

    for (var t = 0; t <= 4; t++) {
      var waarde = (bovengrens / 4) * t;
      var yy = y(waarde);
      svg.push('<line x1="' + marge.links + '" y1="' + yy + '" x2="' +
        (breedte - marge.rechts) + '" y2="' + yy + '" stroke="#dbe1e9" stroke-width="1"/>');
      svg.push('<text x="' + (marge.links - 8) + '" y="' + (yy + 4) +
        '" text-anchor="end" font-size="11" fill="#5a6675">' +
        waarde.toLocaleString("nl-BE", { maximumFractionDigits: 0 }) + "</text>");
    }

    labels.forEach(function (label, i) {
      svg.push('<text x="' + x(i) + '" y="' + (hoogte - 14) +
        '" text-anchor="middle" font-size="11" fill="#5a6675">' + label + "</text>");
    });

    series.forEach(function (reeks, index) {
      var kleur = PALET[index % PALET.length];
      var punten = reeks.waarden.map(function (w, i) { return x(i) + "," + y(w); });
      svg.push('<polyline fill="none" stroke="' + kleur + '" stroke-width="2" ' +
        'stroke-linejoin="round" points="' + punten.join(" ") + '"/>');
      reeks.waarden.forEach(function (w, i) {
        svg.push('<circle cx="' + x(i) + '" cy="' + y(w) + '" r="3" fill="' + kleur + '">' +
          "<title>" + reeks.naam + " " + labels[i] + ": " +
          w.toLocaleString("nl-BE", { minimumFractionDigits: 2 }) + " EUR</title></circle>");
      });
    });

    svg.push("</svg>");
    doel.innerHTML = svg.join("");

    var legende = doel.parentNode.querySelector(".legende");
    if (legende) {
      legende.innerHTML = series.map(function (reeks, index) {
        return '<span><i style="background:' + PALET[index % PALET.length] + '"></i>' +
          reeks.naam + "</span>";
      }).join("");
    }
  }

  /* ------------------------------------------------------------ AI-voorstel */

  function koppelAiKnoppen() {
    document.querySelectorAll("[data-ai-voor]").forEach(function (knop) {
      knop.addEventListener("click", function () {
        var txId = knop.dataset.aiVoor;
        var doel = document.querySelector('[data-ai-uitvoer="' + txId + '"]');
        knop.disabled = true;
        var oud = knop.textContent;
        knop.textContent = "Bezig…";
        fetch(basis() + "api/ai-voorstel/" + txId, { method: "POST" })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
          .then(function (antwoord) {
            if (!doel) return;
            if (!antwoord.ok) {
              doel.textContent = antwoord.d.fout || "Het model gaf geen antwoord.";
              doel.className = "klein-detail";
              return;
            }
            doel.innerHTML = "Voorstel: <strong>" + antwoord.d.pad + "</strong> (" +
              Math.round(antwoord.d.zekerheid * 100) + "% zeker). " +
              "Open de transactie om dit te bevestigen.";
          })
          .catch(function () {
            if (doel) doel.textContent = "Het model is niet bereikbaar.";
          })
          .finally(function () {
            knop.disabled = false;
            knop.textContent = oud;
          });
      });
    });
  }

  /* ------------------------------------------------------------------ start */

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-categoriekiezer]").forEach(function (wortel) {
      koppelKeuzelijsten(wortel);
      koppelRichtingfilter(wortel);
    });
    document.querySelectorAll("[data-boomtabel]").forEach(koppelBoomtabel);
    document.querySelectorAll("[data-lijngrafiek]").forEach(tekenLijngrafiek);
    koppelAiKnoppen();

    document.querySelectorAll("[data-bevestig]").forEach(function (formulier) {
      formulier.addEventListener("submit", function (gebeurtenis) {
        if (!window.confirm(formulier.dataset.bevestig)) gebeurtenis.preventDefault();
      });
    });
  });
})();
