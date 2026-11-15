# 🎮 PS2toPS4-fPKG-Studio

<p align="center">
  <img src="https://img.shields.io/badge/Platform-PS4%20%7C%20GoldHEN-blue?style=for-the-badge&logo=playstation" alt="Platform">
  <img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen?style=for-the-badge&logo=python" alt="Python Version">
  <img src="https://img.shields.io/badge/Resolution-Up%20to%204K%20UHD-orange?style=for-the-badge" alt="4K Resolution">
  <img src="https://img.shields.io/badge/Framerate-60%20FPS%20Unlock-red?style=for-the-badge" alt="60 FPS">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License">
</p>

> **English:** Modern, standalone GUI & CLI utility to convert PlayStation 2 game ISOs into ready-to-install PlayStation 4 Fake Packages (`.pkg`) with enhanced graphics (4K/1080p super-sampling, 60 FPS unlock, native 16:9 widescreen, and de-blur filters).
>
> **Español:** Conversor moderno de ISOs de PlayStation 2 a Fake Packages (`.pkg`) instalables en PlayStation 4 (Jailbreak / GoldHEN) con mejoras gráficas de última generación (escalado 4K/1080p, 60 FPS, widescreen 16:9 y filtro de-blur HD).

---

## ✨ Features / Características

- ⚡ **1-Click ISO ➔ PKG Pipeline**: Drag or select your ISO, configure preferences, and output an installable `.pkg` directly.
- 🚀 **60 FPS Framerate Unlock**: Unlock games from 25/30 FPS limits for silky-smooth gameplay on modern console hardware.
- 📺 **Super-Sampling Resolution (GS Uprender)**:
  - `1x1` (Native 480p)
  - `2x2` (**1080p Full HD**)
  - `3x3` (**1440p 2K**)
  - `4x4` (**2160p 4K UHD** for PS4 Pro & PS5)
- ✨ **De-Blur HD Filter (`--gs-deblur=1`)**: Eliminates the original analog CRT ghosting and blur filters of the PS2, producing crystal-clear visuals.
- 🖥 **True 16:9 Widescreen Hacks**: Expands the horizontal field-of-view (FOV) inside the 3D rendering pipeline without stretching or distorting characters.
- 📺 **Progressive Scan 480p Force**: Eliminates interlacing flicker (480i) and combing artifacts.
- ⚡ **Multi-Threaded VU1 Acceleration (`--mtvu=1`)**: Distributes CPU workloads across multiple cores.
- 📼 **Retro CRT & Scanline Shaders**: Optional scanline intensity (`Light`, `CRT`) for retro CRT aesthetic.
- 💿 **Multi-Disc Support**: Built-in support for up to 5 discs with automated disc-swapping configurations.
- 🔍 **Auto-Detection**: Automatic parsing of `SYSTEM.CNF` from ISO9660 to detect Game ID, regional codes (`SLUS`, `SLES`, `SCUS`, `SLPM`), and titles.
- 📚 **Built-in Compatibility Database**: Comes pre-loaded with fixes, EE/VU clamping modes, and IOP sync configurations for over 30+ popular games (GTA series, God of War I & II, Kingdom Hearts, Persona, DBZ Budokai Tenkaichi 3, etc.).
- 🎨 **Dark Theme UI**: Clean, responsive, and intuitive graphical interface written in Python (Tkinter/TTK).

---

## 🚀 Quick Start / Inicio Rápido

### Windows:
1. Double-click **`Iniciar_Conversor.bat`** (or launch from terminal):
   ```bash
   python main.py
   ```
2. Select your PS2 ISO, customize graphics or icon, and click **"CONSTRUIR PROYECTO PKG"**.

### Command Line Interface (CLI):
```bash
# General conversion
python main.py --cli "path/to/game.iso" -o "path/to/output"

# Inspect ISO metadata
python main.py --info "path/to/game.iso"
```

---

## 🕹️ Installing on PlayStation 4 (GoldHEN)

1. Format a USB drive or external hard drive to **exFAT** (or FAT32).
2. Copy the generated `.pkg` file directly into the **root** of the USB drive.
3. Plug the USB drive into your jailbroken PS4.
4. Navigate to: **Settings ➔ GoldHEN ➔ Package Installer**.
5. Press **X** to install your game and enjoy!

---

## 🏗️ Project Architecture

```
PS2toPS4-fPKG-Studio/
├── assets/                  # Required binary tools & emulator templates
│   ├── eboot.bin            # Official PS2 Classics emulator base
│   ├── orbis-pub-cmd.exe    # Sony package compilation engine
│   ├── orbis-pub-prx.dll    # Packaging runtime DLL
│   └── ext/                 # Packaging helpers (sc.exe, di.exe)
├── src/
│   ├── config_generator.py  # Graphics options & game compatibility DB
│   ├── gp4_builder.py       # GP4 project XML generator
│   ├── gui.py               # Dark-mode GUI interface
│   ├── iso_utils.py         # Pure-python ISO9660 reader & validator
│   ├── pkg_builder.py       # PKG project assembler & orchestrator
│   └── sfo_builder.py       # Pure-python binary PARAM.SFO compiler
├── Iniciar_Conversor.bat    # 1-click launcher for Windows
├── main.py                  # Main entry point (GUI / CLI)
└── README.md
```

---

## ⚖️ Disclaimer & Credits

* This project is developed strictly for backup, preservation, and homebrew purposes.
* All trademarks, game names, and logos belong to their respective copyright holders.
* Special thanks to the PS4 homebrew community, scene developers (Jabu, flatz, cfwprophet, CyB1K, SvenGDK, and xXxTheDarkprogramerxXx) for their pioneering research in PlayStation 2 emulation on PlayStation 4.

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
