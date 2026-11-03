"""Scope-aware scan of a Lua file: which globals it uses, calls and defines.

Shared with forever-lint (same author, MIT). The scanner tracks Lua scopes so a
local named like a Blizzard function is not mistaken for it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .lexer import KEYWORD, NAME, NUMBER, OP, STRING, Token, tokenize

VALUE_END_KW = {"end", "nil", "true", "false", "..."}
STATEMENT_KW = {"local", "if", "for", "while", "repeat", "return", "do", "end", "break", "goto", "else", "elseif", "until", "function"}
GUARD_BEFORE_KW = {"if", "elseif", "while", "and", "or", "not", "until"}
GUARD_AFTER = {"and", "or", "then", "do"}


@dataclass(slots=True)
class _Ref:
    name: str  # full dotted name as checked (e.g. "C_Spell.GetSpellInfo" or "GetSpellInfo")
    tok: Token
    index: int  # token index of the first part
    end: int  # token index after the chain
    is_call: bool
    guarded: bool


@dataclass(slots=True)
class FileScan:
    path: str
    refs: list[_Ref]
    defines: set[str]  # globals the file assigns (polyfills / its own API)
    guarded_names: set[str]
    tokens: list[Token]


class _Scope:
    __slots__ = ("names", "parent")

    def __init__(self, parent: _Scope | None):
        self.names: set[str] = set()
        self.parent = parent

    def has(self, name: str) -> bool:
        s: _Scope | None = self
        while s is not None:
            if name in s.names:
                return True
            s = s.parent
        return False


def _is_value_end(t: Token) -> bool:
    return t.kind in (NAME, NUMBER, STRING) or t.is_op(")", "]", "}") or (t.kind == KEYWORD and t.value in VALUE_END_KW)


def scan(path: str, source: str) -> FileScan:
    toks = tokenize(source)
    n = len(toks)
    refs: list[_Ref] = []
    defines: set[str] = set()
    guarded: set[str] = set()
    reassigned: set[str] = set()  # locals assigned again later (e.g. a guarded replacement)

    root = _Scope(None)
    scope = root
    # Block stack entries: the scope object pushed for that block.
    blocks: list[_Scope] = []
    pending_loop: list[str] = []
    # (names, scope, block depth) declared by "local a, b = ..." and waiting for the statement to end
    pending_locals: list[tuple[list[str], _Scope, int]] = []
    brackets: list[str] = []  # "(", "[", "{"

    def push(names: Iterable[str] = ()) -> None:
        nonlocal scope
        scope = _Scope(scope)
        scope.names.update(names)
        blocks.append(scope)

    def pop() -> None:
        nonlocal scope
        if blocks:
            blocks.pop()
            scope = blocks[-1] if blocks else root

    def flush_locals(force: bool = False) -> None:
        keep = []
        for names, sc, depth in pending_locals:
            if force or depth == len(blocks):
                sc.names.update(names)
            else:
                keep.append((names, sc, depth))
        pending_locals[:] = keep

    i = 0
    while i < n:
        t = toks[i]
        prev = toks[i - 1] if i else None

        # A statement boundary activates "local x = ..." declarations made at this block depth.
        if pending_locals and not brackets and prev is not None:
            if (
                t.is_op(";")
                or (t.kind == KEYWORD and t.value in STATEMENT_KW and t.value != "function")
                or (t.kind == NAME and t.line > prev.line and _is_value_end(prev))
            ):
                flush_locals()

        if t.kind == OP:
            if t.value in "([{":
                brackets.append(t.value)
            elif t.value in ")]}":
                if brackets:
                    brackets.pop()
            i += 1
            continue

        if t.kind == KEYWORD:
            v = t.value
            if v == "local":
                nxt = toks[i + 1] if i + 1 < n else None
                if nxt is not None and nxt.is_kw("function"):
                    if i + 2 < n and toks[i + 2].kind == NAME:
                        scope.names.add(toks[i + 2].value)
                    i += 1  # handled as "function" on the next iteration (name is local now)
                    continue
                names, j = [], i + 1
                while j < n and toks[j].kind == NAME:
                    names.append(toks[j].value)
                    j += 1
                    if j < n and toks[j].is_op("<"):  # Lua 5.4 attribs, harmless
                        j += 3
                    if j < n and toks[j].is_op(","):
                        j += 1
                        continue
                    break
                if j < n and toks[j].is_op("="):
                    pending_locals.append((names, scope, len(blocks)))
                else:
                    scope.names.update(names)
                i = j
                continue
            if v == "function":
                j = i + 1
                method = False
                if j < n and toks[j].kind == NAME:  # function a.b:c(
                    chain = [toks[j].value]
                    first = toks[j]
                    j += 1
                    while j + 1 < n and toks[j].is_op(".", ":") and toks[j + 1].kind == NAME:
                        method = method or toks[j].value == ":"
                        chain.append(toks[j + 1].value)
                        j += 2
                    if len(chain) == 1:
                        if not scope.has(chain[0]):
                            defines.add(chain[0])
                    elif not scope.has(chain[0]):
                        if not method:
                            defines.add(".".join(chain[:2]))
                        # using the table is a reference to it (function SomeGlobal.Foo() needs SomeGlobal)
                        refs.append(_Ref(chain[0], first, i + 1, i + 2, False, True))
                params: list[str] = ["self"] if method else []
                if j < n and toks[j].is_op("("):
                    j += 1
                    while j < n and not toks[j].is_op(")"):
                        if toks[j].kind == NAME:
                            params.append(toks[j].value)
                        j += 1
                    j += 1
                push(params)
                i = j
                continue
            if v == "for":
                j = i + 1
                pending_loop = []
                while j < n and not (toks[j].is_op("=") or toks[j].is_kw("in")):
                    if toks[j].kind == NAME:
                        pending_loop.append(toks[j].value)
                    j += 1
                i = j
                continue
            if v == "do":
                push(pending_loop)
                pending_loop = []
            elif v in ("then", "repeat"):
                push()
            elif v == "elseif":
                pop()
            elif v == "else":
                pop()
                push()
            elif v in ("end", "until"):
                flush_locals()
                pop()
            elif v == "goto":
                i += 2
                continue
            i += 1
            continue

        if t.kind != NAME:
            i += 1
            continue

        # ---- a name
        if prev is not None and (prev.is_op(".", ":", "::") or prev.is_kw("goto")):
            i += 1
            continue
        nxt = toks[i + 1] if i + 1 < n else None
        # table constructor key: { Name = value }
        if brackets and brackets[-1] == "{" and nxt is not None and nxt.is_op("=") and prev is not None and prev.is_op("{", ",", ";"):
            i += 1
            continue
        if scope.has(t.value):
            if nxt is not None and nxt.is_op("=") and not brackets:
                reassigned.add(t.value)
            i += 1
            continue

        # Global reference. Build "Base.Member" for namespace tables.
        j = i + 1
        full = t.value
        if j + 1 < n and toks[j].is_op(".") and toks[j + 1].kind == NAME:
            full = f"{t.value}.{toks[j + 1].value}"
            j += 2
            while j + 1 < n and toks[j].is_op(".") and toks[j + 1].kind == NAME:
                j += 2
        after = toks[j] if j < n else None
        is_call = after is not None and (after.is_op("(") or after.kind == STRING or after.is_op("{"))
        if after is not None and after.is_op(":"):
            is_call = True

        # Assignment targets define the global (polyfill).
        assigned = after is not None and after.is_op("=") and not brackets
        multi_assign = after is not None and after.is_op(",") and not brackets and _looks_like_assignment(toks, j)
        if assigned or multi_assign:
            defines.add(full)
            if full != t.value:
                defines.add(full)
            i = j
            continue

        is_guard = (
            prev is not None
            and (
                (prev.kind == KEYWORD and prev.value in GUARD_BEFORE_KW)
                or (prev.is_op("(") and i >= 2 and toks[i - 2].kind == NAME and toks[i - 2].value in ("type", "issecurevariable", "rawget"))
            )
            and not is_call
        ) or (after is not None and ((after.kind == KEYWORD and after.value in GUARD_AFTER) or after.is_op("==", "~=")) and not is_call)
        if is_guard:
            guarded.add(full)
            guarded.add(t.value)
        refs.append(_Ref(full, t, i, j, is_call, is_guard))
        i = j if full != t.value else i + 1

    flush_locals(force=True)
    # "local X = X" followed by "X = replacement" later: the cached global is only a fallback.
    for r in refs:
        k = r.index
        if r.name in reassigned and k >= 3 and toks[k - 1].is_op("=") and toks[k - 2].value == r.name and toks[k - 3].is_kw("local"):
            r.guarded = True
    # No inline "ignore" comments here on purpose: the code being scanned must not be able to silence the scanner.
    return FileScan(path, refs, defines, guarded, toks)


def _looks_like_assignment(toks: list[Token], j: int) -> bool:
    """``a, b = ...`` at statement level: names and commas up to an ``=``."""
    k = j
    while k + 1 < len(toks) and toks[k].is_op(","):
        if toks[k + 1].kind != NAME:
            return False
        k += 2
        while k + 1 < len(toks) and toks[k].is_op(".") and toks[k + 1].kind == NAME:
            k += 2
    return k < len(toks) and toks[k].is_op("=")
