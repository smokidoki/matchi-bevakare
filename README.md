# MATCHi-bevakare

Bevakar MATCHi och skickar en push-notis till mobilen när en tid **släpps** (ny eller avbokad)
på vardagar med start kl 17:00–18:59 på de anläggningar du valt.

## 1. Notiser i mobilen (ntfy, gratis)
1. Installera appen **ntfy** (App Store / Google Play).
2. Tryck **+** och prenumerera på ett hemligt ämne, t.ex. `matchi-simon-8f3k2q` (den som kan namnet kan läsa notiserna).

## 2. Välj anläggningar
Öppna anläggningen på matchi.se. Adressen ser ut som `matchi.se/facilities/<slug>`.
Lägg in slugarna i `config.json` under `"facilities"`. Du kan också söka fram dem:

```
pip install -r requirements.txt
python matchi_bevakare.py --discover Stockholm
```

`"sport": 1` = tennis (5 padel, 2 badminton, 3 squash). Tidsfönster och veckodagar ställs in i samma fil.

## 3. Testa lokalt
```
NTFY_TOPIC=matchi-simon-8f3k2q python matchi_bevakare.py --test-notis   # testnotis
python matchi_bevakare.py --dry-run --debug                              # visar tider, skickar inget
```
Om inga tider hittas fast det finns lediga: titta i `debug/schedule_*.html`, där ligger det MATCHi
faktiskt skickade.

## 4. Kör automatiskt på GitHub (gratis)
1. Skapa ett **publikt** GitHub-repo och ladda upp de här filerna. Publikt repo ger obegränsat med
   Actions-minuter. Ett privat repo skulle gå över gratiskvoten.
2. Lägg ämnet som hemlighet: *Settings → Secrets and variables → Actions → New repository secret*,
   namn `NTFY_TOPIC`.
3. Gå till fliken *Actions*, aktivera workflows och kör *Bevaka MATCHi* en gång manuellt.

Den kör sedan var 10:e minut kl 06–23. Första körningen skickar alla lediga tider som finns just
nu. Därefter kommer bara nya tider.
GitHub pausar schemalagda körningar om repot inte har haft någon aktivitet på 60 dagar. Gör då en
liten commit eller tryck *Enable* igen.

**Alternativ:** kör `python matchi_bevakare.py --loop 300` på en dator eller Raspberry Pi som alltid är på.
