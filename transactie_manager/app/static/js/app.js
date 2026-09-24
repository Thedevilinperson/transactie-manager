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

  /* Zet een AI-voorstel meteen in de keuzelijsten van het bewerkscherm, als
     de knop daar staat. Op het nazicht-overzicht staat geen keuzelijst naast
     de knop; daar blijft het bij de tekst in koppelAiKnoppen hieronder. */
  function vulAiVoorstelIn(knop, voorstel) {
    var formulier = knop.closest("[data-categoriekiezer]");
    if (!formulier || !voorstel.categorie_id) return;

    var hoofd = formulier.querySelector("[data-cat-niveau='0']");
    var sub = formulier.querySelector("[data-cat-niveau='1']");
    var subsub = formulier.querySelector("[data-cat-niveau='2']");
    if (!hoofd) return;

    hoofd.value = voorstel.categorie_id;
    if (sub) sub.dataset.gekozen = voorstel.subcategorie_id || "";
    if (subsub) subsub.dataset.gekozen = voorstel.subsub_id || "";
    // Laat de bestaande cascade (koppelKeuzelijsten) de sub- en
    // sub-subcategorie ophalen en voorselecteren.
    hoofd.dispatchEvent(new Event("change"));

    var handelaarVeld = formulier.querySelector("#handelaar");
    if (handelaarVeld && !handelaarVeld.value && voorstel.handelaar) {
      handelaarVeld.value = voorstel.handelaar;
    }
    var landVeld = formulier.querySelector("#land");
    if (landVeld && !landVeld.value && voorstel.land) {
      landVeld.value = voorstel.land;
    }
  }

  /* Leest een antwoord als JSON. Een proxy die de verbinding afbreekt, geeft
     een HTML-foutpagina terug; dan liever een duidelijke melding dan een
     stille fout. */
  function leesJson(r) {
    return r.text().then(function (tekst) {
      try {
        return { ok: r.ok, status: r.status, d: JSON.parse(tekst) };
      } catch (e) {
        return { ok: false, status: r.status,
                 d: { fout: "Onverwacht antwoord van de server (HTTP " + r.status + ")." } };
      }
    });
  }

  /* De bevraging loopt op de server in een aparte draad: een lokaal model
     rekent soms minuten, en zo lang op één antwoord wachten brak onderweg af.
     De knop start ze en vraagt dan om de twee seconden de stand op. */
  function koppelAiKnoppen() {
    document.querySelectorAll("[data-ai-voor]").forEach(function (knop) {
      knop.addEventListener("click", function () {
        var txId = knop.dataset.aiVoor;
        var doel = document.querySelector('[data-ai-uitvoer="' + txId + '"]');
        var oud = knop.textContent;
        var begin = Date.now();
        var missers = 0;

        function melding(tekst) { if (doel) doel.textContent = tekst; }
        function klaar() { knop.disabled = false; knop.textContent = oud; }
        function toon(d) {
          if (d.fout) { melding(d.fout); return; }
          if (doel) {
            doel.innerHTML = "Voorstel: <strong>" + d.pad + "</strong>. " +
              (d.toelichting || "") +
              " Opgeslagen als voorstel — nakijken en bevestigen blijft nodig.";
          }
          vulAiVoorstelIn(knop, d);
        }
        function volg(token) {
          fetch(basis() + "api/ai-voorstel/stand/" + encodeURIComponent(token),
                { headers: { "Accept": "application/json" } })
            .then(leesJson)
            .then(function (a) {
              missers = 0;
              if (!a.ok) { melding(a.d.fout || "De stand is niet op te vragen."); klaar(); return; }
              if (!a.d.klaar) {
                knop.textContent = "Bezig… " + Math.round((Date.now() - begin) / 1000) + " s";
                setTimeout(function () { volg(token); }, 2000);
                return;
              }
              klaar();
              if (!a.d.gelukt) { melding("Er liep iets mis: " + (a.d.fout || "onbekende fout")); return; }
              toon(a.d.resultaat || {});
            })
            .catch(function () {
              // Een enkele gemiste stand is geen ramp; blijven proberen.
              if (++missers <= 5) { setTimeout(function () { volg(token); }, 4000); return; }
              melding("De server is niet bereikbaar. Herlaad de bladzijde straks: een " +
                      "voorstel dat intussen klaar is, staat dan al bij de transactie.");
              klaar();
            });
        }

        knop.disabled = true;
        knop.textContent = "Bezig…";
        melding("");
        fetch(basis() + "api/ai-voorstel/" + txId,
              { method: "POST", headers: { "Accept": "application/json" } })
          .then(leesJson)
          .then(function (a) {
            if (!a.ok || !a.d.token) { melding(a.d.fout || "Het model gaf geen antwoord."); klaar(); return; }
            volg(a.d.token);
          })
          .catch(function () { melding("De server is niet bereikbaar."); klaar(); });
      });
    });
  }

  /* ---------------------------------------------------- webopzoeking */

  /* Toont wat Brave Search over de tegenpartij vindt: dezelfde opzoeking die
     het AI-model meekrijgt. Alles wordt als tekst in de pagina gezet, nooit
     als HTML — de resultaten komen van buiten. */
  function toonWebresultaten(doel, d) {
    doel.textContent = "";
    function el(soort, klasse, tekst) {
      var e = document.createElement(soort);
      if (klasse) e.className = klasse;
      if (tekst) e.textContent = tekst;
      return e;
    }

    var kop = el("p", "klein-detail");
    kop.appendChild(document.createTextNode("Gezocht op "));
    kop.appendChild(el("strong", "", d.zoekvraag));
    kop.appendChild(document.createTextNode(". " + d.gebruik));
    doel.appendChild(kop);

    if (!d.resultaten || !d.resultaten.length) {
      doel.appendChild(el("p", "klein-detail", "Brave vond niets."));
      return;
    }

    var lijst = el("ol", "webresultaten");
    d.resultaten.forEach(function (r) {
      var li = el("li");
      var titel = r.titel || r.url || "(zonder titel)";
      if (/^https?:\/\//i.test(r.url || "")) {
        var a = el("a", "", titel);
        a.href = r.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.appendChild(a);
      } else {
        li.appendChild(el("strong", "", titel));
      }
      if (r.bron) li.appendChild(el("span", "klein-detail", " " + r.bron));
      if (r.beschrijving) li.appendChild(el("div", "", r.beschrijving));
      lijst.appendChild(li);
    });
    doel.appendChild(lijst);

    if (d.context) {
      var details = el("details", "webcontext");
      details.appendChild(el("summary", "klein-detail",
        "Zo krijgt het model het te zien"));
      details.appendChild(el("pre", "", d.context));
      doel.appendChild(details);
    }
  }

  function koppelWebKnoppen() {
    document.querySelectorAll("[data-web-voor]").forEach(function (knop) {
      knop.addEventListener("click", function () {
        var txId = knop.dataset.webVoor;
        var doel = document.querySelector('[data-web-uitvoer="' + txId + '"]');
        var oud = knop.textContent;
        var gegevens = new URLSearchParams();
        var naam = document.getElementById("tegenpartij_naam");
        var beschrijving = document.getElementById("beschrijving");
        if (naam) gegevens.set("naam", naam.value);
        if (beschrijving) gegevens.set("beschrijving", beschrijving.value);

        function melding(tekst) {
          if (doel) { doel.textContent = ""; doel.appendChild(document.createTextNode(tekst)); }
        }
        knop.disabled = true;
        knop.textContent = "Bezig met zoeken…";
        fetch(basis() + "api/webopzoeking/" + txId, {
          method: "POST",
          headers: { "Accept": "application/json" },
          body: gegevens
        })
          .then(leesJson)
          .then(function (a) {
            knop.disabled = false;
            knop.textContent = "Opnieuw zoeken";
            if (!a.ok) { melding(a.d.fout || "De opzoeking lukte niet."); return; }
            if (doel) toonWebresultaten(doel, a.d);
          })
          .catch(function () {
            knop.disabled = false;
            knop.textContent = oud;
            melding("De server is niet bereikbaar.");
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

      // Zelf het adres opbouwen in plaats van submit(), zodat het anker mee
      // kan. Staat de filterbalk halverwege de bladzijde, dan blijf je daar
      // staan in plaats van naar boven te springen.
      var anker = formulier.dataset.anker;
      if (!anker || !window.URL || !window.URLSearchParams) {
        formulier.submit();
        return;
      }
      var adres = new URL(formulier.getAttribute("action") || window.location.pathname,
                          window.location.href);
      adres.search = new URLSearchParams(new FormData(formulier)).toString();
      adres.hash = anker;
      window.location.assign(adres.toString());
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

    var breedte = 920, hoogte = 440;
    var marge = { boven: 16, rechts: 18, onder: 46, links: 86 };
    var vlakB = breedte - marge.links - marge.rechts;
    var vlakH = hoogte - marge.boven - marge.onder;

    // Uitgaven zijn negatief geboekt en horen dus onder de nullijn. Boven en
    // onder worden apart opgestapeld, zodat een periode met allebei klopt.
    var boven = [], onder = [], netto = [];
    labels.forEach(function (_l, i) {
      var op = 0, neer = 0;
      series.forEach(function (reeks) {
        var w = reeks.waarden[i] || 0;
        if (w >= 0) op += w; else neer += w;
      });
      boven.push(op); onder.push(neer); netto.push(op + neer);
    });

    var hoogste = Math.max.apply(null, boven.concat([0]));
    var laagste = Math.min.apply(null, onder.concat([0]));
    var bereik = hoogste - laagste || 1;
    var stap = Math.pow(10, Math.floor(Math.log10(bereik)));
    var bovengrens = Math.ceil(hoogste / stap) * stap;
    var ondergrens = Math.floor(laagste / stap) * stap;
    if (bovengrens === ondergrens) bovengrens = ondergrens + stap;

    function y(waarde) {
      return marge.boven + vlakH -
        (vlakH * (waarde - ondergrens)) / (bovengrens - ondergrens);
    }

    var vakbreedte = vlakB / labels.length;
    var staaf = Math.min(vakbreedte * 0.68, 64);
    var nullijn = y(0);

    var svg = ['<svg viewBox="0 0 ' + breedte + " " + hoogte +
      '" class="grafiek" role="img" aria-label="Gestapelde staafgrafiek">'];

    for (var t = 0; t <= 5; t++) {
      var waarde = ondergrens + ((bovengrens - ondergrens) / 5) * t;
      var yy = y(waarde);
      svg.push('<line x1="' + marge.links + '" y1="' + yy + '" x2="' +
        (breedte - marge.rechts) + '" y2="' + yy + '" stroke="#dbe1e9"/>');
      svg.push('<text x="' + (marge.links - 8) + '" y="' + (yy + 4) +
        '" text-anchor="end" font-size="11" fill="#5a6675">' +
        Math.round(waarde).toLocaleString("nl-BE") + "</text>");
    }
    svg.push('<line x1="' + marge.links + '" y1="' + nullijn + '" x2="' +
      (breedte - marge.rechts) + '" y2="' + nullijn + '" stroke="#5a6675"/>');

    labels.forEach(function (label, i) {
      var x = marge.links + vakbreedte * i + (vakbreedte - staaf) / 2;
      var opTop = y(boven[i]);
      var neerTop = nullijn;
      series.forEach(function (reeks, index) {
        var waarde = reeks.waarden[i] || 0;
        if (waarde === 0) return;
        var hoog = Math.abs(y(0) - y(Math.abs(waarde)));
        var top;
        if (waarde > 0) { top = opTop; opTop += hoog; }
        else { top = neerTop; neerTop += hoog; }
        svg.push('<rect x="' + x + '" y="' + top + '" width="' + staaf +
          '" height="' + hoog + '" fill="' + PALET[index % PALET.length] + '">' +
          "<title>" + reeks.naam + " " + label + ": " +
          Math.round(waarde).toLocaleString("nl-BE") + " EUR</title></rect>");
      });
      svg.push('<text x="' + (x + staaf / 2) + '" y="' + (hoogte - 26) +
        '" text-anchor="middle" font-size="11" fill="#5a6675">' + label + "</text>");
      svg.push('<text x="' + (x + staaf / 2) + '" y="' + (hoogte - 12) +
        '" text-anchor="middle" font-size="10" fill="#8b95a3">' +
        Math.round(netto[i]).toLocaleString("nl-BE") + "</text>");
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
          (mislukt.dataset.inleiding || "Het inlezen is misgelopen: ") +
          (gegevens.fout || "onbekende reden");
        return;
      }
      if (!uitslag) { window.location.reload(); return; }
      var r = gegevens.resultaat || {};
      uitslag.classList.remove("verborgen");
      uitslag.querySelectorAll("[data-veld]").forEach(function (el) {
        el.textContent = (r[el.dataset.veld] || 0).toLocaleString("nl-BE");
      });
      /* De samenvatting komt van de server wanneer die er een meegeeft; anders
         wordt ze hier opgeteld, zoals bij een bestandsinvoer. */
      var telling = uitslag.querySelector("[data-telling]");
      if (telling && r.samenvatting) {
        telling.textContent = r.samenvatting;
      } else if (telling && r.totaal !== undefined) {
        var som = (r.nieuw || 0) + (r.aangevuld || 0) + (r.ongewijzigd || 0) +
                  (r.overgeslagen || 0);
        telling.textContent = "Van de " + (r.totaal || 0).toLocaleString("nl-BE") +
          " rijen zijn er " + som.toLocaleString("nl-BE") + " verklaard." +
          (som === r.totaal ? "" : " Er blijven er " + (r.totaal - som) +
            " over; dat hoort niet en is het melden waard.");
      }
      var knop = uitslag.querySelector("[data-naar-regels]");
      if (knop && r.batch && (r.ongewijzigd || r.overgeslagen || r.aangevuld)) {
        knop.href = (document.body.dataset.basis || "/") +
          "importeren/batch/" + r.batch + "/regels";
        knop.classList.remove("verborgen");
      }
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
              gegevens.totaal.toLocaleString("nl-BE") + " " +
              (vlak.dataset.eenheid || "rijen");
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

  /* ---------------------------------------------- oude opmaak herkennen */
  /* Als er iets tussen zit dat bestanden bewaart, kan de browser het stijlblad
     van een vorige versie gebruiken terwijl de bladzijde wel nieuw is. Dat
     levert een half werkend scherm op zonder dat je ziet waarom. */

  function controleerStijlblad() {
    var verwacht = document.body.dataset.versie;
    if (!verwacht) return;
    var geladen = window.getComputedStyle(document.documentElement)
      .getPropertyValue("--stijl-versie").trim().replace(/^"|"$/g, "");
    if (!geladen || geladen === verwacht) return;

    var balk = document.createElement("div");
    balk.className = "melding fout";
    balk.innerHTML = "Je browser gebruikt de opmaak van versie <strong>" +
      geladen + "</strong> terwijl deze toepassing op <strong>" + verwacht +
      "</strong> draait. Herlaad met Ctrl+F5, of leeg de opslag van je browser " +
      "voor deze site.";
    var inhoud = document.querySelector(".inhoud");
    if (inhoud) inhoud.insertBefore(balk, inhoud.firstChild);
  }

  /* ------------------------------------------- omschrijving van categorie */
  /* Bij het kiezen van een categorie de huidige omschrijving invullen, zodat
     je ze aanpast in plaats van opnieuw te typen. */

  function koppelOmschrijving(formulier) {
    var keuze = formulier.querySelector("select[name='id']");
    var veld = formulier.querySelector("input[name='omschrijving']");
    if (!keuze || !veld) return;
    function vul() {
      var optie = keuze.options[keuze.selectedIndex];
      veld.value = (optie && optie.dataset.omschrijving) || "";
    }
    keuze.addEventListener("change", vul);
    vul();
  }

  /* ------------------------------------------ regel maken vanuit transactie */
  /* Wie iets aanpast in het uitklapvenster, wil die regel ook: dan gaat het
     vinkje "bij het opslaan aanmaken" vanzelf aan, en bij een rij waarin je
     een waarde typt ook het vinkje van die rij. De proefknop stuurt het hele
     formulier op en toont op welke transacties de regel nu zou passen. */

  function koppelRegelmaker(vak) {
    var maken = vak.querySelector("[name='regel_maken']");
    var formulier = vak.closest("form");
    var naamVeld = vak.querySelector("[name='rv_naam']");
    var naamZelf = false;  // zelf aangepast? dan niet meer overschrijven

    /* De voorgestelde naam: tegenpartij, met de aangevinkte mededelingen erbij. */
    function stelNaamVoor() {
      if (!naamVeld || naamZelf) return;
      var naam = "", mededelingen = [];
      vak.querySelectorAll(".regelmaker-rij").forEach(function (rij) {
        if (!rij.querySelector("[name='rv_gebruik']").checked) return;
        var veld = rij.querySelector("[name='rv_veld']").value;
        var op = rij.querySelector("[name='rv_operator']").value;
        var w = rij.querySelector("[name='rv_waarde']").value.trim();
        if (!w) return;
        if (veld === "tegenpartij_naam" && !naam) naam = w;
        if (veld === "mededeling") mededelingen.push((op === "bevat_niet" ? "zonder " : "") + w);
      });
      var tekst = [naam].concat(mededelingen).filter(Boolean).join(" – ");
      if (tekst) naamVeld.value = tekst.slice(0, 120);
    }

    vak.addEventListener("input", function (e) {
      if (e.target === maken) return;
      if (maken) maken.checked = true;
      if (e.target === naamVeld) { naamZelf = true; return; }
      if (e.target.name === "rv_waarde") {
        var rij = e.target.closest(".regelmaker-rij");
        var vink = rij && rij.querySelector("[name='rv_gebruik']");
        if (vink) vink.checked = e.target.value.trim() !== "";
      }
      stelNaamVoor();
    });
    vak.addEventListener("change", function (e) {
      if (e.target !== maken && maken) maken.checked = true;
      if (e.target !== naamVeld) stelNaamVoor();
    });

    var knop = vak.querySelector("[data-regelproef]");
    var uitvoer = vak.querySelector("[data-regelproef-uitvoer]");
    if (!knop || !uitvoer || !formulier) return;

    function regel(tekst, sterk) {
      var p = document.createElement("div");
      if (sterk) { var b = document.createElement("strong"); b.textContent = tekst; p.appendChild(b); }
      else p.textContent = tekst;
      uitvoer.appendChild(p);
    }

    knop.addEventListener("click", function () {
      var oud = knop.textContent;
      knop.disabled = true;
      knop.textContent = "Bezig met tellen…";
      uitvoer.textContent = "";
      var gegevens = new FormData(formulier);
      gegevens.append("rv_tx", vak.dataset.tx || "");
      fetch(basis() + "api/regel-proef", { method: "POST", body: gegevens })
        .then(leesJson)
        .then(function (a) {
          if (!a.ok) { uitvoer.textContent = a.d.fout || "Proberen lukte niet."; return; }
          var d = a.d;
          if (!d.aantal) {
            regel("Deze regel past op geen enkele transactie — ook niet op deze. " +
                  "Kijk de voorwaarden na.", true);
            return;
          }
          if (!d.deze) {
            regel("Let op: deze regel past niet op de transactie die je nu bewerkt.", true);
          }
          var andere = d.aantal - d.deze;
          var gelijkenis = d.gelijkenis || 0;
          regel("Past op " + (d.deze ? "deze transactie en " : "") + andere +
                (andere === 1 ? " andere" : " andere") + ": " + d.zelfde +
                " al in de gekozen categorie, " + d.anders + " in een andere, " +
                d.zonder + " zonder categorie" +
                (gelijkenis ? ", " + gelijkenis + " met een nog niet bevestigde gelijkenis" : "") +
                ".", true);
          if (d.zonder || gelijkenis) {
            regel("Met Meteen toepassen aangevinkt krijgen de " +
                  (d.zonder + gelijkenis) + " transacties zonder categorie of met een " +
                  "onbevestigde gelijkenis bij het opslaan de indeling van deze regel.");
          }
          if (d.anders) {
            regel("Transacties die al in een andere categorie staan, blijven daar: " +
                  "de regel geldt voor nieuwe transacties en, als je dat aanvinkt, " +
                  "voor wat nog geen categorie of alleen een onbevestigde gelijkenis heeft." +
                  (d.handmatig_anders ? " " + d.handmatig_anders +
                   " daarvan heb je zelf of via een ingelezen bestand ingedeeld — " +
                   "misschien is de regel te ruim." : ""));
          }
          regel("Prioriteit " + d.prioriteit + ", " + d.voorwaarden +
                (d.voorwaarden === 1 ? " voorwaarde." : " voorwaarden die samen moeten kloppen."));
          var lijst = document.createElement("ul");
          lijst.className = "regelproef-lijst";
          d.voorbeelden.forEach(function (v) {
            var li = document.createElement("li");
            li.textContent = v.datum + " · " + v.tegenpartij +
              (v.mededeling ? " — " + v.mededeling : "") + " · " + v.bedrag + " € · " +
              (v.soort === "deze" ? "deze transactie" :
               v.soort === "zonder" ? "zonder categorie" :
               v.soort === "gelijkenis" ? "onbevestigde gelijkenis: " + v.categorie :
               (v.soort === "zelfde" ? "al in deze categorie" : "nu: " + v.categorie));
            lijst.appendChild(li);
          });
          uitvoer.appendChild(lijst);
          if (d.aantal > d.voorbeelden.length) {
            regel("… en nog " + (d.aantal - d.voorbeelden.length) + " andere.");
          }
        })
        .catch(function () { uitvoer.textContent = "De server is niet bereikbaar."; })
        .finally(function () { knop.disabled = false; knop.textContent = oud; });
    });
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
    controleerStijlblad();
    document.querySelectorAll(".zoekinlijst").forEach(koppelLijstzoeker);
    document.querySelectorAll("[data-voortgang]").forEach(koppelVoortgang);
    koppelAiKnoppen();
    koppelWebKnoppen();
    document.querySelectorAll("[data-regelmaker]").forEach(koppelRegelmaker);
    document.querySelectorAll("[data-omschrijvingkiezer]").forEach(koppelOmschrijving);

    document.querySelectorAll("[data-bevestig]").forEach(function (formulier) {
      formulier.addEventListener("submit", function (gebeurtenis) {
        if (!window.confirm(formulier.dataset.bevestig)) gebeurtenis.preventDefault();
      });
    });
  });
})();
