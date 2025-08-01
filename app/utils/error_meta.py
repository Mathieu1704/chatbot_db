import yaml
from pathlib import Path

_ERR_META_CACHE = None
_ERR_META_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "err_meta.yml"
)

def load_err_meta() -> dict[int, dict]:
    """
    Charge et met en cache le mapping errcode → métadonnées.
    Accepte des clés YAML déjà numériques (0, 1, …) ou hexa sous forme
    de chaîne ("0x01", "0x1A").
    """
    global _ERR_META_CACHE
    if _ERR_META_CACHE is None:
        with _ERR_META_PATH.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        def to_int(key):
            if isinstance(key, int):
                return key                      # déjà un entier
            if isinstance(key, str):
                base = 16 if key.lower().startswith("0x") else 10
                return int(key, base)
            raise TypeError(f"Clé invalide dans err_meta: {key!r}")

        _ERR_META_CACHE = {to_int(k): v for k, v in raw.items()}

    return _ERR_META_CACHE
