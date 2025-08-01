import re
import unicodedata

def slugify_company(name: str) -> str:
    """
    Transforme n'importe quelle écriture en une 'slug' compatible DB :
    - met tout en minuscules
    - enlève les accents
    - remplace tout ce qui n'est pas lettre/chiffre par un underscore
    - supprime les underscores en début/fin et les doublons
    """
    # 1) Normaliser la casse et unicode
    s = name.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    # 2) Remplacer les caractères non alphanumériques par '_'
    s = re.sub(r"[^a-z0-9]+", "_", s)
    # 3) Supprimer les _ du début/fin et les doublons
    s = re.sub(r"_+", "_", s).strip("_")
    return s