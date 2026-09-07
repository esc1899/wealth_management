#!/usr/bin/env python
"""Prüft, ob ein aufgeschriebener ENCRYPTION_KEY + salt.bin die DB wirklich entschlüsselt.

Warum es dieses Skript gibt
---------------------------
ENCRYPTION_KEY lässt sich nicht neu erzeugen.  Bevor er aus der .env verschwindet
und nur noch im Schlüsselbund liegt, muss anderswo eine Kopie liegen, die einen
Schlüsselbund-Verlust übersteht.  Eine Kopie, die man nie ausprobiert hat, ist
aber nur ein Zettel — Tippfehler, fehlendes Zeichen, falscher Salt fallen erst
im Ernstfall auf, und dann ist es zu spät.

Der Schlüssel ist ein PBKDF2-*Passwort*, nicht der Fernet-Schlüssel selbst:

    Fernet-Key = PBKDF2(Passwort, data/salt.bin, 480_000 Runden)

Beides wird gebraucht.  Fehlt salt.bin, legt die App bei nächster Gelegenheit
kommentarlos einen neuen an und entschlüsselt danach gar nichts mehr — ohne
Fehlermeldung.  Deshalb prüft dieses Skript wahlweise gegen den aufgeschriebenen
Salt (--salt-b64), nicht nur gegen die Datei auf der Platte.

    python scripts/verify_encryption_key.py
    python scripts/verify_encryption_key.py --salt-b64 "<was im Passwortmanager steht>"

Der Schlüssel wird am Prompt abgefragt, nie als Argument übergeben — sonst stünde
er in der Shell-History und in der Prozessliste.  Die Datenbank wird
schreibgeschützt geöffnet.  Ausgegeben werden nur Zähler, nie ein Klartextwert.
"""

import argparse
import base64
import getpass
import sqlite3
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.encryption import EncryptionService  # noqa: E402

# Absichtlich NICHT config.DB_PATH: Entwicklungs-Sitzungen laufen mit
# DEMO_MODE=true, und die Demo-DB ist unverschlüsselt — hier ist immer die echte
# Datenbank gemeint.
DEFAULT_DB = _PROJECT_ROOT / "data" / "portfolio.db"
DEFAULT_SALT = _PROJECT_ROOT / "data" / "salt.bin"

# (Tabelle, Spalte) — alles, was laut core/storage/positions.py Fernet-Chiffrat ist.
ENCRYPTED_COLUMNS = [
    ("positions", "quantity"),
    ("positions", "purchase_price"),
    ("positions", "notes"),
    ("positions", "extra_data"),
    ("positions", "story"),
]


