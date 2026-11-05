/* addon-sentry engine, JavaScript port of src/addon_sentry (lexer, lua, engine).
 * Runs in the browser and in Node 18+. The zip never leaves the device.
 * Rule data comes from rules.json, generated from rules.py, so both engines share it.
 * tests/test_parity.py runs both engines on the same zips and requires identical reports.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.AddonSentry = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const VERSION = "0.2.0";
  const NAME = "name", NUMBER = "number", STRING = "string", OP = "op", KEYWORD = "keyword", COMMENT = "comment";
  const KEYWORDS = new Set("and break do else elseif end false for function goto if in local nil not or repeat return then true until while".split(" "));
  const OPS = ["...", "..", "==", "~=", "<=", ">=", "<<", ">>", "//", "::", ..."+-*/%^#&~|<>=(){}[];:,.".split("")];

  class ScanError extends Error {}
  // Upper half of code page 437, the default encoding for zip names without the UTF-8 flag (as Python's zipfile)
  const CP437 = "ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒáíóúñÑªº¿⌐¬½¼¡«»░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀αßΓπΣσµτΦΘΩδ∞φε∩≡±≥≤⌠⌡÷≈°∙·√ⁿ²■\u00a0";

  // ------------------------------------------------------------------ lexer

  function tok(kind, value, line, col, pos) {
    return { kind, value, line, col, pos };
  }
  const isOp = (t, ...v) => t && t.kind === OP && v.includes(t.value);
  const isKw = (t, ...v) => t && t.kind === KEYWORD && v.includes(t.value);

  const ESC = { n: "\n", t: "\t", r: "\r", a: "\x07", b: "\b", f: "\f", v: "\v", "\\": "\\", '"': '"', "'": "'", "\n": "\n" };
  function unquote(body) {
    if (body.indexOf("\\") < 0) return body;
    let out = "", i = 0;
    while (i < body.length) {
      const ch = body[i];
      if (ch === "\\" && i + 1 < body.length) {
        const nx = body[i + 1];
        if (Object.prototype.hasOwnProperty.call(ESC, nx)) { out += ESC[nx]; i += 2; continue; }
        if (nx >= "0" && nx <= "9") {
          const m = /^\d{1,3}/.exec(body.slice(i + 1));
          out += String.fromCharCode(parseInt(m[0], 10) % 256);
          i += 1 + m[0].length;
          continue;
        }
      }
      out += ch;
      i += 1;
    }
    return out;
  }

  const NAME_RE = /[A-Za-z_][A-Za-z0-9_]*/y;
  const NUMBER_RE = /0[xX](?:[0-9A-Fa-f]*\.?[0-9A-Fa-f]+|[0-9A-Fa-f]+\.?)(?:[pP][+-]?[0-9]+)?|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?/y;
  const LONG_OPEN_RE = /\[(=*)\[/y;

  function tokenize(source, keepComments) {
    const tokens = [];
    let i = 0;
    const n = source.length;
    let line = 1, lineStart = 0;
    if (source.startsWith("#")) { i = source.indexOf("\n"); if (i < 0) i = n; }

    function emit(kind, start, end, value) {
      const text = source.slice(start, end);
      const startLine = line, col = start - lineStart + 1;
      let nl = 0, last = -1;
      for (let k = 0; k < text.length; k++) if (text.charCodeAt(k) === 10) { nl++; last = k; }
      if (nl) { line += nl; lineStart = start + last + 1; }
      if (kind !== COMMENT || keepComments) tokens.push(tok(kind, value === undefined ? text : value, startLine, col, start));
    }

    while (i < n) {
      const c = source[i];
      if (c === "\n") { line++; i++; lineStart = i; continue; }
      if (c === " " || c === "\t" || c === "\r" || c === "\f" || c === "\v") { i++; continue; }
      if (source.startsWith("--", i)) {
        LONG_OPEN_RE.lastIndex = i + 2;
        const m = LONG_OPEN_RE.exec(source);
        let end;
        if (m) {
          const close = "]" + m[1] + "]";
          end = source.indexOf(close, LONG_OPEN_RE.lastIndex);
          end = end < 0 ? n : end + close.length;
        } else {
          end = source.indexOf("\n", i);
          if (end < 0) end = n;
        }
        emit(COMMENT, i, end);
        i = end;
        continue;
      }
      if (c === '"' || c === "'") {
        let j = i + 1;
        while (j < n) {
          const ch = source[j];
          if (ch === "\\") { j += 2; continue; }
          if (ch === c || ch === "\n") break;
          j++;
        }
        const end = Math.min(j + 1, n);
        emit(STRING, i, end, unquote(source.slice(i + 1, Math.min(j, n))));
        i = end;
        continue;
      }
      if (c === "[") {
        LONG_OPEN_RE.lastIndex = i;
        const m = LONG_OPEN_RE.exec(source);
        if (m) {
          const close = "]" + m[1] + "]";
          let end = source.indexOf(close, LONG_OPEN_RE.lastIndex);
          const bodyEnd = end < 0 ? n : end;
          end = end < 0 ? n : end + close.length;
          let body = source.slice(LONG_OPEN_RE.lastIndex, bodyEnd);
          if (body.startsWith("\r\n")) body = body.slice(2);
          else if (body.startsWith("\n")) body = body.slice(1);
          emit(STRING, i, end, body);
          i = end;
          continue;
        }
      }
      if ((c >= "0" && c <= "9") || (c === "." && i + 1 < n && source[i + 1] >= "0" && source[i + 1] <= "9")) {
        NUMBER_RE.lastIndex = i;
        const m = NUMBER_RE.exec(source);
        if (m && NUMBER_RE.lastIndex > i) { emit(NUMBER, i, NUMBER_RE.lastIndex); i = NUMBER_RE.lastIndex; continue; }
      }
      NAME_RE.lastIndex = i;
      const nm = NAME_RE.exec(source);
      if (nm) {
        emit(KEYWORDS.has(nm[0]) ? KEYWORD : NAME, i, NAME_RE.lastIndex);
        i = NAME_RE.lastIndex;
        continue;
      }
      let matched = false;
      for (const op of OPS) {
        if (source.startsWith(op, i)) { emit(OP, i, i + op.length); i += op.length; matched = true; break; }
      }
      if (!matched) i++;
    }
    return tokens;
  }

  // ------------------------------------------------------------------ scope-aware scan (lua.py)

  const VALUE_END_KW = new Set(["end", "nil", "true", "false", "..."]);
  const STATEMENT_KW = new Set(["local", "if", "for", "while", "repeat", "return", "do", "end", "break", "goto", "else", "elseif", "until", "function"]);
  const GUARD_BEFORE_KW = new Set(["if", "elseif", "while", "and", "or", "not", "until"]);
  const GUARD_AFTER = new Set(["and", "or", "then", "do"]);

  class Scope {
    constructor(parent) { this.names = new Set(); this.parent = parent; this.aliases = new Map(); }
    has(name) { for (let s = this; s; s = s.parent) if (s.names.has(name)) return true; return false; }
    owner(name) { for (let s = this; s; s = s.parent) if (s.names.has(name)) return s; return null; }
  }
  const isValueEnd = (t) => t.kind === NAME || t.kind === NUMBER || t.kind === STRING || isOp(t, ")", "]", "}") || (t.kind === KEYWORD && VALUE_END_KW.has(t.value));

  // "local load = loadstring" / "local A, B = A, B": the globals ("A" or "A.B") the locals stand for, or null
  function aliasOf(toks, k, names, scope) {
    const n = toks.length;
    const out = new Map();
    let e = k;
    for (let idx = 0; idx < names.length; idx++) {
      if (e >= n || toks[e].kind !== NAME || scope.has(toks[e].value)) return null;
      const chain = [toks[e].value];
      e++;
      while (e + 1 < n && isOp(toks[e], ".") && toks[e + 1].kind === NAME) { chain.push(toks[e + 1].value); e += 2; }
      if (chain.length > 2) return null;
      out.set(names[idx], chain.join("."));
      if (idx < names.length - 1) {
        if (e >= n || !isOp(toks[e], ",")) return null;
        e++;
      }
    }
    const end = e >= n || isOp(toks[e], ";") || toks[e].line > toks[e - 1].line || (toks[e].kind === KEYWORD && STATEMENT_KW.has(toks[e].value));
    return end ? out : null;
  }

  function looksLikeAssignment(toks, j) {
    let k = j;
    while (k + 1 < toks.length && isOp(toks[k], ",")) {
      if (toks[k + 1].kind !== NAME) return false;
      k += 2;
      while (k + 1 < toks.length && isOp(toks[k], ".") && toks[k + 1].kind === NAME) k += 2;
    }
    return k < toks.length && isOp(toks[k], "=");
  }

  function scan(path, source) {
    const toks = tokenize(source);
    const n = toks.length;
    const refs = [], defines = new Set(), guarded = new Set(), reassigned = new Set();
    const root = new Scope(null);
    let scope = root;
    const blocks = [];
    let pendingLoop = [];
    let pendingLocals = [];
    const brackets = [];
    const fnBrackets = []; // [block depth of a function body, brackets outside it]
    const push = (names) => { scope = new Scope(scope); for (const x of names || []) scope.names.add(x); blocks.push(scope); };
    const pop = () => { if (blocks.length) { blocks.pop(); scope = blocks.length ? blocks[blocks.length - 1] : root; } };
    const flush = (force) => {
      const keep = [];
      for (const p of pendingLocals) {
        if (force || p[2] === blocks.length) {
          for (const x of p[0]) {
            p[1].names.add(x);
            if (p[3] && p[3].has(x)) p[1].aliases.set(x, p[3].get(x));
            else p[1].aliases.delete(x);
          }
        } else keep.push(p);
      }
      pendingLocals = keep;
    };

    let i = 0;
    while (i < n) {
      const t = toks[i];
      const prev = i ? toks[i - 1] : null;
      if (pendingLocals.length && !brackets.length && prev) {
        if (isOp(t, ";") || (t.kind === KEYWORD && STATEMENT_KW.has(t.value) && t.value !== "function") || (t.kind === NAME && t.line > prev.line && isValueEnd(prev)) || (isKw(t, "function") && t.line > prev.line && isValueEnd(prev))) flush(false);
      }
      if (t.kind === OP) {
        if ("([{".includes(t.value) && t.value.length === 1) brackets.push(t.value);
        else if (")]}".includes(t.value) && t.value.length === 1) { if (brackets.length) brackets.pop(); }
        i++;
        continue;
      }
      if (t.kind === KEYWORD) {
        const v = t.value;
        if (v === "local") {
          const nxt = i + 1 < n ? toks[i + 1] : null;
          if (nxt && isKw(nxt, "function")) {
            if (i + 2 < n && toks[i + 2].kind === NAME) scope.names.add(toks[i + 2].value);
            i++;
            continue;
          }
          const names = [];
          let j = i + 1;
          while (j < n && toks[j].kind === NAME) {
            names.push(toks[j].value);
            j++;
            if (j < n && isOp(toks[j], "<")) j += 3;
            if (j < n && isOp(toks[j], ",")) { j++; continue; }
            break;
          }
          if (j < n && isOp(toks[j], "=")) pendingLocals.push([names, scope, blocks.length, aliasOf(toks, j + 1, names, scope)]);
          else for (const x of names) scope.names.add(x);
          i = j;
          continue;
        }
        if (v === "function") {
          let j = i + 1, method = false;
          if (j < n && toks[j].kind === NAME) {
            const chain = [toks[j].value];
            const first = toks[j];
            j++;
            while (j + 1 < n && isOp(toks[j], ".", ":") && toks[j + 1].kind === NAME) {
              method = method || toks[j].value === ":";
              chain.push(toks[j + 1].value);
              j += 2;
            }
            if (chain.length === 1) { if (!scope.has(chain[0])) defines.add(chain[0]); }
            else if (!scope.has(chain[0])) {
              if (!method) defines.add(chain.slice(0, 2).join("."));
              refs.push({ name: chain[0], tok: first, index: i + 1, end: i + 2, isCall: false, guarded: true });
            }
          }
          const params = method ? ["self"] : [];
          if (j < n && isOp(toks[j], "(")) {
            j++;
            while (j < n && !isOp(toks[j], ")")) { if (toks[j].kind === NAME) params.push(toks[j].value); j++; }
            j++;
          }
          push(params);
          fnBrackets.push([blocks.length, brackets.slice()]);
          brackets.length = 0;
          i = j;
          continue;
        }
        if (v === "for") {
          let j = i + 1;
          pendingLoop = [];
          while (j < n && !(isOp(toks[j], "=") || isKw(toks[j], "in"))) { if (toks[j].kind === NAME) pendingLoop.push(toks[j].value); j++; }
          i = j;
          continue;
        }
        if (v === "do") { push(pendingLoop); pendingLoop = []; }
        else if (v === "then" || v === "repeat") push();
        else if (v === "elseif") pop();
        else if (v === "else") { pop(); push(); }
        else if (v === "end" || v === "until") {
          flush(false);
          if (v === "end" && fnBrackets.length && fnBrackets[fnBrackets.length - 1][0] === blocks.length) {
            const saved = fnBrackets.pop()[1];
            brackets.length = 0;
            brackets.push(...saved);
          }
          pop();
        }
        else if (v === "goto") { i += 2; continue; }
        i++;
        continue;
      }
      if (t.kind !== NAME) { i++; continue; }
      if (prev && (isOp(prev, ".", ":", "::") || isKw(prev, "goto"))) { i++; continue; }
      const nxt = i + 1 < n ? toks[i + 1] : null;
      if (brackets.length && brackets[brackets.length - 1] === "{" && nxt && isOp(nxt, "=") && prev && isOp(prev, "{", ",", ";")) { i++; continue; }
      const owner = scope.owner(t.value);
      if (owner) {
        if (nxt && isOp(nxt, "=") && !brackets.length) {
          reassigned.add(t.value);
          owner.aliases.delete(t.value);
          i++;
          continue;
        }
        const alias = owner.aliases.get(t.value);
        if (alias === undefined) { i++; continue; }
        let j = i + 1;
        let full = alias;
        if (!alias.includes(".") && j + 1 < n && isOp(toks[j], ".") && toks[j + 1].kind === NAME) { full = alias + "." + toks[j + 1].value; j += 2; }
        const after = j < n ? toks[j] : null;
        const isCall = !!after && (isOp(after, "(", "{", ":") || after.kind === STRING);
        refs.push({ name: full, tok: t, index: i, end: j, isCall, guarded: false, alias: true });
        i = j;
        continue;
      }
      let j = i + 1;
      let full = t.value;
      if (j + 1 < n && isOp(toks[j], ".") && toks[j + 1].kind === NAME) {
        full = t.value + "." + toks[j + 1].value;
        j += 2;
        while (j + 1 < n && isOp(toks[j], ".") && toks[j + 1].kind === NAME) j += 2;
      }
      const after = j < n ? toks[j] : null;
      let isCall = !!after && (isOp(after, "(") || after.kind === STRING || isOp(after, "{"));
      if (after && isOp(after, ":")) isCall = true;
      const assigned = !!after && isOp(after, "=") && !brackets.length;
      const multi = !!after && isOp(after, ",") && !brackets.length && looksLikeAssignment(toks, j);
      if (assigned || multi) { defines.add(full); i = j; continue; }
      const isGuard =
        (!!prev &&
          ((prev.kind === KEYWORD && GUARD_BEFORE_KW.has(prev.value)) ||
            (isOp(prev, "(") && i >= 2 && toks[i - 2].kind === NAME && ["type", "issecurevariable", "rawget"].includes(toks[i - 2].value))) &&
          !isCall) ||
        (!!after && ((after.kind === KEYWORD && GUARD_AFTER.has(after.value)) || isOp(after, "==", "~=")) && !isCall);
      if (isGuard) { guarded.add(full); guarded.add(t.value); }
      refs.push({ name: full, tok: t, index: i, end: j, isCall, guarded: isGuard });
      i = full !== t.value ? j : i + 1;
    }
    flush(true);
    for (const r of refs) {
      const k = r.index;
      if (reassigned.has(r.name) && k >= 3 && isOp(toks[k - 1], "=") && toks[k - 2].value === r.name && isKw(toks[k - 3], "local")) r.guarded = true;
    }
    return { path, refs, defines, guarded, tokens: toks };
  }

  // ------------------------------------------------------------------ helpers shared with engine.py

  function normpath(path) {
    if (path === "") return ".";
    const initial = path.startsWith("/") ? (path.startsWith("//") && !path.startsWith("///") ? 2 : 1) : 0;
    const out = [];
    for (const comp of path.split("/")) {
      if (comp === "" || comp === ".") continue;
      if (comp !== ".." || (!initial && !out.length) || (out.length && out[out.length - 1] === "..")) out.push(comp);
      else if (out.length) out.pop();
    }
    const joined = "/".repeat(initial) + out.join("/");
    return joined || ".";
  }
  const dirname = (p) => { const i = p.lastIndexOf("/"); if (i < 0) return ""; const head = p.slice(0, i + 1); return /^\/+$/.test(head) ? head : head.replace(/\/+$/, ""); };
  const basename = (p) => p.slice(p.lastIndexOf("/") + 1);
  const pjoin = (a, b) => (b.startsWith("/") ? b : !a ? b : a.endsWith("/") ? a + b : a + "/" + b);
  function splitext(base) {
    // posixpath.splitext on a basename: leading dots are not an extension
    let i = base.lastIndexOf(".");
    if (i <= 0) return "";
    let k = 0;
    while (k < i && base[k] === ".") k++;
    return k === i ? "" : base.slice(i);
  }
  const reEscape = (s) => s.replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&");
  function pyStrip(s, chars) {
    let a = 0, b = s.length;
    while (a < b && chars.includes(s[a])) a++;
    while (b > a && chars.includes(s[b - 1])) b--;
    return s.slice(a, b);
  }
  const pyWhitespace = " \t\n\r\x0b\x0c\x1c\x1d\x1e\x1f\x85\xa0                　";
  const strip = (s) => pyStrip(s, pyWhitespace);

  function make(rules) {
    const R = rules;
    const API_CAPABILITY = new Map();
    for (const [cap, info] of Object.entries(R.capabilities)) for (const api of info.api) API_CAPABILITY.set(api, cap);
    const HOOK = new Set(R.sensitive_hook_targets);
    const SENSITIVE_NAMES = new Set([...API_CAPABILITY.keys(), ...HOOK]);
    const FRAME_PREFIXES = R.sensitive_frame_prefixes;
    const HIDING_EVENTS = new Set(R.hiding_filter_events);
    const REMOTE_EVENTS = new Set(R.remote_input_events);
    const EXE = new Set(R.executable_extensions), SCRIPT = new Set(R.script_extensions), ARCH = new Set(R.archive_extensions), ADDON = new Set(R.addon_extensions);
    const ORDER = Object.fromEntries(R.severities.map((s, i) => [s, i]));
    const CODE_RUNNERS = new Set(["loadstring", "load", "RunScript"]);
    const REGISTER_METHODS = new Set(["RegisterEvent", "RegisterUnitEvent", "RegisterEventCallback"]);
    const FRIEND_LIST_APIS = new Set(["BNGetNumFriends", "BNGetFriendInfo", "C_BattleNet.GetFriendAccountInfo", "C_FriendList.GetFriendInfoByIndex", "C_FriendList.GetNumFriends"]);
    const URL_RE = /(?:https?:\/\/|www\.)[^\s"'<>|]+|discord(?:app)?\.(?:gg|com\/invite)\/[\w-]+/gi;
    const SCRAMBLED_RE = /^(?:[Il1]{6,}|_0x[0-9a-fA-F]{3,}|[lI][lI1_]{7,}|O0{4,}|[_]{4,}\w*)$/;
    const ESCAPES_RE = /(?:\\(?:\d{1,3}|x[0-9a-fA-F]{2})){24,}/g;
    const XML_SCRIPT_RE = /<\s*(Script|On[A-Z]\w*)\b([^>]*)>([\s\S]*?)<\/\s*\1\s*>/g;
    const XML_FILE_REF_RE = /<\s*(?:Script|Include)\b[^>]*?\bfile\s*=\s*["']([^"']+)["']/gi;
    const TEMPLATE_FUNCS = new Set(["format", "gsub", "rep", "tostring", "concat", "join", "upper", "lower", "sub", "string", "table", "strjoin", "assert"]);
    const MAX_ENTRIES = 20000, MAX_TOTAL = 300 * 1024 * 1024, MAX_FILE = 40 * 1024 * 1024, MAX_RATIO = 200;
    const startsWithAny = (s, prefixes) => prefixes.some((p) => s.startsWith(p));

    // -------------------------------------------------------------- package

    function hitAdder(hits) {
      return (rule, path, detail) => {
        if (!hits.has(rule)) hits.set(rule, { id: rule, evidence: [] });
        hits.get(rule).evidence.push({ file: path, line: 0, detail, snippet: "" });
      };
    }
    function safeMember(name) {
      const raw = name.replace(/\\/g, "/");
      const escapes = raw.startsWith("/") || /^[A-Za-z]:/.test(raw) || raw.split("/").includes("..");
      const norm = pyStrip(raw, "/") ? normpath(raw.replace(/^\/+/, "")) : raw;
      return [norm, escapes];
    }
    function classify(path, hit) {
      const lower = path.toLowerCase();
      const base = basename(lower);
      const ext = splitext(base);
      if (EXE.has(ext)) hit("PKG_EXECUTABLE", path, ext);
      else if (SCRIPT.has(ext)) hit("PKG_SCRIPT", path, ext);
      else if (ARCH.has(ext)) hit("PKG_NESTED_ARCHIVE", path, ext);
      else if (ext && !ADDON.has(ext) && !["license", "readme", "changelog", "copying", "authors"].includes(base)) hit("PKG_UNUSUAL_FILE", path, ext);
    }
    const wanted = (p) => /\.(lua|xml|toc)$/i.test(p);

    async function inflateRaw(bytes) {
      const ds = new DecompressionStream("deflate-raw");
      const stream = new Blob([bytes]).stream().pipeThrough(ds);
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    async function readZip(buffer, name) {
      const data = new Uint8Array(buffer);
      const dv = new DataView(data.buffer, data.byteOffset, data.byteLength);
      // End of central directory: search backwards (comment can be up to 64 KB)
      let eocd = -1;
      for (let p = data.length - 22; p >= Math.max(0, data.length - 22 - 65535); p--) {
        if (dv.getUint32(p, true) === 0x06054b50) { eocd = p; break; }
      }
      if (eocd < 0) throw new ScanError("not a valid zip file: File is not a zip file");
      let count = dv.getUint16(eocd + 10, true);
      let cdOffset = dv.getUint32(eocd + 16, true);
      if (count === 0xffff || cdOffset === 0xffffffff) throw new ScanError("ZIP64 archives are not supported in the browser; use the command line tool");
      if (count > MAX_ENTRIES) throw new ScanError(`too many files in the zip (${count})`);
      const dec = new TextDecoder("utf-8");
      const dec437 = (u8) => Array.from(u8, (b) => (b < 128 ? String.fromCharCode(b) : CP437[b - 128])).join("");
      const infos = [];
      let p = cdOffset;
      for (let k = 0; k < count; k++) {
        if (p + 46 > data.length || dv.getUint32(p, true) !== 0x02014b50) throw new ScanError("not a valid zip file: bad central directory");
        const flags = dv.getUint16(p + 8, true);
        const method = dv.getUint16(p + 10, true);
        const csize = dv.getUint32(p + 20, true);
        const usize = dv.getUint32(p + 24, true);
        const nlen = dv.getUint16(p + 28, true), xlen = dv.getUint16(p + 30, true), clen = dv.getUint16(p + 32, true);
        const extAttr = dv.getUint32(p + 38, true);
        const local = dv.getUint32(p + 42, true);
        const nameBytes = data.subarray(p + 46, p + 46 + nlen);
        const fname = flags & 0x800 ? dec.decode(nameBytes) : dec437(nameBytes);
        infos.push({ filename: fname, flags, method, csize, usize, extAttr, local });
        p += 46 + nlen + xlen + clen;
      }
      const files = new Map();
      const hits = new Map();
      const hit = hitAdder(hits);
      let total = 0;
      for (const info of infos) {
        const [path, escapes] = safeMember(info.filename);
        if (escapes) hit("PKG_PATH_TRAVERSAL", info.filename, "path leaves the folder");
        const mode = info.extAttr >>> 16;
        if ((mode & 0o170000) === 0o120000) { hit("PKG_PATH_TRAVERSAL", info.filename, "symbolic link"); continue; }
        if (info.filename.endsWith("/")) continue;
        classify(path, hit);
        total += info.usize;
        if (total > MAX_TOTAL) throw new ScanError("the zip unpacks to more than 300 MB; refusing to scan it");
        if (info.usize > 10 * 1024 * 1024 && info.csize && info.usize / info.csize > MAX_RATIO) throw new ScanError(`${info.filename} looks like a zip bomb (compression ratio over ${MAX_RATIO})`);
        if (info.flags & 0x1) { hit("PKG_ENCRYPTED", path, "password protected"); continue; }
        if (wanted(path) && info.usize <= MAX_FILE) {
          const lp = info.local;
          if (dv.getUint32(lp, true) !== 0x04034b50) throw new ScanError(`cannot read ${info.filename}: bad local header`);
          const start = lp + 30 + dv.getUint16(lp + 26, true) + dv.getUint16(lp + 28, true);
          const raw = data.subarray(start, start + info.csize);
          let bytes;
          if (info.method === 0) bytes = raw;
          else if (info.method === 8) {
            try { bytes = await inflateRaw(raw); } catch (e) { throw new ScanError(`cannot read ${info.filename}: ${e.message}`); }
          } else throw new ScanError(`cannot read ${info.filename}: compression method ${info.method} is not supported in the browser; use the command line tool`);
          files.set(path, bytes);
        }
      }
      return { name, files, hits: [...hits.values()], entries: infos.filter((x) => !x.filename.endsWith("/")).length, totalBytes: total };
    }

    // A folder picked or dropped in the browser: items are { path, size, read: async () => Uint8Array }.
    // Same checks as read_folder in Python (dot files skipped, executables and odd files flagged), without .pkgmeta.
    async function readFiles(name, items) {
      const files = new Map();
      const hits = new Map();
      const hit = hitAdder(hits);
      let total = 0, count = 0;
      const sorted = [...items].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
      if (sorted.length > MAX_ENTRIES) throw new ScanError(`too many files in the folder (${sorted.length})`);
      for (const it of sorted) {
        const [path, escapes] = safeMember(it.path);
        if (path.split("/").some((part) => part.startsWith("."))) continue;
        count++;
        if (escapes) { hit("PKG_PATH_TRAVERSAL", it.path, "path leaves the folder"); continue; }
        classify(path, hit);
        total += it.size;
        if (total > MAX_TOTAL) throw new ScanError("the folder holds more than 300 MB; refusing to scan it");
        if (wanted(path) && it.size <= MAX_FILE) files.set(path, await it.read());
      }
      return { name, files, hits: [...hits.values()], entries: count, totalBytes: total };
    }

    // -------------------------------------------------------------- units

    const decoder = new TextDecoder("utf-8");
    const decode = (bytes) => decoder.decode(bytes);
    const xmlUnescape = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");

    function buildUnits(files) {
      const units = [];
      const paths = [...files.keys()].sort();
      for (const path of paths) {
        const lower = path.toLowerCase();
        if (lower.endsWith(".lua")) units.push({ path, source: decode(files.get(path)), lineOffset: 0 });
        else if (lower.endsWith(".xml")) {
          const text = decode(files.get(path));
          const nc = text.replace(/<!--[\s\S]*?-->/g, (m) => "\n".repeat((m.match(/\n/g) || []).length));
          let k = 0;
          XML_SCRIPT_RE.lastIndex = 0;
          let m;
          while ((m = XML_SCRIPT_RE.exec(nc))) {
            k++;
            let body = m[3];
            if (!strip(body)) continue;
            body = body.split("<![CDATA[").join("         ").split("]]>").join("   ");
            const bodyStart = m.index + m[0].indexOf(">") + 1;
            const line = (nc.slice(0, bodyStart).match(/\n/g) || []).length + 1;
            units.push({ path: `${path}#${m[1]}${k}`, source: xmlUnescape(body), lineOffset: line - 1 });
          }
        }
      }
      for (const u of units) { u.scan = scan(u.path, u.source); u.lines = u.source.split("\n"); }
      return units;
    }

    function ev(u, t, detail) {
      const line = t.line;
      let text = line > 0 && line <= u.lines.length ? strip(u.lines[line - 1]) : "";
      if (text.length > 160) {
        const start = Math.max(0, t.col - 60);
        text = (start ? "…" : "") + text.slice(start, start + 150) + "…";
      }
      return { file: u.path.split("#")[0], line: line + u.lineOffset, detail, snippet: text };
    }

    // -------------------------------------------------------------- facts

    function newFacts() {
      const caps = new Map();
      return {
        caps, hits: new Map(), remoteInput: new Set(), dynamicCode: new Map(), templateCode: new Map(), obfuscated: new Set(),
        hiding: new Map(), moneyUnits: new Set(), overrides: [], urls: new Map(), ownDialogs: new Set(),
        cap(c) { if (!caps.has(c)) caps.set(c, []); return caps.get(c); },
        list(map, k) { if (!map.has(k)) map.set(k, []); return map.get(k); },
        hit(rule, e) {
          if (!this.hits.has(rule)) this.hits.set(rule, { id: rule, evidence: [] });
          const h = this.hits.get(rule);
          if (h.evidence.length < 50 && !h.evidence.some((x) => x.file === e.file && x.line === e.line && x.detail === e.detail)) h.evidence.push(e);
        },
      };
    }

    function closing(toks, open) {
      let depth = 0;
      for (let k = open; k < toks.length; k++) {
        if (isOp(toks[k], "(", "[", "{")) depth++;
        else if (isOp(toks[k], ")", "]", "}")) { depth--; if (depth === 0) return k; }
      }
      return toks.length - 1;
    }
    function literalString(ts) {
      if (ts.length && ts.every((t) => t.kind === STRING || isOp(t, "..")) && ts[0].kind === STRING) return ts.filter((t) => t.kind === STRING).map((t) => t.value).join("");
      return null;
    }
    function dotted(toks, k) {
      const parts = [toks[k].value];
      let j = k + 1;
      while (j + 1 < toks.length && isOp(toks[j], ".") && toks[j + 1].kind === NAME) { parts.push(toks[j + 1].value); j += 2; }
      return [parts.slice(0, 2).join("."), j];
    }
    function isLocal(s, name) {
      const base = name.split(".")[0];
      return !s.refs.some((r) => r.name === name || r.name.split(".")[0] === base) && !s.defines.has(name);
    }
    function polyfill(toks, eq, name) {
      const [rhs, j] = eq + 1 < toks.length && toks[eq + 1].kind === NAME ? dotted(toks, eq + 1) : ["", eq + 1];
      return rhs === name && j < toks.length && isKw(toks[j], "or");
    }
    function assignedFromLiteral(toks, name) {
      let seen = false;
      for (let k = 0; k < toks.length - 2; k++) {
        if (toks[k].kind === NAME && toks[k].value === name && isOp(toks[k + 1], "=") && (k === 0 || !isOp(toks[k - 1], ".", ":"))) {
          seen = true;
          const rhs = toks[k + 2];
          if (rhs.kind === STRING) continue;
          if (rhs.kind === NAME && rhs.value === name && k + 3 < toks.length && isOp(toks[k + 3], ":", "..")) continue;
          if (isOp(rhs, "(") && k + 3 < toks.length && toks[k + 3].kind === STRING) continue;
          if (rhs.kind === NAME && (rhs.value === "format" || rhs.value === "string")) continue;
          return false;
        }
      }
      return seen;
    }
    function templateArgument(toks, open) {
      if (open >= toks.length) return false;
      if (toks[open].kind === STRING) return true;
      if (!isOp(toks[open], "(")) return false;
      const close = closing(toks, open);
      let depth = 0;
      const first = [];
      for (const t of toks.slice(open + 1, close)) {
        if (isOp(t, "(", "[", "{")) depth++;
        else if (isOp(t, ")", "]", "}")) depth--;
        else if (depth === 0 && isOp(t, ",")) break;
        first.push(t);
      }
      if (!first.length) return false;
      if (first[0].kind === STRING) return true;
      let afterColon = false;
      for (const t of first) {
        if (t.kind === STRING || t.kind === NUMBER || t.kind === OP) { afterColon = isOp(t, ":", "."); continue; }
        if (t.kind === NAME) {
          if (afterColon || TEMPLATE_FUNCS.has(t.value)) { afterColon = false; continue; }
          if (!assignedFromLiteral(toks, t.value)) return false;
        }
        afterColon = false;
      }
      return true;
    }
    function entropy(s) {
      if (!s) return 0;
      const counts = new Map();
      for (const ch of s) counts.set(ch, (counts.get(ch) || 0) + 1);
      const total = [...s].length;
      let e = 0;
      for (const c of counts.values()) e -= (c / total) * Math.log2(c / total);
      return e;
    }
    const isByte = (text) => { const v = parseNum(text); return v !== null && Number.isInteger(v) && v >= 0 && v <= 255; };
    function parseNum(text) {
      // Python int(text, 0): decimal or 0x/0o/0b prefixes, no floats
      if (/^0[xX][0-9a-fA-F]+$/.test(text)) return parseInt(text, 16);
      if (/^(0|[1-9][0-9]*)$/.test(text)) return parseInt(text, 10);
      return null;
    }

    function createdDialogs(toks) {
      const out = new Set();
      for (let k = 0; k < toks.length; k++) {
        const t = toks[k];
        if (t.kind === NAME && t.value === "StaticPopupDialogs" && k + 1 < toks.length && isOp(toks[k + 1], "[")) {
          const close = closing(toks, k + 1);
          const key = literalString(toks.slice(k + 2, close));
          if (key && close + 2 < toks.length && isOp(toks[close + 1], "=") && isOp(toks[close + 2], "{")) out.add(key);
        }
      }
      return out;
    }

    function namedAccess(u, facts, t, name, toks, close) {
      const key = u.path.split("#")[0];
      const cap = API_CAPABILITY.get(name);
      if (cap) {
        const e = ev(u, t, `_G["${name}"]`);
        if (facts.cap(cap).length < 40) facts.cap(cap).push(e);
        if (cap === "money") facts.moneyUnits.add(key);
        if (CODE_RUNNERS.has(name)) { facts.list(facts.dynamicCode, key).push(e); facts.hit("DYNAMIC_CODE", e); }
      }
      if (HOOK.has(name) && close + 1 < toks.length && isOp(toks[close + 1], "=")) {
        if (!polyfill(toks, close + 1, name)) {
          const e = ev(u, t, `_G["${name}"] =`);
          facts.hit("BLIZZARD_OVERRIDE_SENSITIVE", e);
          facts.overrides.push(e);
          facts.list(facts.hiding, key).push(e);
        }
      }
    }

    function analyseUnit(u, facts, addonDefines) {
      const s = u.scan;
      const toks = s.tokens;
      const n = toks.length;
      const key = u.path.split("#")[0];
      for (const r of s.refs) {
        const name = API_CAPABILITY.has(r.name) ? r.name : r.name.split(".")[0];
        const cap = API_CAPABILITY.get(name);
        if (cap === undefined || (addonDefines.has(name) && !SENSITIVE_NAMES.has(name))) continue;
        const e = ev(u, r.tok, name);
        if (facts.cap(cap).length < 40) facts.cap(cap).push(e);
        if (cap === "money") facts.moneyUnits.add(key);
        if (CODE_RUNNERS.has(name) && r.isCall) {
          if (templateArgument(toks, r.end)) { facts.list(facts.templateCode, key).push(e); continue; }
          facts.list(facts.dynamicCode, key).push(e);
          facts.hit("DYNAMIC_CODE", e);
        }
        if (cap === "sabotage") facts.hit(name === "GuildDisband" ? "GUILD_DISBAND" : "SABOTAGE", e);
        if (cap === "macros" && (name === "CreateMacro" || name === "EditMacro")) facts.hit("MACRO_WRITE", e);
      }
      for (let k = 0; k < n; k++) {
        const t = toks[k];
        const nxt = k + 1 < n ? toks[k + 1] : null;
        const nxt2 = k + 2 < n ? toks[k + 2] : null;
        const prev = k ? toks[k - 1] : null;
        if (t.kind === NAME) {
          if (REGISTER_METHODS.has(t.value) && nxt && isOp(nxt, "(") && nxt2) {
            const arg = nxt2.kind === STRING ? nxt2 : k + 4 < n && isOp(toks[k + 3], ",") ? toks[k + 4] : null;
            if (arg && arg.kind === STRING && REMOTE_EVENTS.has(arg.value)) facts.remoteInput.add(key);
          }
          if (t.value === "RegisterComm" && prev && isOp(prev, ":")) facts.remoteInput.add(key);
          if (t.value === "RegisterAddonMessagePrefix") facts.remoteInput.add(key);
          if (t.value.endsWith("AddMessageEventFilter") && nxt && isOp(nxt, "(") && nxt2 && nxt2.kind === STRING && HIDING_EVENTS.has(nxt2.value)) {
            const e = ev(u, t, nxt2.value);
            facts.hit("HIDING_FILTER", e);
            facts.list(facts.hiding, key).push(e);
          }
          if (t.value === "hooksecurefunc" && nxt && isOp(nxt, "(")) {
            let target = null;
            if (nxt2 && nxt2.kind === STRING) target = nxt2.value;
            else if (nxt2 && nxt2.kind === NAME && k + 4 < n && isOp(toks[k + 3], ",") && toks[k + 4].kind === STRING) target = `${nxt2.value}.${toks[k + 4].value}`;
            if (target && (HOOK.has(target) || HOOK.has(target.split(".").pop()))) facts.hit("SENSITIVE_HOOK", ev(u, t, target));
          }
          if (startsWithAny(t.value, FRAME_PREFIXES) && !(prev && isOp(prev, ".", ":"))) {
            let j = k + 1;
            while (j + 1 < n && isOp(toks[j], ".") && toks[j + 1].kind === NAME) j += 2;
            const method = j + 1 < n && isOp(toks[j], ":") && toks[j + 1].kind === NAME ? toks[j + 1].value : "";
            const direct = j === k + 1;
            if (["Click", "SetScript", "HookScript"].includes(method) || (direct && ["Hide", "SetAlpha", "SetShown", "EnableMouse"].includes(method))) {
              const e = ev(u, t, `${t.value}:${toks[j + 1].value}`);
              facts.hit("SENSITIVE_FRAME", e);
              facts.list(facts.hiding, key).push(e);
            }
          }
          if (t.value === "StaticPopupDialogs" && nxt && isOp(nxt, "[")) {
            const close = closing(toks, k + 1);
            const dialog = literalString(toks.slice(k + 2, close));
            if (close + 3 < n && isOp(toks[close + 1], ".") && toks[close + 2].kind === NAME && isOp(toks[close + 3], "=") && !facts.ownDialogs.has(dialog)) {
              const e = ev(u, t, `StaticPopupDialogs[…].${toks[close + 2].value}`);
              facts.hit("SENSITIVE_FRAME", e);
              facts.list(facts.hiding, key).push(e);
            }
          }
          if (t.value === "_G" && nxt && isOp(nxt, "[")) {
            const close = closing(toks, k + 1);
            const lit = literalString(toks.slice(k + 2, close));
            if (lit !== null) namedAccess(u, facts, t, lit, toks, close);
            else if (close + 1 < n && isOp(toks[close + 1], "(")) facts.hit("INDIRECT_GLOBAL", ev(u, t, "_G[…](…)"));
          }
          if (!(prev && isOp(prev, ".", ":", ",")) && !(prev && isKw(prev, "local"))) {
            const [full, j] = dotted(toks, k);
            if (HOOK.has(full) && j < n && isOp(toks[j], "=")) {
              if (!isLocal(s, full) && !polyfill(toks, j, full)) {
                const e = ev(u, t, full);
                facts.hit("BLIZZARD_OVERRIDE_SENSITIVE", e);
                facts.overrides.push(e);
                facts.list(facts.hiding, key).push(e);
              }
            }
          }
          if (t.value === "char" && prev && isOp(prev, ".", ":") && nxt && isOp(nxt, "(")) {
            const close = closing(toks, k + 1);
            const nums = toks.slice(k + 2, close).filter((x) => x.kind === NUMBER);
            if (nums.length && nums.length * 2 - 1 === close - k - 2) {
              let text = "";
              for (const x of nums) { const v = parseNum(x.value); if (v === null || v > 0x10ffff) { text = ""; break; } text += String.fromCodePoint(v); }
              if (SENSITIVE_NAMES.has(text)) facts.hit("BUILT_API_NAME", ev(u, t, `string.char → ${text}`));
            }
          }
        } else if (t.kind === STRING) {
          if (nxt && isOp(nxt, "..") && !(prev && isOp(prev, ".."))) {
            const parts = [t.value];
            let j = k;
            while (j + 2 < n && isOp(toks[j + 1], "..") && toks[j + 2].kind === STRING) { parts.push(toks[j + 2].value); j += 2; }
            const joined = parts.join("");
            if (parts.length > 1 && SENSITIVE_NAMES.has(joined)) facts.hit("BUILT_API_NAME", ev(u, t, parts.map((p) => `"${p}"`).join(" .. ") + ` → ${joined}`));
          }
          if (nxt && isOp(nxt, ")") && nxt2 && isOp(nxt2, ":") && k + 3 < n && toks[k + 3].value === "reverse") {
            const rev = [...t.value].reverse().join("");
            if (SENSITIVE_NAMES.has(rev)) facts.hit("BUILT_API_NAME", ev(u, t, `"${t.value}":reverse() → ${rev}`));
          }
          URL_RE.lastIndex = 0;
          let m;
          while ((m = URL_RE.exec(t.value))) {
            const url = m[0].replace(/[.,;)]+$/, "");
            if (!facts.urls.has(url.toLowerCase())) facts.urls.set(url.toLowerCase(), ev(u, t, url));
          }
        }
      }
      obfuscation(u, facts);
    }

    function obfuscation(u, facts) {
      const toks = u.scan.tokens;
      const signals = [];
      for (const t of toks) {
        if (t.kind === STRING && [...t.value].length >= 400) {
          const e = entropy(t.value);
          if (e >= 5.2) signals.push([t, `encoded string of ${[...t.value].length} characters (entropy ${e.toFixed(1)})`]);
        }
      }
      const escapes = u.source.match(ESCAPES_RE);
      if (escapes) signals.push([null, `${escapes.length} string(s) written as escaped character codes`]);
      const scrambled = new Set(toks.filter((t) => t.kind === NAME && SCRAMBLED_RE.test(t.value)).map((t) => t.value));
      if (scrambled.size >= 8) signals.push([null, `${scrambled.size} scrambled names (e.g. ${[...scrambled].sort().slice(0, 3).join(", ")})`]);
      let run = 0, best = 0, runStart = null, bestTok = null;
      for (const t of toks) {
        if (t.kind === NUMBER && isByte(t.value)) {
          run++;
          if (run === 1) runStart = t;
          if (run > best) { best = run; bestTok = runStart; }
        } else if (!isOp(t, ",")) run = 0;
      }
      if (best >= 300) signals.push([bestTok, `table of ${best} byte values`]);
      const names = new Set(toks.filter((t) => t.kind === NAME).map((t) => t.value));
      if (names.has("bxor") && names.has("byte") && names.has("char")) signals.push([null, "XOR decoding (bxor with byte/char)"]);
      const longest = u.lines.reduce((a, l) => Math.max(a, l.length), 0);
      const codeTokens = toks.filter((t) => t.kind === NAME || t.kind === OP).length;
      if (longest >= 8000 && codeTokens > 2000 && u.lines.length < 20) signals.push([null, `minified code (a line of ${longest} characters)`]);
      const kinds = new Set(signals.map(([, d]) => (d.startsWith("encoded") ? "encoded" : d.split(" ")[0])));
      const strong = signals.some(([, d]) => d.includes("escaped") || d.includes("byte values") || d.includes("scrambled") || d.includes("minified"));
      if (strong || kinds.size >= 2) {
        facts.obfuscated.add(u.path.split("#")[0]);
        for (const [t, d] of signals.slice(0, 4)) {
          if (t) facts.hit("OBFUSCATION", ev(u, t, d));
          else facts.hit("OBFUSCATION", { file: u.path.split("#")[0], line: 1 + u.lineOffset, detail: d, snippet: "" });
        }
      }
    }

    // -------------------------------------------------------------- toc

    function tocInfo(files) {
      const tocs = [];
      const loaded = new Set();
      let saved = false;
      const lower = new Map();
      for (const p of files.keys()) lower.set(p.toLowerCase(), p);
      function mark(path) {
        if (path.includes("*")) {
          const rx = new RegExp("^" + reEscape(path.toLowerCase()).replace(/\\\*/g, "[^/]*") + "$");
          for (const [low, real] of lower) if (rx.test(low)) mark(real);
          return;
        }
        const real = lower.get(path.toLowerCase());
        if (real === undefined || loaded.has(real)) return;
        loaded.add(real);
        if (real.toLowerCase().endsWith(".xml")) {
          const text = decode(files.get(real)).replace(/<!--[\s\S]*?-->/g, "");
          XML_FILE_REF_RE.lastIndex = 0;
          let m;
          const refs = [];
          while ((m = XML_FILE_REF_RE.exec(text))) refs.push(m[1]);
          for (const ref of refs) mark(normpath(pjoin(dirname(real), ref.replace(/\\/g, "/"))));
        }
      }
      for (const [path, data] of files) {
        if (!path.toLowerCase().endsWith(".toc")) continue;
        const meta = { file: path };
        const base = dirname(path);
        for (const raw of decode(data).split(/\r\n|\r|\n/)) {
          const line = strip(raw);
          if (line.startsWith("##")) {
            const idx = line.indexOf(":");
            const key = strip(idx < 0 ? line.slice(2) : line.slice(2, idx)).toLowerCase();
            const value = idx < 0 ? "" : line.slice(idx + 1);
            if (["title", "author", "version", "interface", "notes"].includes(key) && !(key in meta)) meta[key] = strip(value).replace(/\|c[0-9a-fA-F]{8}|\|r/g, "").slice(0, 120);
            if (key.startsWith("savedvariables")) saved = saved || !!strip(value);
          } else if (line && !line.startsWith("#")) {
            let entry = line.replace(/(\s*\[[^\]]*\])+\s*$/, "").replace(/\\/g, "/");
            entry = entry.split("[Family]").join("*").split("[Game]").join("*").split("[TextLocale]").join("*");
            mark(normpath(pjoin(base, entry)));
          }
        }
        tocs.push(meta);
      }
      return [tocs, loaded, saved];
    }

    // -------------------------------------------------------------- does it load in Forever? (port of forever_check & co.)

    const LOOSE = "__loose__";
    const pyFormat = (s, fields) => s.replace(/\{(\w+)\}/g, (m, k) => (k in fields ? String(fields[k]) : m));

    function tocDirs(files) {
      const dirs = new Set();
      for (const p of files.keys()) if (p.toLowerCase().endsWith(".toc")) dirs.add(dirname(p));
      const depth = (d) => (d ? (d.match(/\//g) || []).length : -1);
      return [...dirs].sort((a, b) => depth(a) - depth(b) || (a < b ? -1 : a > b ? 1 : 0));
    }
    function addonRoots(files) {
      const roots = [];
      for (const d of tocDirs(files)) if (!roots.some((r) => r === "" || d === r || d.startsWith(r + "/"))) roots.push(d);
      return roots;
    }
    function flavorOf(interfaces, lang) {
      for (const v of interfaces) for (const [lo, hi, names] of R.forever.flavors) if (lo <= v && v <= hi) return names[lang];
      return { es: "otra versión", en: "another version" }[lang];
    }
    const numbers = (s) => (s.match(/\d+/g) || []).map((x) => parseInt(x, 10));

    function foreverCheck(files, root, name) {
      const prefix = root ? root + "/" : "";
      const tocs = [...files.keys()].filter((p) => p.toLowerCase().endsWith(".toc") && dirname(p) === root).sort();
      const out = { status: "none", name, toc: "", tocs: tocs.map(basename).join(", "), interface: "" };
      if (!tocs.length) return out;
      const lower = new Map(tocs.map((t) => [basename(t).toLowerCase(), t]));
      let chosen = null;
      for (const suffix of R.forever.toc_suffixes) { const c = lower.get(`${name}${suffix}.toc`.toLowerCase()); if (c) { chosen = c; break; } }
      if (!chosen) { out.status = "no_toc"; out.rename = tocStem(tocs); return out; }
      out.toc = chosen.slice(prefix.length);
      const keyed = new Map();
      let allow = null;
      const exclude = new Set();
      for (const raw of decode(files.get(chosen)).split(/\r\n|\r|\n/)) {
        const line = strip(raw);
        if (!line.startsWith("##")) continue;
        const idx = line.indexOf(":");
        const key = strip(idx < 0 ? line.slice(2) : line.slice(2, idx)).toLowerCase();
        const value = strip(idx < 0 ? "" : line.slice(idx + 1));
        if (R.forever.interface_keys.includes(key)) { if (!keyed.has(key)) keyed.set(key, numbers(value)); }
        else if (key === "allowloadgametype") { allow = allow || new Set(); for (const v of value.split(",")) if (strip(v)) allow.add(strip(v).toLowerCase()); }
        else if (key === "excludeloadgametype") { for (const v of value.split(",")) if (strip(v)) exclude.add(strip(v).toLowerCase()); }
      }
      const gameTypes = ["camelot", "forever", "mainline"];
      if ((allow !== null && !gameTypes.some((g) => allow.has(g))) || gameTypes.some((g) => exclude.has(g))) { out.status = "excluded"; return out; }
      let interfaces = [];
      for (const k of R.forever.interface_keys) if (keyed.get(k) && keyed.get(k).length) { interfaces = keyed.get(k); break; }
      out.interface = interfaces.join(", ");
      const [lo, hi] = R.forever.interface_range;
      if (!interfaces.length) out.status = "unknown";
      else if (interfaces.some((v) => lo <= v && v <= hi)) out.status = "loads";
      else out.status = "outdated";
      return out;
    }

    function tocStem(tocs) {
      const rx = new RegExp(R.forever.flavor_suffix, "i");
      const stems = tocs.map((t) => basename(t).slice(0, -4));
      const plain = stems.filter((s) => !rx.test(s));
      return plain.length ? plain[0] : stems[0].replace(rx, "");
    }

    function foreverDict(check, lang) {
      const [label, detail] = R.forever.load[check.status][lang];
      const fields = Object.assign({}, check, { flavor: flavorOf(numbers(check.interface), lang) });
      return { status: check.status, text: label, detail: pyFormat(detail, fields), toc: check.toc, interface: check.interface };
    }

    function splitPackages(pkg) {
      const roots = addonRoots(pkg.files);
      if (roots.length < 2) return null;
      const groups = new Map(roots.map((r) => [r, { name: basename(r), files: new Map(), hits: [], entries: 0, totalBytes: 0 }]));
      const loose = { name: LOOSE, files: new Map(), hits: [], entries: 0, totalBytes: 0 };
      const owner = (path) => { for (const r of roots) if (path === r || path.startsWith(r + "/")) return groups.get(r); return loose; };
      for (const [path, data] of pkg.files) owner(path).files.set(path, data);
      const all = [...groups.values(), loose];
      for (const h of pkg.hits) {
        const split = new Map();
        for (const e of h.evidence) {
          const g = owner(safeMember(e.file)[0]);
          if (!split.has(g)) split.set(g, { id: h.id, evidence: [] });
          split.get(g).evidence.push(e);
        }
        for (const g of all) if (split.has(g)) g.hits.push(split.get(g));
      }
      for (const g of all) {
        const extra = new Set();
        for (const h of g.hits) for (const e of h.evidence) if (!g.files.has(e.file)) extra.add(e.file);
        g.entries = g.files.size + extra.size;
        g.totalBytes = [...g.files.values()].reduce((s, b) => s + b.length, 0);
      }
      const out = [...groups.values()];
      if (loose.files.size || loose.hits.length) out.push(loose);
      return out;
    }

    // -------------------------------------------------------------- analyse

    function analyse(pkg) {
      const units = buildUnits(pkg.files);
      const addonDefines = new Set();
      for (const u of units) for (const d of u.scan.defines) addonDefines.add(d);
      const facts = newFacts();
      for (const h of pkg.hits) for (const e of h.evidence) facts.hit(h.id, e);
      const [tocs, loaded, saved] = tocInfo(pkg.files);
      const runs = units.filter((u) => !tocs.length || loaded.has(u.path.split("#")[0]));
      for (const u of runs) for (const d of createdDialogs(u.scan.tokens)) facts.ownDialogs.add(d);
      for (const u of runs) analyseUnit(u, facts, addonDefines);
      if (!tocs.length && units.length) facts.hit("PKG_NO_TOC", { file: pkg.name, line: 0, detail: "no .toc", snippet: "" });
      if (tocs.length) {
        for (const path of [...pkg.files.keys()].filter((p) => p.toLowerCase().endsWith(".lua") && !loaded.has(p)).sort())
          facts.hit("PKG_UNLOADED_LUA", { file: path, line: 0, detail: "not listed", snippet: "" });
      }
      const [findings, top] = combine(facts, saved);
      const addons = [...tocs].sort((a, b) => (a.file < b.file ? -1 : a.file > b.file ? 1 : 0));
      const stats2 = {
        files: pkg.entries,
        bytes: pkg.totalBytes,
        lua_files: [...pkg.files.keys()].filter((p) => p.toLowerCase().endsWith(".lua")).length,
        xml_scripts: units.filter((u) => u.path.includes("#")).length,
        lines: units.reduce((a, u) => a + u.lines.length, 0),
      };
      const caps = {};
      for (const c of Object.keys(R.capabilities)) caps[c] = facts.caps.get(c) || [];
      const roots = addonRoots(pkg.files);
      const root = roots.length === 1 ? roots[0] : "";
      const name = root ? basename(root) : pkg.name.replace(/\.zip$/i, "");
      return { target: pkg.name, severity: top, capabilities: caps, findings, addons, stats: stats2, forever: foreverCheck(pkg.files, root, name) };
    }

    function analyseAny(pkg) {
      const parts = splitPackages(pkg);
      if (parts === null) return analyse(pkg);
      return { multi: true, target: pkg.name, reports: parts.map(analyse) };
    }

    function multiToDict(m, lang) {
      const reports = m.reports.map((r) => toDict(r, lang));
      let top = "info";
      for (const r of m.reports) if (ORDER[r.severity] > ORDER[top]) top = r.severity;
      const summary = m.reports.map((r, i) => {
        const d = reports[i];
        const a = r.addons[0] || {};
        return {
          name: d.target,
          title: a.title || d.target,
          version: a.version || "",
          verdict: d.verdict,
          forever: { status: d.forever.status, text: d.forever.text },
          capabilities: d.capabilities.map((c) => ({ id: c.id, text: R.capability_short[c.id][lang] })),
        };
      });
      return {
        tool: { name: "addon-sentry", version: VERSION },
        target: m.target,
        multi: true,
        verdict: { level: top, text: R.verdicts[top][lang] },
        summary,
        reports,
        stats: { addons: m.reports.filter((r) => r.target !== LOOSE).length, files: reports.reduce((s, d) => s + d.stats.files, 0), lines: reports.reduce((s, d) => s + d.stats.lines, 0) },
        disclaimer: R.disclaimer[lang],
      };
    }

    function combine(facts, saved) {
      for (const [path, evs] of facts.dynamicCode) {
        if (facts.remoteInput.has(path)) for (const e of evs.slice(0, 3)) facts.hit("REMOTE_CODE", e);
        else if (facts.remoteInput.size) for (const e of evs.slice(0, 3)) facts.hit("LISTENS_AND_RUNS", e);
      }
      for (const path of [...facts.obfuscated].sort()) {
        for (const e of [...(facts.dynamicCode.get(path) || []), ...(facts.templateCode.get(path) || [])].slice(0, 3)) facts.hit("OBFUSCATED_LOADER", e);
      }
      const money = facts.caps.get("money") || [];
      if (facts.overrides.length && money.length) for (const e of facts.overrides.slice(0, 5)) facts.hit("HIDDEN_MONEY", e);
      else if (money.length && [...facts.hiding.keys()].some((p) => facts.moneyUnits.has(p))) {
        for (const [path, evs] of facts.hiding) if (facts.moneyUnits.has(path)) for (const e of evs.slice(0, 3)) facts.hit("MONEY_AND_HIDING", e);
      }
      const friends = (facts.caps.get("account") || []).filter((e) => FRIEND_LIST_APIS.has(e.detail));
      if (friends.length && (facts.caps.get("chat") || []).length) for (const e of friends.slice(0, 5)) facts.hit("EXFILTRATION", e);
      const stats = (facts.caps.get("profiling") || []).filter((e) => e.detail === "GetComparisonStatistic" || e.detail === "SetAchievementComparisonUnit");
      if (stats.length && saved) for (const e of stats.slice(0, 5)) facts.hit("PROFILING", e);
      if (facts.urls.size) for (const e of [...facts.urls.values()].slice(0, 30)) facts.hit("URL", e);

      const findings = [...facts.hits.values()].sort((a, b) => {
        const d = ORDER[R.findings[b.id].severity] - ORDER[R.findings[a.id].severity];
        return d || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
      });
      let top = "info";
      for (const h of findings) { const s = R.findings[h.id].severity; if (ORDER[s] > ORDER[top]) top = s; }
      return [findings, top];
    }

    function toDict(report, lang) {
      if (report.multi) return multiToDict(report, lang);
      return {
        tool: { name: "addon-sentry", version: VERSION },
        target: report.target === LOOSE ? R.audit[lang].loose : report.target,
        verdict: { level: report.severity, text: R.verdicts[report.severity][lang] },
        forever: report.forever ? foreverDict(report.forever, lang) : null,
        addons: report.addons,
        capabilities: Object.entries(report.capabilities)
          .filter(([, evs]) => evs.length)
          .map(([cap, evs]) => ({ id: cap, text: R.capabilities[cap][lang], evidence: evs.slice(0, 12), count: evs.length })),
        findings: report.findings.map((h) => ({
          id: h.id,
          severity: R.findings[h.id].severity,
          severity_text: R.severity_names[lang][R.findings[h.id].severity],
          title: R.findings[h.id][lang][0],
          explanation: R.findings[h.id][lang][1],
          evidence: h.evidence.slice(0, 20),
          count: h.evidence.length,
        })),
        stats: report.stats,
        disclaimer: R.disclaimer[lang],
      };
    }

    async function scanZip(buffer, name, lang) {
      const pkg = await readZip(buffer, name || "addon.zip");
      return toDict(analyseAny(pkg), lang || "es");
    }

    // -------------------------------------------------------------- WeakAuras strings (port of auras.py)

    const AURA = R.aura;
    const AURA_BLOCKED = new Set(AURA.blocked);
    const CODE_KEYS = new Set(AURA.code_keys);
    const SEND_CHAT = new Set(AURA.send_chat_types);
    const MAX_INPUT_CHARS = 8 * 1024 * 1024, MAX_INFLATED = 64 * 1024 * 1024, MAX_OBJECTS = 2000000, MAX_DEPTH = 120;
    const ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()";
    const SIX = new Map([...ALPHABET].map((c, i) => [c.charCodeAt(0), i]));
    let luaSpace = " ";
    for (let c = 0; c < 32; c++) luaSpace += String.fromCharCode(c);
    luaSpace += "\x7f";
    const GENERIC_KEY = /custom|func$/i;
    const CODE_LIKE = /(?<![A-Za-z0-9_])(?:function|return)(?![A-Za-z0-9_])/;
    const DEC = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;
    const HEX = /^[+-]?0[xX][0-9a-fA-F]+$/;
    const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
    const DAMAGED = "cannot decompress: the string is damaged or cut short";
    const OTHER_FORMATS = [["!PLATER:", "Plater"], ["!E1!", "ElvUI"], ["!MDT", "Mythic Dungeon Tools"]];
    const utf8 = new TextDecoder("utf-8");
    const cpSlice = (s, n) => Array.from(s).slice(0, n).join("");  // Python slices by code point
    // Lua booleans as table keys (a Map keeps them apart from numbers already; these are just markers)
    const LUA_TRUE = { luaBool: true }, LUA_FALSE = { luaBool: false };

    function decodeForPrint(s) {
      s = pyStrip(s, luaSpace);
      if (s.length === 1) return null;
      const out = [];
      let i = 0;
      const n = s.length;
      while (i + 3 < n) {
        const x = [0, 1, 2, 3].map((j) => SIX.get(s.charCodeAt(i + j)));
        if (x.includes(undefined)) return null;
        const cache = x[0] + x[1] * 64 + x[2] * 4096 + x[3] * 262144;
        out.push(cache & 255, (cache >> 8) & 255, cache >> 16);
        i += 4;
      }
      let cache = 0, bits = 0;
      while (i < n) {
        const x = SIX.get(s.charCodeAt(i));
        if (x === undefined) return null;
        cache += x * 2 ** bits;
        bits += 6;
        i++;
      }
      while (bits >= 8) {
        out.push(cache % 256);
        cache = Math.floor(cache / 256);
        bits -= 8;
      }
      return new Uint8Array(out);
    }

    async function inflateLimited(bytes) {
      const ds = new DecompressionStream("deflate-raw");
      const writer = ds.writable.getWriter();
      writer.write(bytes).catch(() => {});
      writer.close().catch(() => {});
      const reader = ds.readable.getReader();
      const parts = [];
      let total = 0;
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          total += value.length;
          if (total > MAX_INFLATED) {
            reader.cancel().catch(() => {});
            throw new ScanError("the string unpacks to more than 64 MB; refusing to read it");
          }
          parts.push(value);
        }
      } catch (e) {
        if (e instanceof ScanError) throw e;
        throw new ScanError(DAMAGED);
      }
      const out = new Uint8Array(total);
      let p = 0;
      for (const part of parts) { out.set(part, p); p += part.length; }
      return out;
    }

    // Pre-2018 strings: WeakAuras' decodeB64 + LibCompress (LZW or Huffman) + AceSerializer
    const V0_ERROR = "this is not a WeakAuras import string (they start with !WA:2!)";
    function decodeB64v0(s) {
      const out = [];
      let bits = 0, nbits = 0, i = 0;
      const n = s.length;
      for (;;) {
        if (nbits >= 8) { out.push(bits % 256); bits = Math.floor(bits / 256); nbits -= 8; }
        const x = i < n ? SIX.get(s.charCodeAt(i)) || 0 : 0;
        bits += x * 2 ** nbits;
        nbits += 6;
        if (i >= n) break;
        i++;
      }
      return new Uint8Array(out);
    }
    function lcNumber(d, i) {
      let a = d[i];
      if (a > 249) {
        a = 256 - a;
        if (i + a >= d.length) throw new ScanError(V0_ERROR);
        let r = 0;
        for (let k = i + a; k > i; k--) r = r * 255 + d[k] - 1;
        return [r, a + 1];
      }
      return [a, 1];
    }
    function concatBytes(a, b) { const out = new Uint8Array(a.length + b.length); out.set(a); out.set(b, a.length); return out; }
    function lcLzw(d) {
      d = d.subarray(1);
      if (!d.length) throw new ScanError(V0_ERROR);
      const table = new Map();
      for (let i = 0; i < 256; i++) table.set(i, Uint8Array.of(i));
      let size = 256;
      let [k, step] = lcNumber(d, 0);
      let t = step;
      if (!table.has(k)) throw new ScanError(V0_ERROR);
      let w = table.get(k);
      const parts = [w];
      let total = w.length;
      while (t < d.length) {
        [k, step] = lcNumber(d, t);
        t += step;
        const got = table.get(k);
        const entry = got && got.length ? got : concatBytes(w, w.subarray(0, 1));
        parts.push(entry);
        total += entry.length;
        if (total > MAX_INFLATED) throw new ScanError("the string unpacks to more than 64 MB; refusing to read it");
        table.set(size++, concatBytes(w, entry.subarray(0, 1)));
        w = entry;
      }
      const out = new Uint8Array(total);
      let p = 0;
      for (const part of parts) { out.set(part, p); p += part.length; }
      return out;
    }
    function lcUnescape(code, codeLen) {
      let out = 0n, l = 0n;
      for (let i = 0n; i < codeLen; i++) {
        if ((code >> i) & 1n) { out |= 1n << l; i++; }
        l++;
      }
      return [out, l];
    }
    function lcHuffman(d) {
      if (d.length < 5) throw new ScanError(V0_ERROR);
      const numSymbols = d[1] + 1;
      const orig = d[2] + d[3] * 256 + d[4] * 65536;
      if (orig === 0) return new Uint8Array(0);
      // BigInt bit queue: codes may be up to 32 bits plus the stop bits
      let bits = 0n, nbits = 0n, i = 5, state = 0, symbol = 0, n = 0;
      const codes = new Map();
      let minLen = 1000n, maxLen = 0n;
      while (n < numSymbols) {
        if (i >= d.length) throw new ScanError(V0_ERROR);
        bits |= BigInt(d[i]) << nbits;
        nbits += 8n;
        if (state === 0) { symbol = Number(bits & 255n); bits >>= 8n; nbits -= 8n; state = 1; }
        else {
          for (let k = 0n; k < nbits - 1n; k++) {
            if (((bits >> k) & 3n) === 3n) {
              if (k > 32n) throw new ScanError(V0_ERROR);
              const code = bits & ((1n << k) - 1n);
              bits >>= k + 2n;
              nbits -= k + 2n;
              const [c, cl] = lcUnescape(code, k);
              codes.set(`${cl}:${c}`, symbol);
              if (cl < minLen) minLen = cl;
              if (cl > maxLen) maxLen = cl;
              n++;
              state = 0;
              break;
            }
          }
        }
        i++;
      }
      bits &= 0xffffffffn;
      const out = new Uint8Array(orig);
      let size = 0, len = minLen;
      for (;;) {
        if (len <= nbits) {
          const sym = codes.get(`${len}:${bits & ((1n << len) - 1n)}`);
          if (sym !== undefined) {
            out[size++] = sym;
            if (size >= orig) break;
            bits >>= len;
            nbits -= len;
            len = minLen;
          } else {
            len++;
            if (len > maxLen) throw new ScanError(V0_ERROR);
          }
        } else {
          bits |= BigInt(i < d.length ? d[i] : 0) << nbits;
          nbits += 8n;
          if (i > d.length) break;
          i++;
        }
      }
      return out.subarray(0, size);
    }
    function libcompressDecompress(d) {
      if (!d.length) throw new ScanError(V0_ERROR);
      if (d[0] === 1) return d.subarray(1);
      if (d[0] === 2) return lcLzw(d);
      if (d[0] === 3) return lcHuffman(d);
      throw new ScanError(V0_ERROR);
    }

    function luaNumber(s) {
      if (HEX.test(s)) return parseInt(s, 16);
      if (DEC.test(s)) return Number(s);
      throw new ScanError("cannot deserialize: bad number");
    }

    function luaSet(t, k, v) {
      if (k === null || k === undefined || (typeof k === "number" && Number.isNaN(k))) throw new ScanError("cannot deserialize: bad table key");
      if (k === true) k = LUA_TRUE;
      else if (k === false) k = LUA_FALSE;
      if (v === null || v === undefined) t.delete(k);
      else t.set(k, v);
    }

    function deserializeLibSerialize(d) {
      let p = 0, count = 0, depth = 0;
      const strings = [], tables = [];
      const bytes = (n) => {
        if (p + n > d.length) throw new ScanError("cannot deserialize: data ends early");
        const b = d.subarray(p, p + n);
        p += n;
        return b;
      };
      const int = (n) => { let v = 0; for (const b of bytes(n)) v = v * 256 + b; return v; };
      const string = (n) => { const v = utf8.decode(bytes(n)); if (n > 2) strings.push(v); return v; };
      const table = (entries, value) => {
        if (!value) { value = new Map(); tables.push(value); }
        for (let i = 0; i < entries; i++) { const k = obj(); const v = obj(); luaSet(value, k, v); }
        return value;
      };
      const array = (entries, value) => {
        if (!value) { value = new Map(); tables.push(value); }
        for (let i = 1; i <= entries; i++) luaSet(value, i, obj());
        return value;
      };
      const mixed = (a, b) => { const value = new Map(); tables.push(value); array(a, value); table(b, value); return value; };
      const ref = (refs, n) => { const i = int(n); if (i < 1 || i > refs.length) throw new ScanError("cannot deserialize: bad reference"); return refs[i - 1]; };
      function obj() {
        if (++count > MAX_OBJECTS) throw new ScanError("too many values in the string");
        if (++depth > MAX_DEPTH) throw new ScanError("tables nested too deep");
        try { return one(); } finally { depth--; }
      }
      function one() {
        const v = int(1);
        if (v % 2 === 1) return (v - 1) / 2;
        if (v % 4 === 2) {
          let typ = (v - 2) / 4;
          const c = Math.floor(typ / 4);
          typ %= 4;
          if (typ === 0) return string(c);
          if (typ === 1) return table(c);
          if (typ === 2) return array(c);
          return mixed((c % 4) + 1, Math.floor(c / 4) + 1);
        }
        if (v % 8 === 4) {
          const packed = int(1) * 256 + v;
          return v % 16 === 12 ? -((packed - 12) / 16) : (packed - 4) / 16;
        }
        const typ = v / 8;
        if (typ === 0) return null;
        if (typ >= 1 && typ <= 8) { const n = int([2, 3, 4, 7][Math.floor((typ - 1) / 2)]); return typ % 2 === 0 ? -n : n; }
        if (typ === 9) { const b = bytes(8); return new DataView(b.buffer, b.byteOffset, 8).getFloat64(0, false); }
        if (typ === 10 || typ === 11) {
          const f = luaNumber(String.fromCharCode(...bytes(int(1))));
          return typ === 11 ? -f : f;
        }
        if (typ === 12) return true;
        if (typ === 13) return false;
        if (typ >= 14 && typ <= 16) return string(int(typ - 13));
        if (typ >= 17 && typ <= 19) return table(int(typ - 16));
        if (typ >= 20 && typ <= 22) return array(int(typ - 19));
        if (typ >= 23 && typ <= 25) { const size = typ - 22; const a = int(size); const b = int(size); return mixed(a, b); }
        if (typ >= 26 && typ <= 28) return ref(strings, typ - 25);
        if (typ >= 29 && typ <= 31) return ref(tables, typ - 28);
        throw new ScanError("cannot deserialize: unknown type");
      }
      const version = int(1);
      if (version > 2) throw new ScanError("cannot deserialize: unknown LibSerialize version");
      const out = [];
      while (p < d.length) out.push(obj());
      return out;
    }

    function deserializeAce(bytesIn) {
      let text = "";
      for (let i = 0; i < bytesIn.length; i += 8192) text += String.fromCharCode(...bytesIn.subarray(i, i + 8192));
      text = text.replace(/[\x00-\x1f\x7f ]/g, "");
      const toks = [...text.matchAll(/(\^.)([^^]*)/g)].map((m) => [m[1], m[2]]);
      let ti = 0;
      const next = () => (ti < toks.length ? toks[ti++] : [null, null]);
      const first = next();
      if (first[0] !== "^1") throw new ScanError("cannot deserialize: not AceSerializer data");
      let counter = 0;
      const unescape = (m) => {
        const c = m[1];
        if (c < "@") throw new ScanError("cannot deserialize: bad escape");
        if (c < "z") return String.fromCharCode(c.charCodeAt(0) - 64);
        const out = { z: "\x1e", "{": "\x7f", "|": "~", "}": "^" }[c];
        if (out === undefined) throw new ScanError("cannot deserialize: bad escape");
        return out;
      };
      function value(ctl, data, depth) {
        if (++counter > MAX_OBJECTS) throw new ScanError("too many values in the string");
        if (depth > MAX_DEPTH) throw new ScanError("tables nested too deep");
        if (ctl === "^S") {
          const raw = data.replace(/~./g, unescape);
          return utf8.decode(Uint8Array.from(raw, (ch) => ch.charCodeAt(0)));
        }
        if (ctl === "^N") {
          if (data === "1.#INF" || data === "inf") return Infinity;
          if (data === "-1.#INF" || data === "-inf") return -Infinity;
          return luaNumber(data);
        }
        if (ctl === "^F") {
          const [ctl2, e] = next();
          if (ctl2 !== "^f") throw new ScanError("cannot deserialize: bad float");
          const mant = luaNumber(data), ex = luaNumber(e);
          return mant === 0 ? 0 : mant * 2 ** ex;
        }
        if (ctl === "^B") return true;
        if (ctl === "^b") return false;
        if (ctl === "^Z") return null;
        if (ctl === "^T") {
          const t = new Map();
          for (;;) {
            const [kc, kd] = next();
            if (kc === null) throw new ScanError("cannot deserialize: table not closed");
            if (kc === "^t") return t;
            const k = value(kc, kd, depth + 1);
            const [vc, vd] = next();
            if (vc === null) throw new ScanError("cannot deserialize: table not closed");
            const v = value(vc, vd, depth + 1);
            if (k === null || v === null) throw new ScanError("cannot deserialize: bad table");
            luaSet(t, k, v);
          }
        }
        throw new ScanError("cannot deserialize: bad control code");
      }
      const out = [];
      for (;;) {
        const [ctl, data] = next();
        if (ctl === null) break;
        if (ctl === "^^") return out;
        out.push(value(ctl, data, 0));
      }
      throw new ScanError("cannot deserialize: AceSerializer end marker missing");
    }

    async function auraDecode(text) {
      if (Array.from(text).length > MAX_INPUT_CHARS) throw new ScanError("the string is longer than 8 MB");
      const s = pyStrip(text, luaSpace);
      for (const [prefix, name] of OTHER_FORMATS) {
        if (s.startsWith(prefix)) throw new ScanError(`this looks like a ${name} string; only WeakAuras strings are supported for now`);
      }
      const m = /^!WA:(\d+)!([\s\S]+)$/.exec(s);
      let version, body;
      if (m) { version = parseInt(m[1], 10); body = m[2]; }
      else if (s.startsWith("!")) { version = 1; body = s.slice(1); }
      else { version = 0; body = s; }
      if (version === 0) {
        let values;
        try { values = deserializeAce(libcompressDecompress(decodeB64v0(body))); }
        catch (e) { if (e instanceof ScanError) throw new ScanError(V0_ERROR); throw e; }
        if (!values.length || !(values[0] instanceof Map)) throw new ScanError(V0_ERROR);
        return ["WA:0", values[0]];
      }
      const raw = decodeForPrint(body);
      if (raw === null) throw new ScanError("cannot decode: the string has characters a WeakAuras export never has (was it cut or changed?)");
      const data = await inflateLimited(raw);
      const values = version >= 2 ? deserializeLibSerialize(data) : deserializeAce(data);
      if (!values.length || !(values[0] instanceof Map)) throw new ScanError("the string decodes, but not to a WeakAuras export");
      return [`WA:${version}`, values[0]];
    }

    function pyFloatRepr(n) {
      // Python's repr: shortest digits, exponent form when exp < -4 or exp >= 16 ("1e-05", "1e+16")
      const [mant, exp] = n.toExponential().split("e");
      const e = parseInt(exp, 10);
      if (e < -4 || e >= 16) return `${mant}e${e < 0 ? "-" : "+"}${String(Math.abs(e)).padStart(2, "0")}`;
      return String(n);
    }
    function numText(n) {
      if (n === Infinity) return "inf";
      if (n === -Infinity) return "-inf";
      return Number.isInteger(n) ? String(n) : pyFloatRepr(n);
    }
    function keyText(k) {
      if (k === LUA_TRUE) return "[true]";
      if (k === LUA_FALSE) return "[false]";
      if (typeof k === "number") return `[${numText(k)}]`;
      if (typeof k === "string") return IDENT.test(k) ? `.${k}` : `["${k.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")}"]`;
      return "[table]";
    }
    function keyRank(k) {
      if (typeof k === "number") return 0;
      if (typeof k === "string") return 1;
      if (k === LUA_TRUE || k === LUA_FALSE) return 2;
      return 3;
    }
    function cmpCodePoints(a, b) {
      // Python compares strings by code point; JS < compares UTF-16 units
      const A = Array.from(a), B = Array.from(b);
      for (let i = 0; i < Math.min(A.length, B.length); i++) {
        const x = A[i].codePointAt(0), y = B[i].codePointAt(0);
        if (x !== y) return x - y;
      }
      return A.length - B.length;
    }
    function keyCmp(a, b) {
      const ra = keyRank(a), rb = keyRank(b);
      if (ra !== rb) return ra - rb;
      if (ra === 0) return a - b;
      if (ra === 1) return cmpCodePoints(a, b);
      if (ra === 2) return (a === LUA_TRUE ? 1 : 0) - (b === LUA_TRUE ? 1 : 0);
      return 0;
    }
    function isCode(key, value, parent) {
      if (!strip(value)) return false;
      if (CODE_KEYS.has(key)) return true;
      if (key === "value" && parent.get("variable") === "customcheck") return true;
      return GENERIC_KEY.test(key) && CODE_LIKE.test(value);
    }
    function chatDetail(t) {
      const kind = t.get("message_type");
      const dest = t.get("message_dest");
      if (kind === "WHISPER" && typeof dest === "string" && strip(dest)) return `WHISPER → ${cpSlice(strip(dest), 40)}`;
      return String(kind);
    }
    const lstripDot = (s) => s.replace(/^\.+/, "");

    function auraExtract(fmt, transmit) {
      const root = transmit.get("d");
      if (!(root instanceof Map)) throw new ScanError("the string decodes, but has no aura in it");
      const displays = [root];
      const children = transmit.get("c");
      if (children instanceof Map) {
        const ks = [...children.keys()].filter((k) => typeof k === "number" && Number.isInteger(k)).sort((a, b) => a - b);
        for (const k of ks) if (children.get(k) instanceof Map) displays.push(children.get(k));
      }
      const sv = transmit.get("s");
      const out = { format: fmt, addonVersion: typeof sv === "string" ? sv : "", auras: [], code: [], chat: [], urls: [] };
      const seenIds = new Map();
      for (const d of displays) {
        let name = d.get("id");
        name = typeof name === "string" && strip(name) ? name : "(no name)";
        if (seenIds.has(name)) { seenIds.set(name, seenIds.get(name) + 1); name = `${name} (${seenIds.get(name)})`; }
        else seenIds.set(name, 1);
        out.auras.push(name);
        const url = d.get("url");
        if (typeof url === "string" && strip(url) && !out.urls.includes(strip(url))) out.urls.push(strip(url));
        walk(d, "", name, out, new Set());
      }
      return out;
    }
    function walk(t, path, aura, out, seen) {
      if (seen.has(t)) return;
      seen.add(t);
      if (t.get("do_message") === true && SEND_CHAT.has(t.get("message_type"))) out.chat.push([aura, lstripDot(path) || "(aura)", chatDetail(t)]);
      else if (t.get("property") === "chat" && t.get("value") instanceof Map) {
        const v = t.get("value");
        if (SEND_CHAT.has(v.get("message_type"))) out.chat.push([aura, lstripDot(path + ".value"), chatDetail(v)]);
      }
      for (const k of [...t.keys()].sort(keyCmp)) {
        const v = t.get(k);
        const here = path + keyText(k);
        if (v instanceof Map) walk(v, here, aura, out, seen);
        else if (typeof v === "string" && typeof k === "string" && isCode(k, v, t)) out.code.push({ aura, path: lstripDot(here), code: v });
      }
    }

    async function analyseAura(text) {
      const [fmt, transmit] = await auraDecode(text);
      const exp = auraExtract(fmt, transmit);
      const label = (a) => a.split("#").join("＃");
      const units = exp.code.map((c) => ({ path: `${label(c.aura)} › ${c.path}`, source: c.code, lineOffset: 0 }));
      for (const u of units) { u.scan = scan(u.path, u.source); u.lines = u.source.split("\n"); }
      const facts = newFacts();
      for (const u of units) for (const d of createdDialogs(u.scan.tokens)) facts.ownDialogs.add(d);
      for (const u of units) {
        analyseUnit(u, facts, new Set());
        for (const r of u.scan.refs) {
          const name = AURA_BLOCKED.has(r.name) ? r.name : r.name.split(".")[0];
          if (AURA_BLOCKED.has(name)) facts.hit("AURA_BLOCKED", ev(u, r.tok, name));
        }
      }
      for (const [aura, path, detail] of exp.chat) {
        if (facts.cap("chat").length < 40) facts.cap("chat").push({ file: `${label(aura)} › ${path}`, line: 0, detail, snippet: "" });
      }
      const [findings, top] = combine(facts, false);
      const meta = { file: `WeakAuras (${exp.format})`, title: cpSlice(exp.auras[0], 120) };
      if (exp.addonVersion) meta.version = `WeakAuras ${cpSlice(exp.addonVersion, 40)}`;
      if (exp.urls.length) meta.url = cpSlice(exp.urls[0], 200);
      const stats = {
        auras: exp.auras.length,
        code_pieces: units.length,
        bytes: new TextEncoder().encode(text).length,
        lines: units.reduce((a, u) => a + u.lines.length, 0),
      };
      const caps = {};
      for (const c of Object.keys(R.capabilities)) caps[c] = facts.caps.get(c) || [];
      return { target: exp.auras[0], severity: top, capabilities: caps, findings, addons: [meta], stats };
    }

    async function scanAura(text, lang) {
      return toDict(await analyseAura(text), lang || "es");
    }

    return { scanZip, scanAura, readZip, readFiles, analyse, analyseAny, analyseAura, toDict };
  }

  return { VERSION, ScanError, tokenize, scan, make };
});
