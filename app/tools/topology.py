"""
app/tools/topology.py
---------------------

Reconstruit un graphe **non dirigé** de connectivité pour une entreprise :

• Chaque document `network_nodes` devient un nœud (`gateway`, `extender`,
  `sensor`, `unknown`).
• Arêtes ajoutées pour :
    – `parent`               (string)
    – `parents[].address`    (string ou objet)
    – `neighbor_gateways`    (string ou objet)
    – `neighbor_transmitters`(string ou objet)
• Les adresses « nulles » (`0000…`) sont ignorées.
• Les nœuds présents en tant que parents / voisins mais absents de la
  collection sont créés avec le type `unknown`.

La sortie est directement compatible avec le front (format `{nodes, links}`).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple, Set, Iterable
from collections import defaultdict

from app.db import get_nodes_collection

# ---------------------------------------------------------------------------
# Constantes & cache
# ---------------------------------------------------------------------------
import os

# Seuils RSSI (en dBm) : par défaut vert ≥ -90, orange ≥ -100, rouge < -100
RSSI_GOOD   = int(os.getenv("RSSI_GOOD",   -90))
RSSI_MEDIUM = int(os.getenv("RSSI_MEDIUM", -100))

# Seuils LQI (0–255) : par défaut good ≥50, medium ≥30, poor <30
LQI_GOOD    = int(os.getenv("LQI_GOOD",    50))
LQI_MEDIUM  = int(os.getenv("LQI_MEDIUM",  30))

NULL_PREFIX  = "0000"
_CACHE_TTL   = 60          # secondes
_CACHE: dict[str, Tuple[float, dict[str, list[dict[str, Any]]]]] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean_addr(addr: Any) -> str | None:
    """Normalise l'adresse, ou retourne None si invalide / nulle."""
    if not addr or not isinstance(addr, str):
        return None
    addr = addr.strip().upper()
    if not addr or addr.startswith(NULL_PREFIX):
        return None
    return addr


def _iter_field_addrs(node: Dict[str, Any], field: str) -> Iterable[str]:
    """Itère sur les adresses d'un champ voisinage (string ou obj)."""
    for entry in node.get(field, []):
        if isinstance(entry, str):
            addr = _clean_addr(entry)
        elif isinstance(entry, dict):
            addr = _clean_addr(entry.get("address"))
        else:
            addr = None
        if addr:
            yield addr


def _iter_parent_addrs(node: Dict[str, Any]) -> Iterable[str]:
    """parent + parents[] → adresses nettoyées."""
    p = _clean_addr(node.get("parent"))
    if p:
        yield p

    for entry in node.get("parents", []):
        if isinstance(entry, str):
            addr = _clean_addr(entry)
        elif isinstance(entry, dict):
            addr = _clean_addr(entry.get("address"))
        else:
            addr = None
        if addr:
            yield addr


def _node_kind(node: Dict[str, Any]) -> str:
    match node.get("node_type"):
        case 1:  return "gateway"
        case 3:  return "extender"
        case 2:  return "sensor"
        case _:  return "unknown"

def _extract_metrics(node: Dict[str, Any], kind: str, raw: dict | None) -> Dict[str, Any]:
    """
    Récupère rssi ou lqi_up/lqi_down selon le lien :
      - pour 'parent' on prend lqi_up, lqi_down et rssi si présents
      - pour 'neighbor' on prend rssi depuis raw (gateway/transmitter)
    """
    m = {}
    if kind == "parent":
        for f in ("rssi", "lqi_up", "lqi_down"):
            v = node.get(f)
            if v is not None:
                m[f] = v
    else:  # neighbor
        if isinstance(raw, dict) and raw.get("rssi") is not None:
            m["rssi"] = raw["rssi"]
    return m

def _classify_quality(metrics: Dict[str, Any]) -> str:
    """
    Retourne 'good', 'medium' ou 'poor' selon la meilleure métrique disponible :
      - on regarde d'abord rssi,
      - sinon lqi_up.
    """
    if (r := metrics.get("rssi")) is not None:
        if r >= RSSI_GOOD:     return "good"
        if r >= RSSI_MEDIUM:  return "medium"
        return "poor"
    if (l := metrics.get("lqi_up")) is not None:
        if l >= LQI_GOOD:      return "good"
        if l >= LQI_MEDIUM:   return "medium"
        return "poor"
    return "unknown"



