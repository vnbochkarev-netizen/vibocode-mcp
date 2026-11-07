#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Каталог действий: поиск нужных эндпоинтов вместо описания всех в контексте."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = Path(os.environ.get("VIBOCODE_CATALOG", _ROOT / "catalog.json"))

# Намерение -> канонический английский глагол. Русский запрос должен находить
# английский каталог: без этого поиск по каталогу Stripe/GitHub на русском даёт ноль.
VERBS = {
    "create": "POST", "add": "POST", "new": "POST", "make": "POST", "send": "POST", "post": "POST",
    "get": "GET", "list": "GET", "show": "GET", "read": "GET", "fetch": "GET", "retrieve": "GET",
    "update": "PATCH", "edit": "PATCH", "change": "PATCH", "modify": "PATCH", "set": "PATCH",
    "delete": "DELETE", "remove": "DELETE", "cancel": "DELETE", "destroy": "DELETE",
    "создать": "POST", "создай": "POST", "добавить": "POST", "добавь": "POST", "новый": "POST",
    "отправить": "POST", "отправь": "POST", "выставить": "POST", "оформить": "POST",
    "получить": "GET", "покажи": "GET", "показать": "GET", "список": "GET", "найти": "GET",
    "найди": "GET", "прочитать": "GET", "читать": "GET", "сколько": "GET", "какой": "GET",
    "изменить": "PATCH", "измени": "PATCH", "обновить": "PATCH", "обнови": "PATCH", "правка": "PATCH",
    "удалить": "DELETE", "удали": "DELETE", "отменить": "DELETE", "отмени": "DELETE", "снять": "DELETE",
}

# Существительные: русский корень/слово -> английские основы, которые ищем в каталоге.
NOUNS = {
    "платёж": ["payment"], "платеж": ["payment"], "платежи": ["payment"], "оплата": ["payment", "charge"],
    "возврат": ["refund"], "вернуть": ["refund"], "возвратить": ["refund"],
    "клиент": ["customer"], "клиенты": ["customer"], "покупатель": ["customer", "buyer"],
    "подписка": ["subscription"], "подписки": ["subscription"], "подписчик": ["subscriber"],
    "счёт": ["invoice"], "счет": ["invoice"], "счёт-фактура": ["invoice"], "инвойс": ["invoice"],
    "товар": ["product"], "товары": ["product"], "продукт": ["product"],
    "заказ": ["order"], "заказы": ["order"], "корзина": ["cart"], "баланс": ["balance"],
    "остаток": ["balance", "stock"], "склад": ["inventory", "stock"], "остатки": ["stock"],
    "репозиторий": ["repo", "repository"], "репозитории": ["repo", "repository"],
    "звёзды": ["star", "stargazer"], "звезды": ["star", "stargazer"], "звезда": ["star"],
    "пользователь": ["user"], "пользователи": ["user"], "юзер": ["user"],
    "файл": ["file"], "файлы": ["file"], "сообщение": ["message"], "сообщения": ["message"],
    "чат": ["chat"], "канал": ["channel"], "письмо": ["email", "message"], "почта": ["email"],
    "встреча": ["event"], "календарь": ["calendar"], "задача": ["task", "issue"],
    "ошибка": ["error"], "логи": ["log"], "метрика": ["metric"], "цена": ["price"],
    "скидка": ["coupon", "discount"], "купон": ["coupon"], "доставка": ["shipping"],
    "адрес": ["address"], "отчёт": ["report"], "отчет": ["report"], "документ": ["document"],
    "договор": ["contract"], "событие": ["event"], "запрос на слияние": ["pull"], "пул-реквест": ["pulls"],
    "issue": ["issues"], "коммит": ["commit"], "коммиты": ["commit"], "ветка": ["branch"],
    "тег": ["tag", "release"], "релиз": ["release"], "статус": ["status"], "номер": ["number"],
}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD = re.compile(r"[^0-9a-zа-яё]+")
_PARAM = re.compile(r"\{[^}]*\}")


