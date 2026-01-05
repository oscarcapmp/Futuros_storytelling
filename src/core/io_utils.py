
def leer_bool(prompt: str, default: bool = False) -> bool:
    val = input(prompt).strip().lower()
    if val == "":
        return default
    return val in ["s", "si", "sí", "y", "yes", "true", "t", "1"]


def leer_int(prompt: str, default: int) -> int:
    val = input(prompt).strip()
    if val == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def leer_float(prompt: str, default: float) -> float:
    val = input(prompt).strip()
    if val == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default
