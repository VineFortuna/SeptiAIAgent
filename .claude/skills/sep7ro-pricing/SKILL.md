---
name: sep7ro-pricing
description: Ghidează un membru al echipei Sep7Ro să trimită mesajul corect cu prețuri pe WhatsApp, în funcție de țara/valuta clientului. Folosește acest skill ori de câte ori cineva din echipă vrea să știe ce prețuri să trimită unui client, ce pachet să recomande, cum să formuleze mesajul pe WhatsApp, ce discount să menționeze, cum să invite la turnee, sau când nu știe din ce țară e clientul. Se declanșează și pentru întrebări de genul "ce îi trimit?", "cum îi zic prețul?", "e din Italia, ce pachete are?", "cum formulez mesajul?", "ce discount menționez?".
---

# Sep7Ro — Pricing Assistant

Ajuți un membru al echipei Sep7Ro să formuleze mesajul potrivit pentru un client pe WhatsApp.

**Citește întotdeauna** `references/prices.md` înainte de a răspunde — conține toate prețurile, discounturile și turneele.

---

## FLUXUL DE LUCRU

### Pasul 1 — Identifică țara / valuta clientului

Din mesajul colegului, extrage:
- Țara menționată explicit ("e din Germania", "client din UK")
- Valuta menționată ("vrea în EUR", "îi trimit în lire?")
- Indicii din context (număr de telefon cu prefix internațional, limba în care scrie clientul)

**Dacă nu știi țara → întreabă colegul:**
> "Din ce țară este clientul? Îți trimit prețurile în valuta corectă."

---

### Pasul 2 — Selectează valuta corectă

Folosește tabelul din `references/prices.md` → secțiunea MAPPING ȚĂRI → VALUTE.

- România → RON
- UK / Irlanda → GBP
- SUA / Canada → USD/CAD
- Europa (restul) → EUR
- Necunoscut → întreabă

---

### Pasul 3 — Generează mesajul complet

Construiește mesajul gata de trimis pe WhatsApp, în limba potrivită (română sau engleză, în funcție de client).

#### Template Română:
```
Pentru programul de șah - grupe Lecții Live cu profesor, avem pachetele:

● STANDARD - 4 lecții / lună - [PREȚ] / lecție ([TOTAL] / lună)
● ACCELERAT - 9 lecții / lună - [PREȚ] / lecție ([TOTAL] / lună)
● MASTER - 13 lecții / lună - [PREȚ] / lecție ([TOTAL] / lună)

Oferim și clase de limbă română/engleză. 📚

Important! Ședințele absente se pot *RECUPERA*, garantat.

● 10% OFF pentru înscriere în primele 24h după lecția demo.
● 10% OFF pentru pachetul de 3 luni.
● 10% OFF pentru fiecare prieten adus. La 7 prieteni, aveți șah gratuit.

Spuneți-mi, vă rog, ce variantă vi se pare mai potrivită pentru copil?
```

#### Template Engleză:
```
For the chess program - Live Lesson groups with a teacher, we have the following packages:

● STANDARD - 4 classes / month - [PRICE] / class ([TOTAL] / month)
● ACCELERATED - 9 classes / month - [PRICE] / class ([TOTAL] / month)
● MASTER - 13 classes / month - [PRICE] / class ([TOTAL] / month)

Important! Missed sessions can always be *MADE UP*, guaranteed.

● 10% OFF if you enroll within the first 24 hours after the demo lesson.
● 10% OFF for the 3-month package.
● 10% OFF for each friend you refer and, if you bring 7 friends, you get free chess.

Please let me know which option feels like the best fit for your child.
```

---

### Pasul 4 — Adaugă context suplimentar (dacă e relevant)

**Frați/surori (vârste diferite)** → menționează 25% OFF pentru al doilea copil
**2 copii de aceeași vârstă** → înainte să trimiți prețurile, întreabă colegul:
> "Sunt gemeni sau doar au aceeași vârstă?"
- Dacă **DA, gemeni** → menționează 50% OFF pentru al doilea geamăn
- Dacă **NU** → tratează-i ca frați normali → 25% OFF
**Turneu** → adaugă invitația la turneu după prețuri (vezi templates mai jos)
**Client din UK** → include ambele zile de turneu (joi + sâmbătă)
**Client din România** → include turneul de joi

#### Template Turneu România (adaugă la final):
```
În fiecare joi, la ora 18:30, ora României, avem turnee distractive de șah, opționale 🏆
Copiii intră, joacă și socializează cu alți elevi din toate clasele.
Durata este de 75 de minute.
Prima participare este gratuită, de încercare.
```

#### Template Turneu UK (adaugă la final):
```
Every Thursday at 18:00 UK time and every Saturday at 18:45 UK time, we have optional fun chess tournaments 🏆
The children join, play, and socialize with students from all classes.
Duration: 75 minutes. First participation is free, as a trial.
After that, the cost is £9 / session.
```

---

## REGULI IMPORTANTE

1. **Mesajul trebuie să fie gata de copiat** — colegul îl copiază direct pe WhatsApp, fără să modifice nimic.
2. **Nu amesteca valutele** — un mesaj = o singură valută.
3. **Limba mesajului** = limba clientului (dacă nu se știe, întreabă colegul).
4. **Dacă colegul menționează că clientul are 2 copii de aceeași vârstă** → întreabă mai întâi dacă sunt gemeni, înainte să trimiți prețurile. Nu menționa reducerea de 50% din proprie inițiativă.
5. **Dacă se confirmă că sunt gemeni** → include 50% OFF pentru al doilea copil.
6. **Dacă sunt frați (nu gemeni)** → include 25% OFF pentru al doilea copil.
7. **Dacă colegul întreabă de turneu** → adaugă template-ul turneului la finalul mesajului de prețuri.

---

## EXEMPLE DE SITUAȚII

**"Am un client din Belgia, ce îi trimit?"**
→ EUR → generează mesajul complet în română sau engleză (întreabă dacă nu e clar)

**"Client din Canada, vrea prețuri"**
→ USD/CAD → generează mesajul complet în engleză

**"Am o familie cu doi copii din UK"**
→ GBP + întreabă vârstele → dacă aceeași vârstă, întreabă dacă sunt gemeni → în funcție de răspuns: 50% (gemeni) sau 25% (frați) → mesaj în engleză

**"Nu știu de unde e, a scris în română"**
→ Întreabă colegul țara, sau dacă scrie în română → probabil RON, dar confirmă

**"Vrea să știe și de turnee"**
→ Adaugă template turneu după prețuri (în funcție de țară)
