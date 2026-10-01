import re

MM_DIGITS = '၀၁၂၃၄၅၆၇၈၉'


def to_eng_digits(text):
    """Convert Myanmar digits (၀-၉) to English digits (0-9)."""
    return ''.join(str(MM_DIGITS.index(ch)) if ch in MM_DIGITS else ch for ch in text)


def clean_line(line):
    """Clean one line of pasted Viber text so the parser can understand it.

    - Collapses repeated dots (.. or ...) into a single dot.
    - Removes leading/trailing dots and dots adjacent to whitespace.
    - Normalises dots around the R/r marker (25.R2500 -> 25 R 2500).
    - Converts dots between two two-digit numbers (12.14.27) into a
      comma-separated list (12, 14, 27). A dot before a longer number
      (e.g. 25.500) is left alone so Direct Bet can read it as 25 @ 500.
    - When a dot-list ends in a longer amount (12.14.27.1500), the last
      dot becomes the amount separator: 12, 14, 27 1500.
    - Normalises Myanmar separators (၊ နှင့် ။) to commas.
    """
    line = line.replace('၊', ',').replace('။', ',').replace('ဒဲ့', ' ').strip()
    line = re.sub(r'\.{2,}', '.', line)
    line = re.sub(r'^\.+', '', line)
    line = re.sub(r'\.+$', '', line)
    line = re.sub(r'\s\.', ' ', line)
    line = re.sub(r'\.\s', ' ', line)
    line = re.sub(r'\.([rRအာ])', r' \1 ', line)
    line = re.sub(r'([rRအာ])\.', r'\1 ', line)
    line = re.sub(
        r'(\d{2}(?:\.\d{2})+)\.(\d{3,})',
        lambda m: ', '.join(re.findall(r'\d{2}', m.group(1))) + ' ' + m.group(2),
        line,
    )
    line = re.sub(
        r'(\d{2}(?:\.\d{2})+)(?!\d)',
        lambda m: ', '.join(re.findall(r'\d{2}', m.group(0))),
        line,
    )
    line = re.sub(r',{2,}', ',', line)
    return line.strip()


def clean_text(raw_text):
    """Clean pasted Viber text (line by line) into a parser-friendly format."""
    return '\n'.join(clean_line(l) for l in raw_text.split('\n'))


def gen_htek(d):
    """ထိပ် (Hteik) / Head - e.g. 5 -> 50,51,...,59"""
    return [f'{d}{i}' for i in range(10)]


def gen_nauk(d):
    """နောက် (Nauk) / Tail - e.g. 5 -> 05,15,...,95"""
    return [f'{i}{d}' for i in range(10)]


def gen_brake(d):
    """ဘရိတ် (Brake) - sum of digits % 10 equals d"""
    d = int(d)
    return [f'{i}{j}' for i in range(10) for j in range(10) if (i + j) % 10 == d]


def gen_puu():
    """ပူး (Puu) - doubles 00,11,...,99"""
    return [f'{i}{i}' for i in range(10)]


def gen_power():
    """Power - fixed pairs"""
    return ['05', '50', '16', '61', '27', '72', '38', '83', '49', '94']


def gen_natkhat():
    """နက္ခတ် (Natkhat) - fixed pairs"""
    return ['07', '70', '18', '81', '24', '42', '35', '53', '69', '96']


def gen_nyiko():
    """ညီကို (Nyi Ko) - consecutive pairs both directions"""
    res = []
    for i in range(9):
        res.append(f'{i}{i + 1}')
        res.append(f'{i + 1}{i}')
    res.append('09')
    res.append('90')
    return res


def gen_r(s):
    """R (Reverse) - reverse each 2-digit number in a list.

    Handles a single number ("02 R 1500" -> 02, 20), a double number
    ("22 R 1500" -> 22 only, since reversing 22 yields the same number),
    and a series of numbers ("12.14 R 500" -> 12, 21, 14, 41).
    Duplicate numbers are kept, so "89, 26, 26, 56 r 100" counts 8 bets
    (each number plus its reverse, including the repeated 26).
    """
    result = []
    for part in re.split(r'[,\s]+', s):
        if not part:
            continue
        if len(part) == 2 and part[0] != part[1]:
            result.append(part)
            result.append(part[1] + part[0])
        else:
            result.append(part)
    return result


