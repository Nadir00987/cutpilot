"""CutPilot AI — keyword extraction stage.

TF-IDF-ish noun-phrase extraction WITHOUT heavy NLP libs:
regex tokenizer + stopword list + unigram/bigram/trigram frequency.
score = tf * (phrase length)^1.5. Top ~20 phrases with the span of their
first occurrence. These drive kinetic-text emphasis + B-roll search.
"""

from __future__ import annotations

import math
import re

STOPWORDS = {
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself",
    "she", "her", "hers", "herself", "it", "its", "itself", "they", "them",
    "their", "theirs", "themselves", "what", "which", "who", "whom", "this",
    "that", "these", "those", "am", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "having", "do", "does", "did", "doing",
    "a", "an", "the", "and", "but", "if", "or", "because", "as", "until",
    "while", "of", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below", "to",
    "from", "up", "down", "in", "out", "on", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same",
    "so", "than", "too", "very", "can", "will", "just", "don", "should",
    "now", "um", "uh", "erm", "ah", "er", "hmm", "like", "know", "get",
    "got", "go", "going", "let", "lets", "well", "really", "actually",
    "basically", "literally", "stuff", "thing", "things", "something",
    "everything", "nothing", "kind", "kinda", "sort", "maybe", "probably",
    "today", "guys", "everyone", "hey", "hi", "hello", "okay", "yeah",
    "yes", "nope", "right", "alright", "im", "ive", "dont", "wont", "cant",
    "its", "thats", "theres", "youre", "were", "theyre", "also",
}


def _clean(w: str) -> str:
    return re.sub(r"[^\w']", "", w or "").lower()


def extract_keywords(words: list[dict], top_n: int = 20) -> list[dict]:
    toks = [_clean(w["word"]) for w in words]
    # positions of content tokens
    ngrams: dict[tuple[str, ...], dict] = {}
    for n in (1, 2, 3):
        for i in range(len(toks) - n + 1):
            gram = tuple(toks[i:i + n])
            if any(g in STOPWORDS or len(g) < 3 for g in gram):
                continue
            # skip n-grams with no alpha at all
            if not any(re.search(r"[a-zA-Z]", g) for g in gram):
                continue
            key = gram
            if key not in ngrams:
                wi, wj = words[i], words[i + n - 1]
                ngrams[key] = {
                    "count": 0,
                    "start": wi["start"],
                    "end": wj["end"],
                }
            ngrams[key]["count"] += 1

    scored = []
    for gram, info in ngrams.items():
        tf = info["count"]
        if len(gram) == 1 and tf < 2:
            continue
        if len(gram) > 1 and tf < 2 and len(words) > 60:
            continue
        score = tf * (len(gram) ** 1.5)
        scored.append({
            "phrase": " ".join(gram),
            "score": round(score, 2),
            "start": info["start"],
            "end": info["end"],
        })
    # de-duplicate: drop a unigram already covered by a higher-scoring bigram
    scored.sort(key=lambda k: -k["score"])
    kept, seen_sets = [], []
    for k in scored:
        tokens = set(k["phrase"].split())
        if any(tokens <= s for s in seen_sets):
            continue
        kept.append(k)
        seen_sets.append(tokens)
        if len(kept) >= top_n:
            break
    return kept
