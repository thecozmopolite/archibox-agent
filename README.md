# ArchiBox Agent

Windows agent for **ArchiBox** — ESP32-S3 USB HID PC control powered by ArchiMade.

Insert the USB key → the agent launches automatically and takes control of the PC keyboard/mouse. Eject the key → everything stops and cleans up.

---

## Comment ça marche

```
[Clé USB insérée]
  └─> usb-watch.exe (WMI events) détecte la clé
        └─> Lit token.txt + config.json sur la clé
              └─> Lance archibox-agent.exe
                    └─> Poll archimade:8766 (authentifié X-Archibox-Token)
                          └─> Exécute TYPE / KEY / MOUSE / SCREENSHOT via pynput

[Clé USB éjectée]
  └─> usb-watch.exe détecte l'éjection
        └─> Tue archibox-agent.exe
              └─> Plus rien ne reste sur le PC
```

---

## Préparation de la clé USB

Sur une clé USB (n'importe quelle taille), crée ces fichiers à la racine :

**`token.txt`** — le secret unique de cette clé :
```
8f3e9a2c-4b7d-4e1f-9c8a-2d5b6e3c1a7f
```

**`config.json`** — configuration :
```json
{
  "device_id": "esp32s3-box-01",
  "archimade_host": "192.168.0.119",
  "archimade_port": 8766
}
```

**`archibox.key`** — fichier marqueur (vide ou avec le nom de la clé) :
```
ArchiBox
```

Optionnel : copie `archibox-agent.exe` à la racine de la clé pour avoir tout auto-contenu.

---

## Installation sur un PC Windows

### Méthode automatique (recommandée)

1. Télécharge la dernière release depuis : https://github.com/thecozmopolite/archibox-agent/releases
2. Exécute `install.bat` **en tant qu'administrateur**
3. C'est fini — le watchdog tourne en arrière-plan

### Désinstallation
```
scripts\uninstall.bat   (en admin)
```
→ arrête les processus, supprime l'entrée démarrage, rien d'autre.

---

## Commandes supportées

| Commande | Description |
|----------|-------------|
| `TYPE Bonjour le monde` | Tape le texte |
| `KEY WIN R` | Appuie sur la touche Windows |
| `KEY CTRL C` | Raccourci Ctrl+C |
| `MOUSE 100 50` | Déplace la souris de +100/+50 px |
| `CLICK left` | Clic gauche |
| `CLICK right` | Clic droit |
| `SCROLL 0 -3` | Scroll vers le bas |
| `SCREENSHOT` | Prend une capture et l'envoie à archimade |
| `STOP` | Arrête l'agent |

---

## Générer un token

```python
import uuid
print(uuid.uuid4())
# ex: 8f3e9a2c-4b7d-4e1f-9c8a-2d5b6e3c1a7f
```

Chaque clé USB = un token différent. Le token est validé côté serveur archimade.

---

## Développement

```bash
# Build agent Windows (.exe)
pip install pyinstaller pynput mss requests
pyinstaller --onefile --name archibox-agent --console agent/agent.py

# Build USB watchdog (nécessite .NET 8)
cd usb-watch && dotnet build -c Release

# Lancer en local (sans USB)
python agent/agent.py <token> <device_id> <archimade_host> [port]
```

---

## Sécurité

- Le token est lu uniquement depuis la clé USB physique → pas de fichier sur le PC
- Chaque requête HTTP inclut le header `X-Archibox-Token`
- Le serveur archimade valide le token avant d'accepter les commandes
- Pas de persistence sur le PC : le token n'est jamais écrit sur le disque
- Agent.exe se ferme et disparaît quand la clé est retirée

---

## Architecture

```
archibox-agent/
├── agent/
│   └── agent.py          # Agent principal (Python + pynput)
├── usb-watch/
│   ├── Program.cs         # Watchdog USB (C# / .NET 8)
│   └── usb-watch.csproj  # Projet .NET
├── scripts/
│   ├── install.bat       # Script d'installation
│   └── uninstall.bat     # Script de désinstallation
└── .github/
    └── workflows/
        └── build.yml     # CI: compile les deux .exe
```