# ---------------------------------------------------------------------------
# Construction du graphe
# ---------------------------------------------------------------------------
def _collect_nodes_links(nodes: List[Dict[str, Any]]
                         ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    node_kinds: Dict[str, str] = {}
    links_out: List[Dict[str, Any]] = []
    seen_edges: Set[frozenset[str]] = set()

    def _add_node(addr: str, kind: str) -> None:
        prev = node_kinds.get(addr)
        if prev is None or (prev == "unknown" and kind != "unknown"):
            node_kinds[addr] = kind

    for n in nodes:
        src = _clean_addr(n.get("address"))
        if not src:
            continue
        _add_node(src, _node_kind(n))

        # -------------------- parents -------------------------------------
        # Parents: 'parent' unique
        raw_p = n.get("parent")
        addr_p = _clean_addr(raw_p)
        if addr_p:
            key = frozenset((src, addr_p))
            if key not in seen_edges:
                seen_edges.add(key)
                met = _extract_metrics(n, "parent", None)
                qual = _classify_quality(met)
                links_out.append({"source": src, "target": addr_p, "kind": "parent", "metrics": met, "quality": qual})
            _add_node(addr_p, node_kinds.get(addr_p, "unknown"))

        # Parents: liste
        for raw in n.get("parents", []):
            if isinstance(raw, str):
                addr_p = _clean_addr(raw)
            elif isinstance(raw, dict):
                addr_p = _clean_addr(raw.get("address"))
            else:
                addr_p = None
            if not addr_p:
                continue
            key = frozenset((src, addr_p))
            if key not in seen_edges:
                seen_edges.add(key)
                met = _extract_metrics(n, "parent", raw)
                qual = _classify_quality(met)
                links_out.append({"source": src, "target": addr_p, "kind": "parent", "metrics": met, "quality": qual})
            _add_node(addr_p, node_kinds.get(addr_p, "unknown"))

        # Voisins: gateways & transmetteurs
        for field, kind in (("neighbor_gateways", "neighbor"), ("neighbor_transmitters", "neighbor")):
            for raw in n.get(field, []):
                if isinstance(raw, str):
                    addr_n = _clean_addr(raw)
                    raw_entry = None
                elif isinstance(raw, dict):
                    addr_n = _clean_addr(raw.get("address"))
                    raw_entry = raw
                else:
                    continue
                if not addr_n:
                    continue
                key = frozenset((src, addr_n))
                if key not in seen_edges:
                    seen_edges.add(key)
                    met = _extract_metrics(n, "neighbor", raw_entry)
                    qual = _classify_quality(met)
                    links_out.append({"source": src, "target": addr_n, "kind": kind, "metrics": met, "quality": qual})
                _add_node(addr_n, node_kinds.get(addr_n, "unknown"))

    nodes_out = [{"id": addr, "type": kind} for addr, kind in node_kinds.items()]
    return nodes_out, links_out

# ---------------------------------------------------------------------------
# API principale
# ---------------------------------------------------------------------------
def get_network_topology(company: str, use_cache: bool = True
                         ) -> dict[str, list[dict[str, Any]]]:
    """
    Retourne un objet {nodes, links} prêt à être serialisé vers le front.
    """
    if use_cache and company in _CACHE:
        ts, cached = _CACHE[company]
        if time.time() - ts < _CACHE_TTL:
            return cached

    coll = get_nodes_collection(company)
    projection = {
        "_id": 0,
        "address": 1,
        "node_type": 1,
        "battery": 1,
        "last_com": 1,
        "parent": 1,
        "parents": 1,
        "neighbor_gateways": 1,
        "neighbor_transmitters": 1,
        "lqi_up": 1,
        "lqi_down": 1,
        "rssi": 1,
    }
    nodes: List[Dict[str, Any]] = list(coll.find({}, projection))

    nodes_out, links_out = _collect_nodes_links(nodes)

    raw_map = { _clean_addr(n["address"]): n for n in nodes }
    for nd in nodes_out:
        doc = raw_map.get(nd["id"], {})
        nd["battery"] = doc.get("battery")
        nd["last_com"] = doc.get("last_com")
    topo = {"nodes": nodes_out, "links": links_out}

    _CACHE[company] = (time.time(), topo)
    return topo


def topology_to_d3(topology: dict[str, list[dict[str, Any]]]
                   ) -> dict[str, list[dict[str, Any]]]:
    """Ici : identité, pour compat Laravel / anciens appels."""
    return topology
