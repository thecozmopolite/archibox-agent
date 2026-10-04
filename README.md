# ArchiBox Agent

**ArchiBox** = clé physique ESP32-S3 (future XIAO ESP32S3 Sense) qui, branchée en USB sur un PC, donne à **archimade** des yeux et des mains sur ce PC.

Branches l'ESP → archimade reçoit la connexion → notif Telegram → je prends le contrôle clavier/souris.
Retires l'ESP → archimade détecte la déconnexion → tout s'arrête.

---

## Comment ça marche

```
[ESP32-S3 branché en USB]
  └─> Alimentation + connexion WiFi
        └─> Poll archimade:8766 (X-Archibox-Token)
              └─> archimade notifie Cédric sur Telegram
                    └─> Windows agent (pynput) exécute les commandes

[ESP débranché]
  └─> archimade détecte la déconnexion
        └─> Arrêt propre, rien ne persiste
```

**L'ESP n'est pas un périphérique USB** (pas de stockage, pas de HID).
Il汲 uniquement l'alimenté par USB et communique en WiFi.
Le contrôle clavier/souris est fait par l'agent Windows.

---

## Matériel nécessaire

| Composant | Rôle | Prix |
|-----------|------|------|
| **ESP32-S3** (ou XIAO ESP32S3) | Clé physique — token WiFi | ~8-23€ |
| Agent Windows (`archibox-agent.exe`) | Contrôle clavier/souris/screenshot | gratuit |

### ESP32-S3 SuperMini (prototype v1)
- ~8-10€
- WiFi intégré, 240MHz, 4MB flash
- Alimenté par USB-C

### XIAO ESP32S3 Sense (prototype v2)
- ~23€
- Micro INMP441 intégré (pour voix)
- USB-C, compact

---

## Préparation de l'ESP

Flash le firmware avec ton token :

```python
import uuid
print(uuid.uuid4())  # génère le token
```

Le token `0ea3bbbc-8035-4c24-a551-14094f74daf1` est déjà enregistré côté archimade.

Configure le WiFi + token dans `platformio.ini` ou via `arduino_secrets.h`, puis flash.

---

## Installation sur PC Windows

### 1. Installe Python + dépendances
```powershell
# Python 3.10+ requis
pip install pyinstaller pynput mss requests
```

### 2. Génère le .exe
```bash
pyinstaller --onefile --name archibox-agent --console agent/agent.py
```

### 3. Installe
```powershell
# En admin
install.bat
```

Le service tourne en arrière-plan. Il se connecte à archimade avec le token de l'ESP.

---

## Commandes supportées

| Commande | Description |
|----------|-------------|
| `TYPE Bonjour` | Tape le texte |
| `KEY WIN R` | Touche Windows |
| `KEY CTRL C` | Raccourci clavier |
| `MOUSE 100 50` | Déplacement relatif |
| `CLICK left` | Clic gauche |
| `CLICK right` | Clic droit |
| `SCREENSHOT` | Capture d'écran |
| `STOP` | Arrête l'agent |

---

## Développement

```bash
# Agent Windows
pip install pyinstaller pynput mss requests
pyinstaller --onefile --name archibox-agent --console agent/agent.py

# USB watchdog (C# / .NET 8)
cd usb-watch && dotnet build -c Release

# Lancer agent manuellement
python agent/agent.py <token> <device_id> <archimade_host> [port]
```

---

## Sécurité

- Token stocké uniquement dans la flash de l'ESP → pas sur le PC
- Header `X-Archibox-Token` validé côté serveur archimade
- Token révocable à distance (`DELETE /admin/token/{token}`)
- Aucune persistence sur le PC quand l'ESP est débranché

---

## Architecture

```
archibox-agent/
├── agent/
│   └── agent.py          # Agent Windows (Python + pynput)
├── usb-watch/
│   ├── Program.cs         # Watchdog USB (C# / .NET 8)
│   └── usb-watch.csproj
├── scripts/
│   ├── install.bat
│   └── uninstall.bat
└── .github/
    └── workflows/
        └── build.yml     # CI: compile les .exe
```
