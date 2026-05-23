"""Generate typos for every keyword in crops.yaml and populate typos lists."""

import re
from ruamel.yaml import YAML

# Only the most realistic phonetic confusions (especially for Indian-English users)
PHONETIC_SUBS = [
    ("ph", "f"), ("f", "ph"),
    ("c", "k"), ("k", "c"),
    ("ck", "k"),
    ("ee", "i"), ("i", "ee"),
    ("ea", "e"), ("e", "ea"),
    ("ou", "ow"), ("ow", "ou"),
    ("tion", "shun"),
    ("er", "ar"), ("ar", "er"),
    ("z", "s"), ("s", "z"),
    ("y", "i"), ("i", "y"),
    ("ss", "s"), ("s", "ss"),
    ("ll", "l"), ("l", "ll"),
    ("tt", "t"),
    ("nn", "n"),
    ("rr", "r"),
    ("mm", "m"),
    ("gg", "g"),
    ("pp", "p"),
    ("bb", "b"),
    ("dd", "d"),
    ("gh", "g"),
    ("kn", "n"),
    ("mb", "m"),
]


def transpose_adjacent(word):
    results = []
    for i in range(len(word) - 1):
        t = list(word)
        t[i], t[i + 1] = t[i + 1], t[i]
        candidate = "".join(t)
        if candidate != word:
            results.append(candidate)
    return results


def delete_char(word):
    if len(word) <= 2:
        return []
    results = []
    for i in range(len(word)):
        candidate = word[:i] + word[i + 1:]
        if candidate != word and len(candidate) >= 3:
            results.append(candidate)
    return results


def double_char(word):
    results = []
    for i in range(len(word)):
        if word[i].isalpha():
            candidate = word[:i] + word[i] + word[i:]
            if candidate != word:
                results.append(candidate)
    return results


def keyboard_sub(word):
    results = []
    for i, ch in enumerate(word):
        if ch in KEYBOARD_ADJACENCY:
            for replacement in KEYBOARD_ADJACENCY[ch]:
                candidate = word[:i] + replacement + word[i + 1:]
                if candidate != word:
                    results.append(candidate)
    return results


def phonetic_sub(word):
    results = []
    for original, replacement in PHONETIC_SUBS:
        idx = 0
        while True:
            pos = word.lower().find(original, idx)
            if pos == -1:
                break
            candidate = word[:pos] + replacement + word[pos + len(original):]
            if candidate.lower() != word.lower():
                results.append(candidate)
            idx = pos + 1
    return results


def typos_for_word(word):
    """Generate typos for a single word (no spaces)."""
    if len(word) <= 2:
        return []
    candidates = set()
    candidates.update(transpose_adjacent(word))
    candidates.update(delete_char(word))
    # double_char and phonetic only for words >= 4 chars to avoid noise
    if len(word) >= 4:
        candidates.update(phonetic_sub(word))
    # Remove anything that matches the original (case-insensitive)
    candidates = {c for c in candidates if c.lower() != word.lower()}
    return list(candidates)


def typos_for_phrase(phrase):
    """Generate typos for a keyword that may be a multi-word phrase."""
    words = phrase.split()
    all_typos = set()
    for i, word in enumerate(words):
        # Only generate typos for words longer than 2 chars
        if len(word) <= 2:
            continue
        word_typos = typos_for_word(word)
        for t in word_typos:
            new_phrase = " ".join(words[:i] + [t] + words[i + 1:])
            if new_phrase.lower() != phrase.lower():
                all_typos.add(new_phrase)
    return list(all_typos)


def generate_all_typos(keywords):
    """Generate and deduplicate typos for a full list of keywords."""
    keyword_set = {k.lower() for k in keywords}
    all_typos = set()
    for kw in keywords:
        for t in typos_for_phrase(kw):
            if t.lower() not in keyword_set:
                all_typos.add(t)
    return sorted(all_typos)


def main():
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.best_sequence_indent = 4
    yaml.best_map_flow_style = False

    with open("crops.yaml", "r") as f:
        data = yaml.load(f)

    crops = data["Crops"]
    total_filled = 0
    total_typos = 0

    for crop_name, crop_data in crops.items():
        keywords = crop_data.get("keywords", [])
        if not keywords:
            continue
        typos = generate_all_typos(keywords)
        crop_data["typos"] = typos
        total_filled += 1
        total_typos += len(typos)
        print(f"  {crop_name}: {len(typos)} typos")

    with open("crops.yaml", "w") as f:
        yaml.dump(data, f)

    print(f"\nDone: {total_filled} crops, {total_typos} total typos")


if __name__ == "__main__":
    main()
