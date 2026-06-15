#!/usr/bin/env python3
"""
Helper para ejecutar `kimi --yolo` de forma automatizada vía pexpect.
Recibe un prompt por stdin o archivo y guarda el output limpio en un archivo.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import pexpect


def strip_ansi(text):
    """Elimina códigos de escape ANSI."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def run_kimi_yolo(prompt, output_path, max_wait_seconds=90, ready_timeout=30):
    """Ejecuta kimi --yolo con el prompt dado y guarda output limpio."""
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt vacío")

    cmd = ["kimi", "--yolo"]
    child = pexpect.spawn(cmd[0], cmd[1:], encoding="utf-8", timeout=ready_timeout)

    output_lines = []

    def read_available():
        try:
            while child.buffer or child.before is not None:
                child.expect([r"\r\n", r"\n", pexpect.TIMEOUT], timeout=0.5)
                line = strip_ansi(child.before or "")
                if line:
                    output_lines.append(line)
        except pexpect.TIMEOUT:
            pass

    # Esperar a que Kimi esté listo
    try:
        child.expect([r"K2\.7 Code is ready", r"yolo"], timeout=ready_timeout)
        read_available()
    except pexpect.TIMEOUT:
        read_available()

    # Pequeña pausa para estabilizar
    time.sleep(2)
    read_available()

    # Enviar prompt
    child.sendline(prompt)

    # Esperar mientras trabaja
    start = time.time()
    last_output_len = 0
    while time.time() - start < max_wait_seconds:
        try:
            child.expect([r"\r\n", r"\n"], timeout=2)
            line = strip_ansi(child.before or "")
            if line:
                output_lines.append(line)
            last_output_len = len(output_lines)
        except pexpect.TIMEOUT:
            # Si no hay output nuevo durante 5 segundos, consideramos que terminó
            if len(output_lines) == last_output_len and len(output_lines) > 0:
                break
            continue

    # Intentar salir limpiamente
    try:
        child.sendcontrol("c")
        time.sleep(0.5)
        child.sendline("/exit")
        child.expect(pexpect.EOF, timeout=10)
    except pexpect.TIMEOUT:
        child.terminate(force=True)
    except Exception:
        child.terminate(force=True)

    # Leer cualquier cosa restante
    try:
        remaining = child.read()
        if remaining:
            for line in remaining.splitlines():
                cleaned = strip_ansi(line)
                if cleaned:
                    output_lines.append(cleaned)
    except Exception:
        pass

    # Guardar output
    out_text = "\n".join(output_lines)
    Path(output_path).write_text(out_text, encoding="utf-8")
    return out_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", required=True, help="Archivo con el prompt")
    parser.add_argument("--output", required=True, help="Archivo de salida")
    parser.add_argument("--wait", type=int, default=90, help="Segundos máximos de espera")
    args = parser.parse_args()

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    out = run_kimi_yolo(prompt, args.output, max_wait_seconds=args.wait)
    print(f"Output guardado en {args.output} ({len(out)} chars)")


if __name__ == "__main__":
    main()
