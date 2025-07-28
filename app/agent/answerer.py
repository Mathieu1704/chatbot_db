import json
import os
from bson import ObjectId
from openai import AsyncOpenAI
from datetime import datetime
from collections import defaultdict


# Client OpenAI asynchrone
llm = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Prompt système pour les réponses normales (FR/EN selon user_locale)
def _system_prompt(user_locale: str) -> str:
    if user_locale.lower().startswith("en"):
        return (
            "You are I-CARE Answerer. Format the response for the user, "
            "in English or French depending on the query.\n"
            "Use deterministic code for known tool results and only fallback to LLM for open-ended answers."
        )
    else:
        return (
            "Tu es I-CARE Answerer. Formate la réponse pour l’utilisateur, "
            "en français ou anglais selon la question.\n"
            "Utilise du code pour les cas connus et LLM uniquement pour le reste."
        )

async def answer(
    user_locale: str,
    tool_result: dict,
    original_query: str
) -> str:
    """
    Formate un résultat d’outil pour l’utilisateur.

    Règles :
    • 'clarify'  → le LLM rédige la question de précision.
    • 'fields'   → liste les champs d’une collection.
    • 'documents'→ renvoie un résumé humain (le tableau JSON brut part dans la
                    réponse HTTP, pas dans ce texte).
    • 'items'    → vue de connectivité.
    • 'counts'   → résumé état batterie.
    • 'category' → liste des adresses d’une même catégorie batterie.
    • sinon      → fallback LLM.
    """

    # ------------------------------------------------------------------ #
    # 1. Clarification : on délègue au LLM                               #
    # ------------------------------------------------------------------ #
    if "clarify" in tool_result:
        c       = tool_result["clarify"]
        raw     = c.get("raw", "").strip()
        cands   = [s.replace("_", " ").title() for s in c.get("candidates", [])]

        if user_locale.lower().startswith("en"):
            system_msg = (
                "You are an assistant whose role is to politely ask the user "
                "to clarify an ambiguous company name.\n"
                f"Original query: “{original_query}”\n"
                f"Raw input: “{raw}”\n"
                f"Possible matches: {', '.join(cands) or 'none'}\n"
                "Please ask one short question."
            )
            if not raw:
                user_msg = "The user did not specify a company name."
            elif not cands:
                user_msg = f"The user provided '{raw}', which I do not recognize."
            else:
                opts = " or ".join(cands)
                user_msg = (
                    f"The user provided '{raw}', but multiple companies match: {opts}. "
                    "Which one would you like?"
                )
        else:
            system_msg = (
                "Vous êtes un assistant dont le rôle est de demander poliment "
                "à l'utilisateur de préciser le nom d'une entreprise ambiguë.\n"
                f"Requête initiale : « {original_query} »\n"
                f"Brut : « {raw} »\n"
                f"Options : {', '.join(cands) or 'aucune'}\n"
                "Formulez une question courte."
            )
            if not raw:
                user_msg = "L'utilisateur n'a précisé aucune entreprise."
            elif not cands:
                user_msg = f"L'utilisateur a fourni « {raw} », que je ne reconnais pas."
            else:
                opts = " ou ".join(cands)
                user_msg = (
                    f"L'utilisateur a fourni « {raw} », plusieurs entreprises correspondent : {opts}. "
                    "Laquelle choisissez-vous ?"
                )

        resp = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg}
            ],
            temperature=0.2
        )
        return resp.choices[0].message.content.strip()

    # ------------------------------------------------------------------ #
    # 2. Introspection de schéma                                         #
    # ------------------------------------------------------------------ #
    if "fields" in tool_result:
        label = "Available fields: " if user_locale.lower().startswith("en") else "Champs disponibles : "
        return label + ", ".join(tool_result["fields"])

        # ------------------------------------------------------------------ #
    # 3. Résultats de requête (documents)                                #
    #    -> Ne pas renvoyer le JSON complet ; résumé mono-DB ou grouping  #
    # ------------------------------------------------------------------ #
    if "documents" in tool_result:
        docs = tool_result["documents"] or []
        total = len(docs)

        if total == 0:
            return "No matching documents." if user_locale.startswith("en") else "Aucun document ne correspond."

        # On convertit proprement dates / ObjectId pour la preview éventuelle
        def _normalize(d):
            d = {**d}
            _id = d.pop("_id", None)
            if isinstance(_id, ObjectId):
                d["id"] = str(_id)
            for k, v in d.items():
                if isinstance(v, (datetime,)):
                    d[k] = v.isoformat()
            return d

        preview_docs = [_normalize(d) for d in docs[:5]]

        # Détection cross-DB : présence du champ "_company" ?
        is_cross = any("_company" in d for d in docs)
        if is_cross:
            # Groupement par base
            grouped = defaultdict(list)
            for d in docs:
                comp = d.get("_company", "inconnue")
                clean = {k: v for k, v in d.items() if k != "_company"}
                grouped[comp].append(clean)

            lines = []
            is_en = user_locale.lower().startswith("en")

            for comp, items in grouped.items():
                count = len(items)
                if is_en:
                    # gestion du pluriel en anglais
                    label = "result" if count == 1 else "results"
                else:
                    # pluriel en français
                    label = "résultat" if count == 1 else "résultats"

                # liste à puce
                lines.append(f" Pour {comp} : {count} {label} \n\n")

            # join avec saut de ligne entre chaque puce
            return "\n".join(lines)

        else:
            # Mono-DB : comportement existant inchangé
            if user_locale.lower().startswith("en"):
                if total == 1:
                    header = "1 element found."
                    intro  = "Here is a summary:"
                else:
                    header = f"{total} elements founded."
                    intro  = "Here is a summary:"
            else:
                if total == 1:
                    header = "1 élément a été trouvé."
                    intro  = "Voici un résumé :"
                else:
                    header = f"{total} éléments on été trouvés.\n"
                    intro  = "Voici un tableau recapitulatif :"

            return "\n".join([header, intro])


    # ------------------------------------------------------------------ #
    # 4. Connectivity Overview #
    # ------------------------------------------------------------------ #
    if {"items", "connected_count", "disconnected_count"} <= tool_result.keys():
        conn = tool_result["connected_count"]
        disc = tool_result["disconnected_count"]

        if user_locale.lower().startswith("en"):
            return f"**{disc} offline sensors**, {conn} connected."
        else:
            return f"Il y a {disc} capteurs hors ligne, et {conn} connectés. \n Voici la liste : \n"


    # ------------------------------------------------------------------ #
    # 5. Vue batterie (totaux)                                           #
    # ------------------------------------------------------------------ #
    if "counts" in tool_result and "items_critical" in tool_result:
        cnt = tool_result["counts"]
        if user_locale.lower().startswith("en"):
            lines = [
                "**Battery Status**",
                f"🔴 Critical : {cnt['critical']}",
                f"🟠 Warning  : {cnt['warning']}",
                f"✅ OK       : {cnt['ok']}"
            ]
        else:
            lines = [
                "**État des batteries**",
                f"🔴 Critique : {cnt['critical']}",
                f"🟠 Alerte   : {cnt['warning']}",
                f"✅ OK       : {cnt['ok']}"
            ]
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # 6. Liste batterie (détails)                                        #
    # ------------------------------------------------------------------ #
    if "category" in tool_result and "addresses" in tool_result:
        cat   = tool_result["category"]
        addrs = tool_result["addresses"]
        header = (
            f"**Battery {cat.title()}** – {len(addrs)} nodes"
            if user_locale.lower().startswith("en")
            else f"**Liste des batteries « {cat} »** – {len(addrs)} capteurs"
        )
        items = [f"- {addr}" for addr in addrs]
        return "\n".join([header] + items)
    # ------------------------------------------------------------------ #
    # 7. Network topology                                                #
    # ------------------------------------------------------------------ #
    if "topology" in tool_result:
        topo = tool_result["topology"] or {}

        if isinstance(topo, dict) and {"nodes", "links"} <= topo.keys():
            nodes = topo.get("nodes", [])
            gws   = sum(1 for n in nodes if n.get("type") == "gateway")
            ext   = sum(1 for n in nodes if n.get("type") == "extender")
            sens  = sum(1 for n in nodes if n.get("type") == "sensor")
        else:
            gws  = len(topo)
            ext  = sum(len(g.get("extenders", [])) for g in topo)
            sens = sum(
                len(g.get("sensors_direct", [])) +
                sum(len(e.get("sensors", [])) for e in g.get("extenders", []))
                for g in topo
            )

        if user_locale.lower().startswith("en"):
            return "\n".join([
                "**Network topology**",
                f"Gateways : {gws}",
                f"Range-extenders : {ext}",
                f"Sensors : {sens}"
            ])
        else:
            return "\n".join([
                "**Topologie réseau**",
                f"Gateways : {gws}",
                f"Range-extenders : {ext}",
                f"Capteurs : {sens}"
            ])

        
    # ------------------------------------------------------------------ #
    # X. Fallback : laisse GPT formater                                  #
    # ------------------------------------------------------------------ #
    system_prompt = _system_prompt(user_locale) + "\nUse the exact company name when referring."
    user_prompt = (
        f"Question : {original_query}\n"
        f"Locale : {user_locale}\n"
        f"TOOL_RESULT: {json.dumps(tool_result, ensure_ascii=False)}"
    )
    resp = await llm.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        temperature=0
    )
    return resp.choices[0].message.content.strip()
