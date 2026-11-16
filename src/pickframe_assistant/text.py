"""Tokenisation, language detection and the small amount of language knowledge the assistant needs.

The pipeline for one piece of text is: normalise, split into words and numbers, expand chat
slang, drop stop words, map domain words to shared concepts, then stem what is left.
Concepts carry an "@" prefix (for example "@price" for harga, biaya, price and cost), which keeps
them apart from ordinary tokens and lets Indonesian and English text meet on the same terms.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Final

from pickframe_assistant.model import Language

_WORD: Final = re.compile(r"[a-z]+|\d+(?:[.,]\d+)*")
_GROUPED_NUMBER: Final = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")

SLANG: Final[dict[str, str]] = {
    "brp": "berapa",
    "gmn": "bagaimana",
    "gimana": "bagaimana",
    "yg": "yang",
    "utk": "untuk",
    "gak": "tidak",
    "ga": "tidak",
    "nggak": "tidak",
    "ngga": "tidak",
    "tdk": "tidak",
    "dgn": "dengan",
    "sy": "saya",
    "aku": "saya",
    "gw": "saya",
    "gue": "saya",
    "bln": "bulan",
    "thn": "tahun",
    "krn": "karena",
    "udh": "sudah",
    "sdh": "sudah",
    "blm": "belum",
    "jg": "juga",
    "klo": "kalau",
    "kalo": "kalau",
    "pake": "pakai",
    "tlg": "tolong",
    "dpt": "dapat",
    "bs": "bisa",
    "msh": "masih",
    "pls": "please",
    "plz": "please",
}

_STOPWORDS_ID: Final = frozenset(
    [
        "yang",
        "dan",
        "di",
        "ke",
        "dari",
        "untuk",
        "dengan",
        "atau",
        "ini",
        "itu",
        "apa",
        "apakah",
        "adalah",
        "ada",
        "akan",
        "bisa",
        "dapat",
        "saya",
        "kami",
        "kita",
        "anda",
        "kamu",
        "dong",
        "sih",
        "deh",
        "ya",
        "nih",
        "tolong",
        "mohon",
        "kah",
        "lah",
        "pun",
        "juga",
        "pada",
        "dalam",
        "oleh",
        "sebagai",
        "karena",
        "agar",
        "supaya",
        "jika",
        "kalau",
        "bila",
        "kapan",
        "bagaimana",
        "berapa",
        "mengapa",
        "kenapa",
        "siapa",
        "mana",
        "tidak",
        "belum",
        "sudah",
        "masih",
        "sedang",
        "lagi",
        "saja",
        "hanya",
        "seperti",
        "bagi",
        "para",
        "suatu",
        "nya",
        "kok",
        "kan",
        "lho",
        "tiap",
        "pakai",
        "memakai",
        "menggunakan",
        "mau",
        "ingin",
        "perlu",
        "butuh",
        "sekarang",
        "pickframe",
        "punya",
        "tentang",
        "soal",
        "mengenai",
        "rp",
        "rupiah",
        "cara",
    ]
)
_STOPWORDS_EN: Final = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "do",
        "does",
        "did",
        "can",
        "could",
        "will",
        "would",
        "should",
        "i",
        "my",
        "me",
        "we",
        "our",
        "you",
        "your",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "what",
        "which",
        "who",
        "how",
        "when",
        "where",
        "why",
        "much",
        "many",
        "there",
        "any",
        "at",
        "by",
        "from",
        "as",
        "if",
        "so",
        "than",
        "then",
        "about",
        "please",
        "just",
        "get",
        "also",
        "have",
        "has",
        "had",
        "not",
        "am",
        "im",
        "ive",
        "dont",
        "doesnt",
        "cant",
        "whats",
        "thats",
        "hows",
        "use",
        "used",
        "using",
        "want",
        "need",
        "make",
        "now",
        "today",
        "pickframe",
        "really",
        "actually",
        "exactly",
        "anything",
        "something",
        "rp",
        "tell",
        "gets",
        "give",
        "gives",
        "given",
        "happen",
        "happens",
        "go",
        "goes",
        "up",
        "down",
        "after",
        "before",
    ]
)

_CONCEPT_GROUPS: Final[dict[str, str]] = {
    "price": "harga berharga biaya tarif ongkos price prices pricing cost costs fee fees rate",
    "subscribe": (
        "berlangganan langganan subscribe subscribing subscription subscriptions beli membeli "
        "buy purchase purchasing"
    ),
    "refund": "refund refunds refunded refunding pengembalian",
    "gallery": "galeri gallery galleries",
    "invoice": "invoice invoices tagihan faktur",
    "receipt": "kuitansi receipt receipts nota",
    "project": "proyek project projects projek",
    "plan": "paket plan plans tier package packages",
    "month": "bulan bulanan month months monthly",
    "year": "tahun tahunan year years yearly annual annually",
    "week": "minggu mingguan week weeks weekly",
    "free": "gratis free",
    "trial": "trial percobaan",
    "quota": "kuota quota quotas jatah allowance allowances limit limits batas batasan",
    "photo": "foto photo photos picture pictures",
    "client": "klien client clients pelanggan customer customers",
    "code": "kode code codes",
    "redeem": "tebus menebus ditebus redeem redeems redeeming redemption",
    "renew": (
        "perpanjang memperpanjang diperpanjang diperpanjangkan perpanjangan renew renews renewal renewing renewed extend "
        "extending"
    ),
    "expire": "habis berakhir kedaluwarsa kadaluarsa expire expires expired expiry expiring",
    "delete": "hapus menghapus dihapus delete deletes deleted deleting deletion",
    "guarantee": "garansi guarantee jaminan warranty",
    "document": "dokumen document documents docs",
    "download": "unduh mengunduh unduhan download downloads downloading",
    "export": "ekspor mengekspor export exports exporting",
    "link": "tautan link links url",
    "account": "akun account accounts",
    "payment": "pembayaran bayar membayar dibayar payment payments pay paying paid",
    "cancel": "batal membatalkan batalkan cancel cancelling canceling cancellation unsubscribe",
    "automatic": "otomatis automatic automatically auto",
    "reset": "reset direset resets mereset",
    "brand": "merek brand watermark logo atribusi attribution",
    "return": "kembali mengembalikan dikembalikan kembalikan return returns returned back",
    "user": "pengguna user users orang people person",
    "share": "bagikan membagikan dibagikan berbagi share shares sharing shared",
    "own": "milik pemilik memiliki dimiliki kepemilikan own owns owner owned ownership",
    "duration": "durasi duration berlangsung last lasts lasted lasting",
    "difference": (
        "perbedaan beda bedanya berbeda difference differences differ differs different compare "
        "comparison"
    ),
    "card": "kartu card cards",
    "shutdown": "dihentikan dihentikan ditutup tutup discontinued discontinue shutdown",
    "lose": "hangus hilang lose loses lost losing",
    "remain": "sisa tersisa remaining remain remains left",
}

_CONCEPTS: Final[dict[str, str]] = {
    word: f"@{concept}" for concept, words in _CONCEPT_GROUPS.items() for word in words.split()
}

# Words that tell us a question is about PickFrame even when the knowledge base cannot answer it.
DOMAIN_TERMS: Final = frozenset(
    {
        *(_CONCEPTS.values()),
        "pickframe",
        "pro",
        "studio",
        "select",
        "drive",
        "excel",
        "dashboard",
        "workspace",
        "whatsapp",
        "gallery",
    }
)

_ID_MARKERS: Final = frozenset(
    [
        "yang",
        "apa",
        "apakah",
        "bagaimana",
        "berapa",
        "untuk",
        "dengan",
        "saya",
        "bisa",
        "tidak",
        "atau",
        "dan",
        "di",
        "ke",
        "dari",
        "ini",
        "itu",
        "kapan",
        "kenapa",
        "mengapa",
        "ada",
        "paket",
        "harga",
        "tolong",
        "gak",
        "ga",
        "brp",
        "gmn",
        "udh",
        "blm",
        "dong",
        "sih",
    ]
)
_EN_MARKERS: Final = frozenset(
    [
        "the",
        "what",
        "how",
        "much",
        "for",
        "with",
        "can",
        "is",
        "are",
        "do",
        "does",
        "my",
        "or",
        "and",
        "to",
        "of",
        "in",
        "when",
        "why",
        "which",
        "there",
        "any",
        "please",
        "plan",
        "price",
        "does",
        "i",
        "your",
        "you",
        "tell",
        "give",
        "show",
        "who",
        "where",
        "was",
        "were",
        "will",
        "would",
        "could",
        "should",
        "by",
        "from",
        "on",
        "at",
        "about",
        "if",
        "that",
        "these",
        "those",
        "an",
        "a",
    ]
)


def normalise(text: str) -> str:
    """Casefold, unify quote marks and drop apostrophes so that "can't" and "cant" match."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return re.sub("['\u2019`]", "", folded)


def canonical_number(token: str) -> str:
    """69.000 and 69,000 are both 69000; 1,5 is 1.5."""
    if _GROUPED_NUMBER.match(token):
        return re.sub(r"[.,]", "", token)
    return token.replace(",", ".")


def words(text: str) -> list[str]:
    """Lower-cased words and canonical numbers, with chat slang expanded."""
    out: list[str] = []
    for raw in _WORD.findall(normalise(text)):
        if raw[0].isdigit():
            out.append(canonical_number(raw))
        else:
            out.append(SLANG.get(raw, raw))
    return out


def detect_language(text: str) -> Language:
    """Indonesian or English, decided by function words. Ties go to Indonesian, the site default."""
    seen = [w for w in words(text) if not w[0].isdigit()]
    id_score = sum(1 for w in seen if w in _ID_MARKERS)
    en_score = sum(1 for w in seen if w in _EN_MARKERS)
    return "en" if en_score > id_score else "id"


def _stem_en(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    return word


# Two words that mean one thing. They are merged before stop words are dropped.
_PHRASES: Final[dict[tuple[str, str], str]] = {
    ("berapa", "lama"): "@duration",
    ("how", "long"): "@duration",
    ("money", "back"): "@refund",
    ("uang", "kembali"): "@refund",
    ("kartu", "kredit"): "@card",
    ("credit", "card"): "@card",
    ("shut", "down"): "@shutdown",
    ("shuts", "down"): "@shutdown",
    ("shutting", "down"): "@shutdown",
}

_ID_PARTICLES: Final = ("lah", "kah", "pun", "nya")
_ID_SUFFIXES: Final = ("kan", "an", "i")
# (prefix, letter the stem may have lost when the prefix was attached: meng+kembali -> mengembali)
_ID_PREFIXES: Final = (
    ("memper", ""), ("diper", ""), ("meng", "k"), ("meny", "s"), ("peng", "k"), ("peny", "s"),
    ("mem", "p"), ("pem", "p"), ("men", "t"), ("pen", "t"), ("ber", ""), ("ter", ""),
    ("per", ""), ("me", ""), ("di", ""), ("ke", ""), ("pe", ""), ("se", ""),
)  # fmt: skip
_VOWELS: Final = "aeiou"


def _id_candidates(word: str) -> list[str]:
    """Possible stems of an Indonesian word, most reduced first. Only a dictionary can say which
    is real, so these are checked against the words of the knowledge base."""
    bases = [word]
    for particle in _ID_PARTICLES:
        if word.endswith(particle) and len(word) - len(particle) >= 4:
            bases = [word[: -len(particle)]]
            break
    for suffix in _ID_SUFFIXES:
        if bases[0].endswith(suffix) and len(bases[0]) - len(suffix) >= 4:
            bases.insert(0, bases[0][: -len(suffix)])
            break
    out: list[str] = []
    for base in bases:
        for prefix, restored in _ID_PREFIXES:
            if base.startswith(prefix) and len(base) - len(prefix) >= 3:
                rest = base[len(prefix) :]
                out.append(rest)
                if restored and rest[0] in _VOWELS:
                    out.append(restored + rest)
        out.append(base)
    return [c for c in dict.fromkeys(out) if len(c) >= 4]


class Analyzer:
    """Turns text into the terms used for matching: stop words dropped, domain words mapped to
    concepts, then stemmed.

    Indonesian stemming is guided by `vocabulary`, the words that occur in the knowledge base. A
    word is reduced to the first candidate stem that is itself a word of the knowledge base; failing
    that, to the first stem that some knowledge-base word can be reduced to; failing that it is left
    alone. This is how "dikembalikan" and "mengembalikan" both become "kembali".
    """

    def __init__(self, lang: Language, vocabulary: frozenset[str] = frozenset()) -> None:
        self.lang = lang
        self._vocabulary = vocabulary
        self._derivable = frozenset(c for w in vocabulary for c in _id_candidates(w) if c != w)
        self._stopwords = _STOPWORDS_ID if lang == "id" else _STOPWORDS_EN

    def _stem(self, word: str) -> str:
        if self.lang == "en":
            return _stem_en(word)
        candidates = [c for c in _id_candidates(word) if c != word]
        for pool, shortest in ((self._vocabulary | _CONCEPTS.keys(), 4), (self._derivable, 5)):
            for candidate in candidates:
                if len(candidate) >= shortest and candidate in pool:
                    return candidate
        return word

    @staticmethod
    def _merge_phrases(tokens: list[str]) -> list[str]:
        merged: list[str] = []
        skip = False
        for first, second in zip(tokens, [*tokens[1:], ""], strict=False):
            if skip:
                skip = False
            elif (first, second) in _PHRASES:
                merged.append(_PHRASES[(first, second)])
                skip = True
            else:
                merged.append(first)
        return merged

    def __call__(self, text: str) -> list[str]:
        out: list[str] = []
        previous = ""
        for word in self._merge_phrases(words(text)):
            after_number = previous[:1].isdigit()
            previous = word
            if word.startswith("@"):
                out.append(word)
                continue
            if word in self._stopwords or (len(word) == 1 and word.isalpha()):
                continue
            concept = _CONCEPTS.get(word) or _CONCEPTS.get(self._stem(word))
            if concept == "@year" and not after_number:
                # PickFrame sells 1, 3 and 12 months, so "a year" is the 12-month plan.
                out.extend(["12", "@month"])
            elif concept is not None:
                out.append(concept)
            else:
                out.append(self._stem(word))
        return out


def vocabulary(texts: Iterable[str]) -> frozenset[str]:
    """Every word in `texts`, for guiding the Indonesian stemmer."""
    return frozenset(w for text in texts for w in words(text) if not w[0].isdigit())


def tokenize(text: str, lang: Language) -> list[str]:
    """`Analyzer` without a vocabulary: enough to compare two texts consistently."""
    return Analyzer(lang)(text)


def split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation followed by a capital letter or a digit."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
    return [part for part in parts if part]
