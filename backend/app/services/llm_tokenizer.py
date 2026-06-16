from __future__ import annotations
import json
import string
from dataclasses import dataclass
from pathlib import Path

SPECIAL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>"]

DEFAULT_ALPHABET = (
    string.ascii_letters
    + string.digits
    + string.punctuation
    + " \n\t"
    + "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ"
    + "€'«»—–…"
)


@dataclass
class CharTokenizer:
    stoi: dict[str, int]
    itos: dict[int, str]

    @classmethod
    def build_default(cls) -> "CharTokenizer":
        chars = []
        for ch in DEFAULT_ALPHABET:
            if ch not in chars:
                chars.append(ch)
        vocab = SPECIAL_TOKENS + chars
        stoi = {token: index for index, token in enumerate(vocab)}
        itos = {index: token for token, index in stoi.items()}
        return cls(stoi=stoi, itos=itos)

    @property
    def pad_id(self) -> int:
        return self.stoi["<pad>"]

    @property
    def bos_id(self) -> int:
        return self.stoi["<bos>"]

    @property
    def eos_id(self) -> int:
        return self.stoi["<eos>"]

    @property
    def unk_id(self) -> int:
        return self.stoi["<unk>"]

    @property
    def vocab_size(self) -> int:
        return len(self.stoi)

    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> list[int]:
        ids: list[int] = []
        if add_bos:
            ids.append(self.bos_id)
        ids.extend(self.stoi.get(ch, self.unk_id) for ch in text)
        if add_eos:
            ids.append(self.eos_id)
        return ids

    def decode(self, ids: list[int] | tuple[int, ...]) -> str:
        chars: list[str] = []
        for token_id in ids:
            token = self.itos.get(int(token_id), "<unk>")
            if token in SPECIAL_TOKENS:
                continue
            chars.append(token)
        return "".join(chars)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"stoi": self.stoi}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "CharTokenizer":
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        stoi = {str(k): int(v) for k, v in payload["stoi"].items()}
        itos = {index: token for token, index in stoi.items()}
        return cls(stoi=stoi, itos=itos)
