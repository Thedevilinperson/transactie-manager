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
    leeg.textContent = select.dataset.leeg
      || (opties.length ? "— kies —" : "— geen —");
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

  /* ------------------------------------------------- filters die zelf gaan */

  function koppelAutofilter(formulier) {
    var wacht = null;

    function verstuur() {
      // De bladzijde begint weer vooraan wanneer de selectie verandert.
      var pagina = formulier.querySelector("[name='pagina']");
      if (pagina) pagina.value = "1";
      formulier.submit();
    }

    formulier.addEventListener("change", function (gebeurtenis) {
      if (gebeurtenis.target.classList.contains("zoekinlijst")) return;
      verstuur();
    });

    // Tikken in een zoekveld wacht even af, anders vertrekt het formulier
    // na elke aanslag.
    formulier.querySelectorAll("[data-traag]").forEach(function (veld) {
      veld.addEventListener("input", function () {
        window.clearTimeout(wacht);
        wacht = window.setTimeout(verstuur, 600);
      });
      veld.addEventListener("keydown", function (gebeurtenis) {
        if (gebeurtenis.key === "Enter") {
          gebeurtenis.preventDefault();
          window.clearTimeout(wacht);
          verstuur();
        }
      });
    });
  }

  /* Zoeken binnen een lange meerkeuzelijst. */
  function koppelLijstzoeker(veld) {
    var lijst = document.getElementById("lijst-" + veld.dataset.zoekt);
    if (!lijst) return;
    var alle = Array.prototype.map.call(lijst.options, function (o) {
      return { waarde: o.value, tekst: o.textContent, gekozen: o.selected };
    });
    veld.addEventListener("input", function () {
      var naald = veld.value.trim().toLowerCase();
      Array.prototype.forEach.call(lijst.options, function (optie) {
        if (optie.selected) return;   // een keuze blijft altijd zichtbaar
        optie.hidden = naald !== "" && optie.textContent.toLowerCase().indexOf(naald) === -1;
      });
      void alle;
    });
  }

  /* De aanvinkbare jaartallen kleuren mee. */
  function koppelChips(wortel) {
    wortel.querySelectorAll(".chip input").forEach(function (vakje) {
      vakje.addEventListener("change", function () {
        vakje.closest(".chip").classList.toggle("aan", vakje.checked);
      });
    });
  }

  /* ------------------------------------------------- gestapelde staafgrafiek */

  function tekenStapelgrafiek(doel) {
    var gegevens = JSON.parse(doel.dataset.reeksen || "{}");
    var labels = gegevens.labels || [];
    var series = gegevens.series || [];
    if (!labels.length || !series.length) return;

    var breedte = 920, hoogte = 420;
    var marge = { boven: 16, rechts: 18, onder: 46, links: 78 };
    var vlakB = breedte - marge.links - marge.rechts;
    var vlakH = hoogte - marge.boven - marge.onder;

    var totalen = labels.map(function (_l, i) {
      return series.reduce(function (som, reeks) { return som + (reeks.waarden[i] || 0); }, 0);
    });
    var max = Math.max.apply(null, totalen) || 1;
    var stap = Math.pow(10, Math.floor(Math.log10(max)));
    var bovengrens = Math.ceil(max / stap) * stap;

    var vakbreedte = vlakB / labels.length;
    var staaf = Math.min(vakbreedte * 0.68, 64);

    function y(waarde) { return marge.boven + vlakH - (vlakH * waarde) / bovengrens; }

    var svg = ['<svg viewBox="0 0 ' + breedte + " " + hoogte +
      '" class="grafiek" role="img" aria-label="Gestapelde staafgrafiek">'];

    for (var t = 0; t <= 4; t++) {
      var waarde = (bovengrens / 4) * t;
      var yy = y(waarde);
      svg.push('<line x1="' + marge.links + '" y1="' + yy + '" x2="' +
        (breedte - marge.rechts) + '" y2="' + yy + '" stroke="#dbe1e9"/>');
      svg.push('<text x="' + (marge.links - 8) + '" y="' + (yy + 4) +
        '" text-anchor="end" font-size="11" fill="#5a6675">' +
        Math.round(waarde).toLocaleString("nl-BE") + "</text>");
    }

    labels.forEach(function (label, i) {
      var x = marge.links + vakbreedte * i + (vakbreedte - staaf) / 2;
      var onder = marge.boven + vlakH;
      series.forEach(function (reeks, index) {
        var waarde = reeks.waarden[i] || 0;
        if (waarde <= 0) return;
        var hoog = (vlakH * waarde) / bovengrens;
        onder -= hoog;
        svg.push('<rect x="' + x + '" y="' + onder + '" width="' + staaf +
          '" height="' + hoog + '" fill="' + PALET[index % PALET.length] + '">' +
          "<title>" + reeks.naam + " " + label + ": " +
          Math.round(waarde).toLocaleString("nl-BE") + " EUR</title></rect>");
      });
      svg.push('<text x="' + (x + staaf / 2) + '" y="' + (hoogte - 26) +
        '" text-anchor="middle" font-size="11" fill="#5a6675">' + label + "</text>");
      svg.push('<text x="' + (x + staaf / 2) + '" y="' + (hoogte - 12) +
        '" text-anchor="middle" font-size="10" fill="#8b95a3">' +
        Math.round(totalen[i]).toLocaleString("nl-BE") + "</text>");
    });

    svg.push("</svg>");
    doel.innerHTML = svg.join("");
    zetLegende(doel, series.map(function (r) { return r.naam; }));
  }

  /* ------------------------------------------------------------------ taart */

  function tekenTaart(doel) {
    var gegevens = JSON.parse(doel.dataset.stukken || "{}");
    var stukken = (gegevens.stukken || []).filter(function (s) { return s.waarde > 0; });
    var totaal = gegevens.totaal || stukken.reduce(function (s, d) { return s + d.waarde; }, 0);
    if (!stukken.length || totaal <= 0) return;

    var maat = 340, straal = 150, mid = maat / 2;
    var hoek = -Math.PI / 2;
    var svg = ['<svg viewBox="0 0 ' + maat + " " + maat +
      '" width="340" height="340" role="img" aria-label="Verdeling">'];

    stukken.forEach(function (stuk, index) {
      var deel = stuk.waarde / totaal;
      var eind = hoek + deel * Math.PI * 2;
      var kleur = PALET[index % PALET.length];
      if (deel > 0.9999) {
        svg.push('<circle cx="' + mid + '" cy="' + mid + '" r="' + straal +
          '" fill="' + kleur + '"/>');
      } else {
        var x1 = mid + straal * Math.cos(hoek), y1 = mid + straal * Math.sin(hoek);
        var x2 = mid + straal * Math.cos(eind), y2 = mid + straal * Math.sin(eind);
        var groot = deel > 0.5 ? 1 : 0;
        svg.push('<path d="M' + mid + ' ' + mid + ' L' + x1 + ' ' + y1 +
          ' A' + straal + ' ' + straal + ' 0 ' + groot + ' 1 ' + x2 + ' ' + y2 +
          ' Z" fill="' + kleur + '" stroke="#fff" stroke-width="1.5">' +
          "<title>" + stuk.naam + ": " + Math.round(stuk.waarde).toLocaleString("nl-BE") +
          " EUR (" + (deel * 100).toFixed(1) + "%)</title></path>");
      }
      hoek = eind;
    });

    svg.push("</svg>");
    doel.classList.add("taartvlak");
    doel.innerHTML = svg.join("");
    zetLegende(doel, stukken.map(function (s) {
      return s.naam + " — " + Math.round(s.waarde).toLocaleString("nl-BE") +
        " (" + (s.waarde / totaal * 100).toFixed(1) + "%)";
    }));
  }

  function zetLegende(doel, namen) {
    var legende = doel.parentNode.querySelector(".legende");
    if (!legende) return;
    legende.innerHTML = namen.map(function (naam, index) {
      return '<span><i style="background:' + PALET[index % PALET.length] + '"></i>' +
        naam + "</span>";
    }).join("");
  }

  /* ------------------------------------------------------- paneeltjes sluiten */
  /* Eén paneel tegelijk open, en klikken buiten het paneel sluit het. Zonder
     dit blijven alle knopjes openstaan en dekt het ene het andere af. */

  function koppelPanelen() {
    document.addEventListener("click", function (gebeurtenis) {
      var binnen = gebeurtenis.target.closest(".keuzeknop");
      document.querySelectorAll(".keuzeknop[open]").forEach(function (knop) {
        if (knop !== binnen) knop.open = false;
      });
      // Bij een knop rechts op het scherm klapt het paneel naar links open.
      if (binnen && binnen.open) {
        var plaats = binnen.getBoundingClientRect();
        binnen.classList.toggle("naarlinks",
          plaats.left + 480 > document.documentElement.clientWidth);
      }
    });

    document.addEventListener("keydown", function (gebeurtenis) {
      if (gebeurtenis.key !== "Escape") return;
      document.querySelectorAll(".keuzeknop[open]").forEach(function (knop) {
        knop.open = false;
      });
    });
  }

  /* De knop "Alleen bevestigd" kleurt mee. */
  function koppelAanvinkknoppen(wortel) {
    wortel.querySelectorAll(".aanvinkknop input").forEach(function (vakje) {
      vakje.addEventListener("change", function () {
        vakje.closest(".aanvinkknop").classList.toggle("aan", vakje.checked);
      });
    });
  }

  /* ------------------------------------------------------------- voortgang */
  /* Werk dat in de achtergrond loopt: om de seconde de stand opvragen en de
     balk bijwerken, zodat je ziet dat er iets gebeurt. */

  function koppelVoortgang(vlak) {
    var balk = vlak.querySelector(".voortgangsvulling");
    var fase = vlak.querySelector(".voortgangsfase");
    var teller = vlak.querySelector(".teller");
    var verstreken = vlak.querySelector(".verstreken");
    var uitslag = document.querySelector("[data-uitslag]");
    var mislukt = document.querySelector("[data-mislukt]");
    var mislukken = 0;

    function toonUitslag(gegevens) {
      vlak.classList.add("verborgen");
      if (!gegevens.gelukt) {
        if (!mislukt) return;
        mislukt.classList.remove("verborgen");
        mislukt.querySelector("[data-boodschap]").textContent =
          "Het inlezen is misgelopen: " + (gegevens.fout || "onbekende reden");
        return;
      }
      if (!uitslag) { window.location.reload(); return; }
      var r = gegevens.resultaat || {};
      uitslag.classList.remove("verborgen");
      uitslag.querySelectorAll("[data-veld]").forEach(function (el) {
        el.textContent = (r[el.dataset.veld] || 0).toLocaleString("nl-BE");
      });
      if (r.uit_bestand) {
        var p = uitslag.querySelector("[data-uit-bestand]");
        p.classList.remove("verborgen");
        p.textContent = r.uit_bestand +
          " daarvan kregen hun indeling rechtstreeks uit het bestand.";
      }
      if (r.fouten && r.fouten.length) {
        var doel = uitslag.querySelector("[data-fouten]");
        doel.classList.remove("verborgen");
        doel.innerHTML = "<h2>Rijen die niet gelukt zijn</h2><ul>" +
          r.fouten.map(function (f) { return "<li>" + f + "</li>"; }).join("") + "</ul>";
      }
    }

    function vraag() {
      fetch(vlak.dataset.bron, { headers: { "Accept": "application/json" } })
        .then(function (antwoord) {
          if (!antwoord.ok) throw new Error("geen antwoord");
          return antwoord.json();
        })
        .then(function (gegevens) {
          mislukken = 0;
          balk.style.width = gegevens.percent + "%";
          fase.textContent = gegevens.fase;
          if (gegevens.totaal) {
            teller.textContent = gegevens.stand.toLocaleString("nl-BE") + " van " +
              gegevens.totaal.toLocaleString("nl-BE") + " rijen";
          }
          verstreken.textContent = gegevens.seconden + " seconden";
          if (gegevens.klaar) { toonUitslag(gegevens); return; }
          window.setTimeout(vraag, 1000);
        })
        .catch(function () {
          mislukken += 1;
          if (mislukken > 10) {
            fase.textContent = "De verbinding met de toepassing is weg. " +
              "Herlaad de bladzijde om te zien waar de invoer staat.";
            return;
          }
          window.setTimeout(vraag, 2000);
        });
    }

    vraag();
  }

  /* ------------------------------------------------------------------ start */

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-categoriekiezer]").forEach(function (wortel) {
      koppelKeuzelijsten(wortel);
      if (!wortel.hasAttribute("data-plat")) koppelRichtingfilter(wortel);
    });
    document.querySelectorAll("[data-boomtabel]").forEach(koppelBoomtabel);
    document.querySelectorAll("[data-lijngrafiek]").forEach(tekenLijngrafiek);
    document.querySelectorAll("[data-stapelgrafiek]").forEach(tekenStapelgrafiek);
    document.querySelectorAll("[data-taartgrafiek]").forEach(tekenTaart);
    document.querySelectorAll("[data-autofilter]").forEach(function (formulier) {
      koppelAutofilter(formulier);
      koppelChips(formulier);
      koppelAanvinkknoppen(formulier);
    });
    koppelPanelen();
    document.querySelectorAll(".zoekinlijst").forEach(koppelLijstzoeker);
    document.querySelectorAll("[data-voortgang]").forEach(koppelVoortgang);
    koppelAiKnoppen();

    document.querySelectorAll("[data-bevestig]").forEach(function (formulier) {
      formulier.addEventListener("submit", function (gebeurtenis) {
        if (!window.confirm(formulier.dataset.bevestig)) gebeurtenis.preventDefault();
      });
    });
  });
})();