def parse_salt_text(text: str) -> bytes:
    """Salt aus einer abgetippten/eingefügten Zeichenkette lesen.

    Nachsichtig gegenüber allem, was beim Kopieren aus einem Passwortmanager
    dazukommt: Zeilenumbrüche, Leerzeichen, umschließende Anführungszeichen,
    fehlendes Padding.  Akzeptiert base64 (24 Zeichen für 16 Bytes) ebenso wie
    hex (32 Zeichen) — je nachdem, wie man ihn notiert hat.
    """
    cleaned = "".join(text.split())          # jedes Whitespace raus, auch innen
    cleaned = cleaned.strip("\"'")           # \"abc==\" → abc==

    if not cleaned:
        raise ValueError("leere Eingabe")
    if cleaned.startswith("<") or cleaned.endswith(">"):
        raise ValueError(
            "sieht nach dem Platzhalter aus der Anleitung aus — die spitzen "
            "Klammern gehören nicht mit, dort muss der echte Wert stehen"
        )

    # hex? 32 Zeichen für 16 Bytes
    if len(cleaned) in (32, 64) and all(c in "0123456789abcdefABCDEF" for c in cleaned):
        return bytes.fromhex(cleaned)

    padded = cleaned + "=" * (-len(cleaned) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except Exception:
        bad = sorted({c for c in cleaned if not (c.isalnum() or c in "+/=-_")})
        hint = f" — unerwartete Zeichen: {' '.join(repr(c) for c in bad)}" if bad else ""
        raise ValueError(f"weder gültiges base64 noch hex ({len(cleaned)} Zeichen){hint}")


def load_salt(salt_b64: str | None, salt_path: Path) -> tuple[bytes, str]:
    if salt_b64:
        try:
            salt = parse_salt_text(salt_b64)
        except ValueError as exc:
            sys.exit(
                f"✗ --salt-b64 nicht lesbar: {exc}\n"
                f"  Erwartet wird die Ausgabe von:  base64 -i {salt_path}\n"
                f"  (16 Bytes → 24 Zeichen, endend auf '==')"
            )
        return salt, "aufgeschriebener Salt (--salt-b64)"
    if not salt_path.exists():
        sys.exit(f"✗ {salt_path} fehlt — und ohne Salt ist der Schlüssel wertlos.")
    return salt_path.read_bytes(), f"Datei {salt_path.name}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--salt-file", type=Path, default=DEFAULT_SALT)
    ap.add_argument(
        "--salt-b64",
        help="Salt aus dem Passwortmanager statt aus data/salt.bin — prüft die "
             "Kopie, auf die es im Ernstfall ankommt.",
    )
    ap.add_argument(
        "--from-keychain",
        action="store_true",
        help="Schlüssel aus dem Schlüsselbund (wm-ENCRYPTION_KEY) lesen statt am "
             "Prompt fragen — prüft den frisch angelegten Eintrag, bevor die "
             "Zeile aus der .env gelöscht wird.",
    )
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"✗ Datenbank nicht gefunden: {args.db}")

    salt, salt_source = load_salt(args.salt_b64, args.salt_file)
    print(f"\nDatenbank : {args.db}")
    print(f"Salt      : {salt_source} ({len(salt)} Bytes)")

    if args.from_keychain:
        # Bewusst am Schlüsselbund vorbei an core.secrets: get_secret() würde die
        # Umgebung bevorzugen und damit womöglich den .env-Wert prüfen statt den
        # Eintrag, um den es hier geht.
        from core.secrets import keychain_get, service_name

        print(f"Schlüssel : Schlüsselbund-Eintrag {service_name('ENCRYPTION_KEY')}")
        key = keychain_get("ENCRYPTION_KEY")
        if not key:
            sys.exit(
                f"✗ Kein Eintrag {service_name('ENCRYPTION_KEY')} im Schlüsselbund gefunden.\n"
                f'  Anlegen mit:  security add-generic-password -U -a "$USER" '
                f"-s {service_name('ENCRYPTION_KEY')} -w"
            )
    else:
        key = getpass.getpass("ENCRYPTION_KEY (Eingabe unsichtbar): ").strip()
        if not key:
            sys.exit("✗ Kein Schlüssel eingegeben.")

    enc = EncryptionService(key, salt)

    # Schreibgeschützt: dieses Skript darf unter keinen Umständen etwas verändern.
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    total_ok = total_fail = total_empty = 0
    print()
    for table, column in ENCRYPTED_COLUMNS:
        ok = fail = empty = 0
        for (value,) in conn.execute(f"SELECT {column} FROM {table}"):
            if not value:
                empty += 1
                continue
            try:
                enc.decrypt(value)
                ok += 1
            except Exception:
                fail += 1
        total_ok += ok
        total_fail += fail
        total_empty += empty
        mark = "✓" if fail == 0 else "✗"
        print(f"  {mark} {table}.{column:<16} entschlüsselt: {ok:>4}   fehlgeschlagen: {fail:>4}   leer: {empty:>4}")

    conn.close()

    print(f"\n  Summe: {total_ok} entschlüsselt, {total_fail} fehlgeschlagen, {total_empty} leer\n")

    if total_fail:
        print("✗ Diese Kombination aus Schlüssel und Salt entschlüsselt die Daten NICHT.")
        print("  Nicht auf sie verlassen. ENCRYPTION_KEY in der .env lassen, bis eine")
        print("  geprüfte Kopie existiert.\n")
        return 1
    if total_ok == 0:
        print("⚠ Nichts zu prüfen — keine verschlüsselten Werte gefunden.")
        print("  Läuft das gegen die Demo-DB? Die ist unverschlüsselt (--db angeben).\n")
        return 1

    print("✓ Schlüssel und Salt entschlüsseln die Datenbank vollständig.")
    print("  Diese Kombination ist als Sicherung tauglich — beide Teile zusammen")
    print("  aufbewahren, getrennt vom Schlüsselbund.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
