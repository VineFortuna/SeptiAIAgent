---
name: sep7ro-class-invite
description: >
  Gestionează invitațiile la clasă și opțiunile de recuperare pentru elevii Sep7Ro.
  Folosește acest skill ori de câte ori primești informații despre un elev de la Sep7Ro:
  nivelul său (alb/galben/portocaliu/verde sau newbie/beginner/intermediate/advanced),
  profesorul curent, ziua și ora clasei, și fusul orar al elevului.
  Skill-ul generează: (1) mesajul de invitație la clasă gata de trimis, și
  (2) lista completă de clase disponibile pentru recuperare la același nivel și profesor,
  convertite în fusul orar al elevului. Se declanșează pentru fraze ca:
  "elevul X e centura galbena, cls marti adam, pacific time",
  "trimite invitatie la clasa", "ce clase poate recupera", "opțiuni de recuperare",
  "când poate face makeup", "fă invitația pentru elev".
---

# Sep7Ro Class Invite & Makeup Scheduler

## Scopul skill-ului
Primești date despre un elev și generezi:
1. **Mesajul de invitație** la clasă (din template-ul din `references/invite-template.md`)
2. **Lista de clase pentru recuperare** la același nivel, la alți profesori sau zile alternative — convertite în fusul orar al elevului

---

## Pasul 1 — Parsează inputul

Extrage din mesajul userului:
- **Nume elev** (dacă e dat)
- **Nivel**: alb / galben / portocaliu / verde (sau newbie / beginner / intermediate / advanced)
- **Profesor curent** și **ziua + ora clasei**
- **Fusul orar al elevului** (ex: Pacific, Eastern, Central, UK, RO/MD, Central Europe)

Dacă lipsesc informații esențiale, întreabă înainte să continui.

---

## Pasul 2 — Mapare nivel

| Română | Engleză | Culoare |
|--------|---------|---------|
| Alb / Boboc | Newbie | ⬜ White |
| Galben / Începător | Beginner | 🟡 Yellow |
| Portocaliu / Intermediar | Intermediate | 🟠 Orange |
| Verde / Avansat | Advanced | 🟢 Green |

---

## Pasul 3 — Profesori și limbă

| Profesor | Limbă clase | Observații |
|----------|-------------|------------|
| **Adam** | 🇬🇧 Engleză ONLY | Nu vorbește română |
| **Michael** | 🇬🇧 Engleză ONLY | Nu vorbește română |
| **Daniel** | 🇷🇴 Română ONLY | Nu vorbește engleză |
| **Cami** | 🇷🇴 / 🇬🇧 | Bilingvă |
| **Alina** | 🇷🇴 / 🇬🇧 | Bilingvă |
| **Denisa** | 🇷🇴 / 🇬🇧 | Limba română + engleză |

> **Important**: Dacă elevul e la Adam sau Michael, invitația se trimite în engleză.
> Dacă e la Daniel, invitația se trimite în română.
> Cami, Alina, Denisa — adaptează după preferința elevului.

---

## Pasul 4 — Programul complet EST (baza de date clase)

Citește `references/schedule-est.md` pentru programul complet în EST.

---

## Pasul 5 — Conversie fus orar

Aplică offset-ul față de EST:

| Fus orar | Offset față de EST |
|----------|--------------------|
| **Eastern (Toronto/Miami)** | EST ±0 |
| **Central (Chicago)** | EST −1h |
| **Pacific (Vancouver/Seattle)** | EST −3h |
| **RO/MD (București/Chișinău)** | EST +7h |
| **UK/IRL (London/Dublin)** | EST +5h |
| **Central Europe (Berlin/Amsterdam)** | EST +6h |

---

## Pasul 6 — Filtrare clase pentru recuperare

1. Identifică **nivelul elevului**
2. Găsește **toate clasele la același nivel** din schedule-est.md
3. **Exclude** clasa curentă a elevului (ziua + ora + profesor)
4. **Sortează** pe zile (Luni → Duminică), apoi pe oră
5. Convertește orele în fusul orar al elevului
6. Dacă profesorul curent e Daniel → sugerează doar clase la Daniel sau bilingve (nu Adam/Michael dacă elevul nu știe engleză)
7. Dacă profesorul curent e Adam/Michael → clasele sunt în engleză; indică ce profesori vorbesc engleză

---

## Pasul 7 — Generează output

### A) Mesajul de invitație
Citește `references/invite-template.md` și completează:
- `___` (clasa/ziua/ora) cu datele elevului, convertite în fusul lui
- Link Zoom al profesorului din `references/zoom-links.md`
- Limba mesajului: română sau engleză în funcție de profesor

### B) Opțiunile de recuperare
Format output:

```
📅 OPȚIUNI DE RECUPERARE — [Nume Elev] — Nivel: [Nivel] — [Fus orar]

Clase disponibile la același nivel:

• [Zi] la [Ora în fusul elevului] — Prof. [Profesor] ([limbă]) 
  ↳ EST: [ora originală]

• [Zi] la [Ora în fusul elevului] — Prof. [Profesor] ([limbă])
  ↳ EST: [ora originală]

[...etc]

ℹ️ Clasa curentă a elevului ([Zi] [Ora] cu [Profesor]) a fost exclusă din lista de mai sus.
```

---

## Reguli speciale

- **Tournament / Turneu** — nu se poate recupera, nu le include în opțiuni
- **Denisa Romanian Language / Limba Română** — e clasă de limbă română, nu șah; include-o doar dacă e relevant
- **Denisa Limba Engleză** — clasă de engleză, nu șah; include-o doar dacă e relevant  
- Dacă elevul e **începător (galben/alb)** și nu știe engleză → nu-l trimite la Adam sau Michael
- Întotdeauna menționează **limba clasei** în opțiunile de recuperare

---

## Reference files

- `references/schedule-est.md` — Programul complet în EST
- `references/invite-template.md` — Template mesaj invitație (RO + EN)
- `references/zoom-links.md` — Link-urile Zoom ale profesorilor
