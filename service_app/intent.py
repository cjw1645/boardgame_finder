"""Explainable Korean preference rules; no remote model calls."""
import re

PREFERENCES = {
    '마피아': ('마피아', '정체 숨기기', '정체숨기기', '역할', '배신자'),
    '추리': ('추리', 'deduction', '미스터리'),
    '협력': ('협력', '협동', 'cooperative'),
    '전략': ('전략', '전략게임', 'strategy', '일꾼 놓기', '덱 구성'),
    '파티': ('파티', 'party'),
    '블러핑': ('블러핑', 'bluffing'),
}
ALIASES = {'협동': '협력', '마피아류': '마피아', '심리전': '블러핑', '머리쓰는': '전략'}


def preferences(query):
    query = query.lower()
    excluded = []
    for word in (*PREFERENCES, *ALIASES):
        pattern = rf'{word}(?:는|은|을|를|게임)?\s*(?:말고|제외|빼고|싫어)'
        if re.search(pattern, query):
            excluded.append(ALIASES.get(word, word))
            query = re.sub(pattern, ' ', query)
    easy = bool(re.search(r'초보|입문|쉬운|쉽게|간단한', query))
    query = re.sub(r'초보자?(?:용|도)?|입문(?:자|용)?|쉬운|쉽게|간단한', ' ', query)
    for old, new in ALIASES.items():
        query = query.replace(old, new)
    query = re.sub(r'(협력|추리|전략|파티|마피아|블러핑)\s*게임', r'\1', query)
    return query, easy, excluded


def is_easy(row):
    difficulty = str(row.get('difficulty', '')).lower().strip()
    return difficulty in ('초급', '쉬움', '입문', 'easy', 'very easy')
