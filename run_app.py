"""Ponto de entrada para empacotar com o PyInstaller (ver packaging/atabot.spec).

Em dev use `python -m app`; este arquivo existe porque o PyInstaller precisa de um
script de entrada (não aceita `-m`).
"""
from app.__main__ import main

if __name__ == "__main__":
    main()
