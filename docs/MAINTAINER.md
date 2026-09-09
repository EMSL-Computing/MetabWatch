# Maintainer / development

Lab Windows PCs: [Windows install](INSTALL.md) (Python, venv, desktop shortcut).
Do not copy that recipe here.

This page is for people who develop MetabWatch or run it outside the lab
Windows setup.

## Python

Use **Python 3.10+**. From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
```

Thermo `.raw` access uses CoreMS + pythonnet (Mono on macOS/Linux). Follow [CoreMS on GitHub](https://github.com/EMSL-Computing/CoreMS)
(Installation → Thermo Raw File Access).

Tests and CLI notes: [cli.md](cli.md) (Developers). Releases: [RELEASING.md](RELEASING.md).
After a versioned release, make a new Windows shortcut per [INSTALL.md](INSTALL.md).

## macOS (developers only)

Lab use is **Windows**. macOS is unsupported for operators.

If you develop on a Mac, install Python 3.10+ and the venv as above, then follow
CoreMS for Mono + pythonnet.
