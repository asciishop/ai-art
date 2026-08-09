"""
Lector del registro central de personajes (personajes.yaml).

Es la ÚNICA forma en que el resto del código conoce a los personajes. Nadie
codifica rutas ni nombres de LoRA a mano: todo pasa por aquí. Así, añadir un
personaje es tocar el YAML y nada más.

Uso:
    from registro import cargar, personaje, activos
    p = personaje("va91")
    print(p.system_prompt_texto())   # lee el .md ya resuelto a ruta absoluta
"""

import os
from dataclasses import dataclass

try:
    import yaml
except ImportError:
    raise SystemExit("[error] Falta PyYAML.  pip install pyyaml")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML = os.path.join(RAIZ, "personajes.yaml")


@dataclass
class Personaje:
    id: str
    nombre: str
    activo: bool
    lora_texto: str
    adapter: str
    system_prompt: str
    coleccion: str
    memory: str
    lora_imagen: str
    trigger: str
    saludo: str
    color: str
    # --- voz sintetizada en el pod (Piper + efectos, backend/voz.py) ---
    voz_modelo: str = ""        # voz de Piper; "" = la de por defecto
    voz_androide: float = 0.75  # 0-1: cuánta máquina (armónicos inarmónicos)
    voz_lejania: float = 0.35   # 0-1: cuánta transmisión rota. Ojo: por encima
                                # de 0.8 se pierde inteligibilidad.
    # --- voz del navegador (Web Speech API) · solo si falla la de arriba ---
    voz_pitch: float = 1.0    # tono: <1 grave, >1 agudo. Diferencia personajes.
    voz_rate: float = 1.0     # velocidad: <1 lento, >1 rápido.

    def _abs(self, rel: str) -> str:
        return rel if os.path.isabs(rel) else os.path.join(RAIZ, rel)

    def adapter_abs(self) -> str:
        return self._abs(self.adapter)

    def memory_abs(self) -> str:
        return self._abs(self.memory)

    def system_prompt_texto(self) -> str:
        """Devuelve el System Prompt del personaje ya leído del .md.

        Extrae el bloque ```text si existe (mismo formato que system_prompt.md
        del proyecto original); si no, devuelve el archivo entero."""
        import re
        ruta = self._abs(self.system_prompt)
        if not os.path.exists(ruta):
            return ""
        txt = open(ruta, encoding="utf-8").read()
        m = re.search(r"```text\s*\n(.*?)```", txt, re.DOTALL)
        return (m.group(1) if m else txt).strip()


_cache = None


def cargar() -> dict:
    """Lee personajes.yaml y devuelve {meta, personajes:{id:Personaje}}."""
    global _cache
    if _cache is not None:
        return _cache
    with open(YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    personajes = {}
    for pid, c in data.get("personajes", {}).items():
        personajes[pid] = Personaje(id=pid, **c)
    _cache = {
        "modelo_base": data.get("modelo_base"),
        "modelo_imagen": data.get("modelo_imagen"),
        "personajes": personajes,
    }
    return _cache


def personaje(pid: str) -> Personaje:
    p = cargar()["personajes"].get(pid)
    if p is None:
        raise KeyError(f"Personaje desconocido: {pid}. "
                       f"Válidos: {', '.join(cargar()['personajes'])}")
    return p


def activos() -> list:
    """Solo los personajes marcados activo:true (los que la web debe mostrar)."""
    return [p for p in cargar()["personajes"].values() if p.activo]


if __name__ == "__main__":
    reg = cargar()
    print(f"Modelo base texto : {reg['modelo_base']}")
    print(f"Modelo base imagen: {reg['modelo_imagen']}\n")
    for p in reg["personajes"].values():
        estado = "ACTIVO" if p.activo else "pendiente"
        sp = len(p.system_prompt_texto())
        print(f"  [{estado:9}] {p.id:5} {p.nombre}")
        print(f"              lora_texto={p.lora_texto}  coleccion={p.coleccion}"
              f"  trigger={p.trigger}  system_prompt={sp} chars")