def load() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _norm(w: str) -> str:
    return w.replace("ё", "е").lower()


def _tokens(text: str) -> list[str]:
    """PostPaymentIntents -> [post, payment, intents]; /v1/payment_intents -> [v1, payment, intents]."""
    return [t for t in _WORD.split(_norm(_CAMEL.sub(" ", text))) if t]


def _same(a: str, b: str) -> bool:
    """Равенство с учётом английского множественного числа: subscription == subscriptions."""
    if a == b:
        return True
    sa, sb = (a[:-1] if a.endswith("s") else a), (b[:-1] if b.endswith("s") else b)
    if sa == sb:
        return True
    return a.endswith(b + "s") or b.endswith(a + "s")


def _query_terms(query: str) -> tuple[list[str], set[str]]:
    q = _norm(query)
    terms: list[str] = []
    methods: set[str] = set()

    for ru, en in sorted(NOUNS.items(), key=lambda kv: -len(kv[0])):  # многословные первыми
        if " " in ru and ru in q:
            terms.extend(en)
            q = q.replace(ru, " ")

    for raw in _WORD.split(q):
        if len(raw) < 2:
            continue
        if raw in VERBS:
            methods.add(VERBS[raw])
            continue
        if raw in NOUNS:
            terms.extend(NOUNS[raw])
            continue
        stem = raw[:5]
        hit = [en for ru, en in NOUNS.items() if " " not in ru and ru.startswith(stem)]
        if hit:
            for en in hit:
                terms.extend(en)
            continue
        terms.append(raw)
    return list(dict.fromkeys(terms)), methods


def _score(query: str, action: dict) -> int:
    terms, methods = _query_terms(query)
    if not terms and not methods:
        return 0

    name_toks = _tokens(action.get("name", ""))
    path = action.get("path", "")
    # ресурсные сегменты пути без версии и без параметров: /v1/charges/{charge}/refund -> charges/refund
    res_toks = [t for t in _tokens(_PARAM.sub(" ", path)) if not re.fullmatch(r"v\d+|\d+", t)]
    resource = "/".join(res_toks)
    first, last = (res_toks[0] if res_toks else ""), (res_toks[-1] if res_toks else "")
    desc = _norm(action.get("desc", ""))

    score = 0
    for t in terms:
        if any(_same(tok, t) for tok in name_toks):
            score += 7
        elif any(tok.startswith(t[:4]) for tok in name_toks) and len(t) >= 4:
            score += 4
        if any(tok.startswith(t[:4]) for tok in res_toks) and len(t) >= 4:
            score += 3
        if t in desc or (len(t) >= 4 and t[:5] in desc):
            score += 2
    if not score:
        return 0

    if methods:
        score += 6 if action.get("method") in methods else -3

    # попадание в сам ресурс: точное важнее префикса, префикс важнее «где-то внутри пути»
    for t in terms:
        if _same(first, t) or _same(last, t):
            score += 10
        elif first.startswith(t[:4]) or last.startswith(t[:4]):
            score += 6
        elif t[:4] in resource:
            score += 2
    # глубокий путь — обычно подресурс, а не то, что просили
    score -= 2 * max(0, len(res_toks) - 1)
    return score


def search(query: str, limit: int = 4) -> list[dict]:
    cat = load()
    scored = [(s, a) for a in cat["actions"] if (s := _score(query, a)) > 0]
    scored.sort(key=lambda x: (-x[0], len(x[1].get("path", ""))))
    return [a for _, a in scored[:limit]]


def signature(action: dict) -> str:
    """Компактная сигнатура для модели: без описаний, только то, что нужно для вызова."""
    auth = "" if action.get("auth") is False else " (нужна сессия)"
    return f'{action["name"]}: {action["method"]} {action["path"]}{auth}'


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "баланс"
    for a in search(q):
        print(signature(a), "—", a["desc"])
