"""Find a person in Jira by name, email or account id, and say whether the match is unique, ambiguous or missing.

Jira's own search matches only the start of a word of the name or the email, so a typo ("Matiaz" for "Matías") finds
nobody. This module asks Jira once per word of the name, merges the people it returns and ranks them itself, folding
accents and tolerating a one-letter slip. It never picks between two people: it lists them and lets a person choose.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Dict, List, Optional

SIMILAR = 0.8  # similarity at which a slip still counts as the same word
NEAREST = 5  # how many near misses a "none" answer offers


class NotResolved(ValueError):
    """The name matched nobody or several people; the message says which and how to be precise."""

    def __init__(self, message: str, result: dict):
        super().__init__(message)
        self.result = result


def fold(text: str) -> str:
    """Lower case without accents, so "Matías" and "matias" are the same word."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c))
    return plain.lower()


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def _word_score(wanted: str, have: str) -> float:
    if wanted == have:
        return 1.0
    if len(wanted) >= 3 and have.startswith(wanted):
        return 0.9
    ratio = difflib.SequenceMatcher(None, wanted, have).ratio()
    return ratio if ratio >= SIMILAR else 0.0


def _score(wanted: List[str], user: dict) -> tuple:
    """(words matched, total words, similarity summed, every word spelled as in the name) against what was asked for."""
    have = _words(user["name"])
    best = [max((_word_score(w, h) for h in have), default=0.0) for w in wanted]
    return sum(1 for b in best if b > 0), len(wanted), sum(best), all(b == 1.0 for b in best)


def _person(user: dict, score: float = 0.0, exact: bool = False) -> dict:
    """`exact` is False when a slip was forgiven to find them: Maria can come back as Mario, so say so."""
    return {"id": user["id"], "name": user["name"], "email": user.get("email") or "", "score": round(score, 2),
            "exact": exact}


def _result(status: str, candidates: List[dict]) -> dict:
    return {"status": status, "candidates": candidates}


def find(jira, query: str, project: Optional[str] = None) -> dict:
    """{"status": "unique" | "ambiguous" | "none", "candidates": [{id, name, email, score}]}, best first."""
    query = " ".join((query or "").split())
    if not query:
        return _result("none", [])
    if " " not in query and "@" not in query:
        direct = jira.user(query)  # an account id; Jira answers nothing for any other word
        if direct:
            return _result("unique", [_person(direct, 1.0, exact=True)])
    if "@" in query:
        same = [u for u in jira.search_users(query, project) if fold(u.get("email", "")) == fold(query)]
        return _result("unique", [_person(same[0], 1.0, exact=True)]) if len(same) == 1 else _result("none", [])

    wanted = _words(query)
    pool: Dict[str, dict] = {}
    for term in [query] + [w for w in wanted if len(w) >= 2]:
        for user in jira.search_users(term, project):
            pool.setdefault(user["id"], user)

    scored = [(_score(wanted, u), u) for u in pool.values()]
    scored = [(s, u) for s, u in scored if s[0] > 0]
    scored.sort(key=lambda su: (-su[0][0], -su[0][2], su[1]["name"]))
    every = [(s, u) for s, u in scored if s[0] == s[1]]  # every word of the query found in the name
    named = [(s, u) for s, u in every if fold(u["name"]) == fold(query)]  # the whole name, word for word
    spelled = [(s, u) for s, u in every if s[3]]  # every word as written, though the name may have more words

    for winners in (named, spelled):  # whoever is spelled right beats a near miss; two of them are still two people
        if len(winners) == 1:
            return _result("unique", [_person(winners[0][1], winners[0][0][2], exact=True)])
    if len(every) == 1:
        return _result("unique", [_person(every[0][1], every[0][0][2], exact=every[0][0][3])])
    if every:
        return _result("ambiguous", [_person(u, s[2], exact=s[3]) for s, u in every])
    return _result("none", [_person(u, s[2]) for s, u in scored[:NEAREST]])


def _listing(candidates: List[dict]) -> str:
    return "\n".join(f"  - {c['name']} <{c['email'] or 'email hidden'}> ({c['id']})" for c in candidates)


def resolve(jira, query: str, project: Optional[str] = None) -> dict:
    """The one person the query names, or NotResolved: never a guess between several."""
    result = find(jira, query, project)
    if result["status"] == "unique":
        return result["candidates"][0]
    if result["status"] == "ambiguous":
        raise NotResolved(f"{query!r} matches {len(result['candidates'])} people; pass the email or accountId of the "
                          f"one you mean:\n{_listing(result['candidates'])}", result)
    near = f" Closest:\n{_listing(result['candidates'])}" if result["candidates"] else ""
    raise NotResolved(f"nobody in Jira matches {query!r}.{near}", result)
