---
name: sep7ro-account-onboarding
description: Ghidează un membru al echipei Sep7Ro prin fluxul de mesaje de după clasa demo de șah — de la cererea de feedback, la crearea contului de Lichess al copilului, până la mesajele de încurajare pentru primele partide. Folosește acest skill ori de câte ori cineva din echipă vrea să trimită instrucțiunile de creare cont Lichess, să ceară feedback după demo, să activeze modul pentru copii, să adauge elevul în echipa Sep7Ro, sau să încurajeze copilul să joace înainte de prima clasă reală. Se declanșează pentru fraze ca "cum îi fac cont pe lichess?", "ce îi trimit după demo?", "cum cer feedback după clasa demo?", "cum îi zic de kid mode?", "cum îl adaug în echipa Sep7Ro?", "ce îi trimit ca să joace acasă?", "cum îl încurajez să joace vs computer?".
---

# Sep7Ro — Onboarding Cont Lichess & Follow-up Demo

## Scopul skill-ului

Ghidezi un membru al echipei prin secvența de mesaje trimisă unui părinte în jurul clasei demo: cerere de feedback → instrucțiuni de creare cont Lichess → consolidare reguli de bază (dacă e cazul) → încurajare să joace înainte de prima clasă reală.

**Citește întotdeauna** `references/messages.md` înainte de a răspunde — conține toate template-urile RO/EN exacte, gata de copiat.

Acest skill acoperă etapa **tehnică** (crearea contului, joc, familiarizare cu platforma). Pentru prețuri, discounturi și finalizarea înscrierii, vezi skill-ul `sep7ro-pricing`. Pentru programarea claselor și recuperări, vezi `sep7ro-class-invite`.

---

## FLUXUL DE LUCRU

### Pasul 1 — Identifică unde se află elevul în flux

Din mesajul colegului, stabilește care e situația:
- **Înainte de demo, elevul știe deja puțin șah** → poate primi contul + video-uri de familiarizare înainte de clasa demo, ca profesorul să-i evalueze nivelul (secțiunea 2, varianta lungă din `references/messages.md`).
- **Chiar după clasa demo** → trimite mai întâi mesajul de feedback (secțiunea 1), apoi tranziția scurtă către creare cont (secțiunea 2, varianta scurtă).
- **Contul e deja creat, dar copilul nu a jucat încă** → trimite mesajele de încurajare (secțiunile 4-6, după caz).

Dacă nu e clar, întreabă colegul în ce etapă e elevul.

---

### Pasul 2 — Feedback după demo (dacă e cazul)

Trimite mesajul din `references/messages.md` secțiunea 1, cu numele copilului completat. Nu trece la pasul următor până nu ai (sau colegul nu are) un răspuns, dacă contextul sugerează că feedback-ul contează pentru a decide pasul următor.

---

### Pasul 3 — Instrucțiuni de creare cont Lichess

Generează mesajul complet din `references/messages.md` secțiunea 3, în limba potrivită (română sau engleză, în funcție de client). Include:
1. Video explicativ
2. Creare cont pe lichess.org (parolă ușoară)
3. Activare Kid Mode
4. Alăturare la echipa Sep7Ro (parola fixă: `d4d5c4`)
5. Download aplicație / bookmark

**Nu schimba ordinea pașilor și nu inventa o parolă nouă pentru echipă** — `d4d5c4` este fixă.

---

### Pasul 4 — Consolidare reguli de bază (opțional)

Dacă elevul știe deja puțin șah și profesorul vrea să-i verifice/consolideze nivelul înainte de clasă, adaugă mesajul din secțiunea 4 (video + exerciții LEARN → CHESS BASICS/FUNDAMENTALS).

---

### Pasul 5 — Încurajare joc (Play vs Computer)

Pentru a-i da încredere copilului să folosească platforma, trimite mesajul din secțiunea 5 (Play against Computer, nivel 1). Subliniază mereu că **nu câștigul contează**, ci familiarizarea cu piesele și platforma.

---

### Pasul 6 — Recomandare device (opțional, spre finalul secvenței)

Dacă părintele nu știe cum să facă accesul mai simplu pentru copil, trimite mesajul din secțiunea 6 (aplicație pe telefon/tabletă, bookmark pe computer, importanța de a rămâne logat ca profesorul să poată urmări activitatea).

---

## REGULI IMPORTANTE

1. **Mesajul trebuie să fie gata de copiat** — colegul îl copiază direct pe WhatsApp, fără să modifice altceva decât numele copilului.
2. **Limba mesajului** = limba clientului (dacă nu se știe, întreabă colegul).
3. **Link-urile video și link-urile Lichess se reproduc exact** — nu le parafraza, nu le scurta, nu le înlocui.
4. **Parola echipei Sep7Ro (`d4d5c4`) e fixă** pentru toți elevii — nu genera o parolă nouă.
5. **Nu trimite niciodată link-ul `ccmanager.sep7ro.com/teacherssdr`** către un părinte — e un instrument intern pentru profesori.
6. **Nu presa cu prețuri în acest flux** — dacă părintele întreabă de preț în timpul acestei conversații, direcționează către skill-ul `sep7ro-pricing`.
7. **"Câștigul nu contează"** — orice mesaj de încurajare la joc trebuie să păstreze acest ton, nu unul competitiv.

---

## EXEMPLE DE SITUAȚII

**"Elevul tocmai a terminat clasa demo, ce îi trimit?"**
→ Mesaj de feedback (Pasul 2) → apoi, după răspuns, tranziția scurtă + pașii de creare cont (Pasul 3).

**"Cum îi fac cont copilului înainte de demo, ca profesorul să-i vadă nivelul?"**
→ Varianta lungă de tranziție (secțiunea 2) + pașii de creare cont (Pasul 3) + eventual consolidare reguli de bază (Pasul 4) dacă știe deja puțin șah.

**"Și-a făcut cont, dar nu a jucat nimic încă"**
→ Mesajul de încurajare Play vs Computer (Pasul 5), eventual + recomandarea de device (Pasul 6).

**"Cum îl adaug în echipa Sep7Ro pe Lichess?"**
→ Link echipă + parola fixă `d4d5c4`, din Pasul 3.

**"Părintele întreabă și de preț în aceeași conversație"**
→ Termină fluxul de cont, apoi direcționează la skill-ul `sep7ro-pricing` pentru prețuri/discounturi.