def gen_hkway(chars_str, include_puu):
    """ခွေ (Hkway) - combinations of unique digits, optional doubles"""
    chars = list(dict.fromkeys(chars_str))
    res = []
    for i in range(len(chars)):
        for j in range(len(chars)):
            if i == j:
                if include_puu:
                    res.append(chars[i] + chars[i])
            else:
                res.append(chars[i] + chars[j])
    return res


def gen_kaut(s1, s2, is_reverse):
    """ကပ် (Kaut) - pair every digit of the two numbers.

    For each digit a in s1 and b in s2 the number "ab" is produced, and
    when is_reverse the reverse "ba" is also added -- so a bet of the form
    "A ကို B ကပ် r" counts 2 x len(A) x len(B) boxes (e.g.
    "123456 ကို 23 ကပ် r 100" = 24, "12345 ကို 12345 ကပ် r 100" = 50).
    Duplicates are kept (a doubled digit like 22 contributes 2 entries:
    22 and 22), matching the expected box count.
    """
    s1 = re.sub(r'[^\d]', '', s1)
    s2 = re.sub(r'[^\d]', '', s2)
    res = []
    for c1 in s1:
        for c2 in s2:
            res.append(c1 + c2)
            if is_reverse:
                res.append(c2 + c1)
    return res


def _dedupe(items):
    return list(dict.fromkeys(items))


# Order is crucial: more specific patterns must come first.
PATTERNS = [
    {
        # Kaut: e.g. 2470 ကို 18 နဲ့ ကပ် r 1000 / 7980 ကို 12 r 1000
        'name': 'Kaut',
        'regex': re.compile(
            r'^(\d+)\s*(?:ကို|ko)\s*(\d+)\s*(?:နဲ့\s*ကပ်|နဲ့ကပ်|ကပ်|kap)?\s*(r|အာ)?\s*(\d+)$'
        ),
        'process': lambda m: gen_kaut(m.group(1), m.group(2), bool(m.group(3))),
    },
    {
        # Hkway Puu: e.g. 02468 kp 500
        'name': 'Hkway Puu',
        'regex': re.compile(r'^(\d{3,})\s*(kp|ခွေပူး)\s*(\d+)$'),
        'process': lambda m: gen_hkway(m.group(1), True),
    },
    {
        # Hkway: e.g. 02468 k 500
        'name': 'Hkway',
        'regex': re.compile(r'^(\d{3,})\s*(k|ခွေ|kway)\s*(\d+)$'),
        'process': lambda m: gen_hkway(m.group(1), False),
    },
    {
        # R (Reverse): e.g. 25 r 500, 02 R 1500, 25R500, 25.r.500,
        # or a series like "12.14 r 500" (each number is reversed)
        'name': 'R (Reverse)',
        'regex': re.compile(r'^(\d{2}(?:[,\s]+\d{2})*)[\.\s]*[rRအာ][\.\s]*(\d+)$'),
        'process': lambda m: gen_r(m.group(1)),
    },
    {
        # Patshee: e.g. 5 p 500, or 26 ပါတ် 1000 (head of 2 + tail of 6)
        'name': 'Patshee',
        'regex': re.compile(r'^(\d{1,2})\s*(ပတ်သီး|ပါတ်|ပတ်|အပါ|ပါ|p)\s*(\d+)$'),
        'process': lambda m: _dedupe(gen_htek(m.group(1)[0]) + gen_nauk(m.group(1)[-1])),
    },
    {
        # Hteik: e.g. 5 t 500, or 26 ထိပ် 500 (head digit of 26 -> 20-29)
        'name': 'Hteik',
        'regex': re.compile(r'^(\d{1,2})\s*(ထိပ်|t)\s*(\d+)$'),
        'process': lambda m: gen_htek(m.group(1)[0]),
    },
    {
        # Nauk: e.g. 5 n 500, or 26 နောက် 500 (tail digit of 26 -> 06,16,...,96)
        'name': 'Nauk',
        'regex': re.compile(r'^(\d{1,2})\s*(နောက်|နောက်ပိတ်|န|n)\s*(\d+)$'),
        'process': lambda m: gen_nauk(m.group(1)[-1]),
    },
    {
        # Brake: e.g. 5 b 500, or 26 ဘရိတ် 500 (sum of digits 2+6=8)
        'name': 'Brake',
        'regex': re.compile(r'^(\d{1,2})\s*(ဘရိတ်|bk|b)\s*(\d+)$'),
        'process': lambda m: gen_brake(str((int(m.group(1)[0]) + int(m.group(1)[-1])) % 10)),
    },
    {
        # Puu: e.g. ပူး 500
        'name': 'Puu',
        'regex': re.compile(r'^(အပူး|ပူး|pu)\s*(\d+)$'),
        'process': lambda m: gen_puu(),
    },
    {
        # Power: e.g. power 500
        'name': 'Power',
        'regex': re.compile(r'^(power|ပါဝါ|pw)\s*(\d+)$'),
        'process': lambda m: gen_power(),
    },
    {
        # Natkhat: e.g. nk 500
        'name': 'Natkhat',
        'regex': re.compile(r'^(နက္ခတ်|nk)\s*(\d+)$'),
        'process': lambda m: gen_natkhat(),
    },
    {
        # Nyi Ko: e.g. ညီကို 500
        'name': 'Nyi Ko',
        'regex': re.compile(r'^(ညီကို|ညီအကို|ညီအစ်ကို)\s*(\d+)$'),
        'process': lambda m: gen_nyiko(),
    },
    {
        # Multiple direct bets: e.g. "12, 14, 27 500". Dot-separated lists
        # like "12.14.27 500" are converted to this form by clean_line().
        'name': 'Multiple Direct Bets',
        'regex': re.compile(r'^(\d{2}(?:[,\s]+\d{2})+)\s+(\d+)$'),
        'process': lambda m: [t for t in re.split(r'[,]|\s+', m.group(1)) if t],
    },
    {
        # Direct: e.g. 25 500 or 25-500 or 25.500
        'name': 'Direct Bet',
        'regex': re.compile(r'^(\d{2})\s*(?:-|=|:|\.)?\s*(\d+)$'),
        'process': lambda m: [m.group(1)],
    },
]


