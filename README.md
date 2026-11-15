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

## 4. Kör automatiskt på din dator
MATCHi blockerar GitHubs servrar, så boten körs på en dator som är på (Mac, Windows eller Raspberry Pi).
Hämta koden: **Code → Download ZIP** på GitHub och packa upp den.

**Mac:** öppna Terminal i mappen och kör
```
bash installera_mac.sh matchi-tennis-DITTÄMNE
```
**Windows:** öppna PowerShell i mappen och kör
```
powershell -ExecutionPolicy Bypass -File installera_windows.ps1 matchi-tennis-DITTÄMNE
```
**Linux/Raspberry Pi:** `NTFY_TOPIC=matchi-tennis-DITTÄMNE python3 matchi_bevakare.py --loop 300`
(lägg i crontab `@reboot` eller en systemd-tjänst).

Skripten skickar en testnotis och kollar sedan var 5:e minut. Datorn måste vara vaken för att få notiser.