def _try_match(original, line, parsed):
    """Try to parse a single line. Returns True if it matched (mutates parsed)."""
    line = line.strip().lower()
    if not line:
        return True
    line = to_eng_digits(line)
    for pattern in PATTERNS:
        m = pattern['regex'].match(line)
        if not m:
            continue
        try:
            amount = int(m.group(len(m.groups())))
        except (ValueError, IndexError):
            return False
        if amount <= 0:
            return False
        numbers = pattern['process'](m)
        parsed.append({
            'formula': pattern['name'],
            'original': original,
            'count': len(numbers),
            'amount': amount,
            'numbers': numbers,
        })
        return True
    return False


def _num_list(line):
    """Return the tokens of a line if every token is a 2-digit number, else []."""
    tokens = [t for t in re.split(r'[,]|\s+', to_eng_digits(line.strip())) if t]
    if tokens and all(re.fullmatch(r'\d{2}', t) for t in tokens):
        return tokens
    return []


def _is_amount_line(line):
    return bool(re.fullmatch(r'\d+', to_eng_digits(line.strip())))


def parse_text(raw_text):
    """Parse Viber text into (parsed_results, errors).

    parsed_results: list of dicts with formula, original, count, amount, numbers
    errors: list of unparseable original lines
    """
    parsed = []
    errors = []
    raw_lines = [l for l in raw_text.split('\n') if l.strip()]
    i, n = 0, len(raw_lines)

    while i < n:
        raw_line = raw_lines[i]
        stripped = raw_line.strip()
        cleaned = clean_line(raw_line)
        if not cleaned:
            errors.append(stripped)
            i += 1
            continue

        # "12.14.27" or "15, 14, 57, 54" on its own line followed by a lone
        # amount line (common Viber style): bet every number in the list.
        nums = _num_list(cleaned)
        if nums and i + 1 < n and _is_amount_line(raw_lines[i + 1]):
            parsed.append({
                'formula': 'Multiple Direct Bets',
                'original': stripped,
                'count': len(nums),
                'amount': int(to_eng_digits(raw_lines[i + 1].strip())),
                'numbers': nums,
            })
            i += 2
            continue

        if _try_match(stripped, cleaned, parsed):
            i += 1
            continue

        # A line may hold several comma-separated bets (e.g. "12 500, 34 200").
        segments = [s.strip() for s in cleaned.split(',') if s.strip()]
        if len(segments) > 1:
            for seg in segments:
                if not _try_match(seg, seg, parsed):
                    errors.append(seg)
        else:
            errors.append(stripped)
        i += 1

    return parsed, errors
