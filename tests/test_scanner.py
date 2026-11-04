import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from addon_sentry import cli, engine

FIX = Path(__file__).parent / "fixtures"


def verdict(name):
    return engine.scan_path(FIX / name)


def ids(report):
    return {h.id for h in report.findings}


@pytest.mark.parametrize(
    "name, level, must",
    [
        ("Backdoor", "critical", {"REMOTE_CODE"}),
        ("XmlBackdoor", "critical", {"REMOTE_CODE"}),
        ("AuctionScam", "critical", {"HIDDEN_MONEY", "BLIZZARD_OVERRIDE_SENSITIVE"}),
        ("Packed", "critical", {"OBFUSCATED_LOADER", "OBFUSCATION"}),
        ("BuiltNames", "high", {"BUILT_API_NAME"}),
        ("GuildNuke", "high", {"GUILD_DISBAND"}),
        ("Profiler", "medium", {"PROFILING"}),
        ("Clean", "info", set()),
    ],
)
def test_fixture_verdicts(name, level, must):
    r = verdict(name)
    assert r.severity == level
    assert must <= ids(r)


def test_built_names_all_three_tricks():
    details = [e.detail for h in verdict("BuiltNames").findings if h.id == "BUILT_API_NAME" for e in h.evidence]
    assert any("SendMail" in d for d in details)
    assert any("InitiateTrade" in d for d in details)
    assert any("SetTradeMoney" in d for d in details)


def test_unloaded_files_do_not_count_but_are_listed():
    r = verdict("Clean")
    assert "DYNAMIC_CODE" not in ids(r) and "money" not in {c for c, e in r.capabilities.items() if e}
    unloaded = next(h for h in r.findings if h.id == "PKG_UNLOADED_LUA")
    assert unloaded.evidence[0].file.endswith("NotInToc.lua")


def test_evidence_points_at_the_line():
    ev = next(h for h in verdict("Backdoor").findings if h.id == "REMOTE_CODE").evidence[0]
    assert ev.file == "Backdoor/Core.lua" or ev.file.endswith("Core.lua")
    assert ev.line == 6 and "loadstring(msg)" in ev.snippet


def test_xml_line_numbers_are_file_lines():
    ev = next(h for h in verdict("XmlBackdoor").findings if h.id == "REMOTE_CODE").evidence[0]
    assert ev.file == "UI.xml" and ev.line == 7


def lua_report(code, toc="## Interface: 16001\nMain.lua\n", extra=None):
    files = {"A/A.toc": toc.encode(), "A/Main.lua": code.encode()}
    files.update({k: v.encode() for k, v in (extra or {}).items()})
    return engine.analyse(engine.Package("A", files, [], len(files), 0))


def test_template_loadstring_is_not_dynamic():
    # CallbackHandler-style: code is a string in the file itself
    src = 'local code = [[ return function() end ]]\ncode = code:gsub("X", "Y")\nlocal f = loadstring(code)\nlocal g = loadstring("return _G[\'" .. name .. "\']")'
    r = lua_report(src)
    assert "DYNAMIC_CODE" not in ids(r)


def test_dynamic_loadstring_is_low_alone_and_critical_with_remote_input():
    assert "DYNAMIC_CODE" in ids(lua_report("local f = loadstring(GetUserScript())"))
    assert lua_report("local f = loadstring(GetUserScript())").severity == "low"
    r = lua_report('self:RegisterComm("PFX", function(_, msg) RunScript(msg) end)')
    assert r.severity == "critical"


def test_listening_in_one_file_and_running_in_another_is_low():
    r = lua_report(
        "local f = loadstring(GetText())",
        toc="## Interface: 16001\nMain.lua\nComm.lua\n",
        extra={"A/Comm.lua": 'f:RegisterEvent("CHAT_MSG_ADDON")'},
    )
    assert "LISTENS_AND_RUNS" in ids(r) and r.severity == "low"


def test_polyfill_is_not_an_override_and_locals_do_not_count():
    r = lua_report("GetMoney = GetMoney or function() return 0 end\nlocal SendMail = function() end\nSendMail()")
    assert "BLIZZARD_OVERRIDE_SENSITIVE" not in ids(r)
    assert not r.capabilities["money"]


def test_override_through_G_and_named_capability():
    r = lua_report('_G["GetMoney"] = function() return 99999 end\n_G["SendMail"]("x", "y", "")')
    assert {"BLIZZARD_OVERRIDE_SENSITIVE", "HIDDEN_MONEY"} <= ids(r)
    assert r.capabilities["money"][0].detail == '_G["SendMail"]'


def test_skin_alpha_on_children_is_not_flagged_but_clicks_are():
    r = lua_report("TradeFrame.Portrait:SetAlpha(0)\nStaticPopup1.button1:Click()")
    frames = [e.detail for h in r.findings if h.id == "SENSITIVE_FRAME" for e in h.evidence]
    assert frames == ["StaticPopup1:Click"]


def test_own_dialog_changes_are_fine_blizzard_dialog_changes_are_not():
    r = lua_report('StaticPopupDialogs["MYADDON_OK"] = { text = "x" }\nStaticPopupDialogs["MYADDON_OK"].text = "y"')
    assert "SENSITIVE_FRAME" not in ids(r)
    r = lua_report('StaticPopupDialogs["CONFIRM_BINDER"].OnAccept = function() end')
    assert "SENSITIVE_FRAME" in ids(r)


def test_dialog_change_does_not_break_later_checks_in_the_file():
    # Regression: the dialog key used to overwrite the file key, so the remote-code link was lost.
    src = 'StaticPopupDialogs["CONFIRM_BINDER"].OnAccept = f\nf:RegisterEvent("CHAT_MSG_WHISPER")\nRunScript(msg)'
    assert "REMOTE_CODE" in ids(lua_report(src))


def test_money_with_chat_filter_in_same_file_is_medium_only():
    r = lua_report('ChatFrame_AddMessageEventFilter("CHAT_MSG_MONEY", f)\nSendMail("x", "y", "")')
    assert r.severity == "medium" and "MONEY_AND_HIDING" in ids(r) and "HIDDEN_MONEY" not in ids(r)


def test_friends_list_and_chat_is_low():
    r = lua_report("local n = BNGetNumFriends()\nC_ChatInfo.SendAddonMessage('P', 'x', 'WHISPER', 'y')")
    assert "EXFILTRATION" in ids(r) and r.severity == "low"


def test_no_inline_ignore_for_scanned_code():
    r = lua_report("-- forever-lint: ignore-file\n-- addon-sentry: ignore\nGuildDisband()")
    assert "GUILD_DISBAND" in ids(r)


def test_no_toc_scans_everything():
    r = engine.analyse(engine.Package("x", {"x.lua": b"GuildDisband()"}, [], 1, 0))
    assert {"PKG_NO_TOC", "GUILD_DISBAND"} <= ids(r)


# ---------------------------------------------------------------- zips


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data, *mode in entries:
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            if mode:
                info.external_attr = mode[0] << 16
            z.writestr(info, data)
    return buf.getvalue()


def test_zip_package_problems():
    data = make_zip(
        [
            ("Good/Good.toc", "## Interface: 16001\nGood.lua\n"),
            ("Good/Good.lua", "print(1)"),
            ("Good/Install.exe", "MZ"),
            ("Good/readme.txt.scr", "x"),
            ("../../Startup/evil.lua", "x"),
            ("Good/extra.zip", "PK"),
            ("Good/build.sh", "echo"),
            ("Good/link", "/etc/passwd", stat.S_IFLNK | 0o777),
        ]
    )
    r = engine.scan_bytes(data, "Good.zip")
    got = {h.id: [e.file for e in h.evidence] for h in r.findings}
    assert r.severity == "critical"
    assert set(got["PKG_EXECUTABLE"]) == {"Good/Install.exe", "Good/readme.txt.scr"}
    assert "../../Startup/evil.lua" in got["PKG_PATH_TRAVERSAL"] and "Good/link" in got["PKG_PATH_TRAVERSAL"]
    assert got["PKG_NESTED_ARCHIVE"] == ["Good/extra.zip"] and got["PKG_SCRIPT"] == ["Good/build.sh"]


def test_encrypted_member_is_reported_not_crashed():
    data = bytearray(make_zip([("A/A.toc", "## Interface: 16001\nA.lua\n"), ("A/A.lua", "print(1)")]))
    # set the "encrypted" flag on every local and central header
    for sig in (b"PK\x03\x04", b"PK\x01\x02"):
        pos = data.find(sig)
        while pos != -1:
            off = pos + (6 if sig == b"PK\x03\x04" else 8)
            data[off] |= 1
            pos = data.find(sig, pos + 4)
    r = engine.scan_bytes(bytes(data))
    assert "PKG_ENCRYPTED" in ids(r)


def test_zip_bomb_and_garbage():
    bomb = make_zip([("A/big.lua", "a" * (12 * 1024 * 1024))])
    with pytest.raises(engine.ScanError, match="zip bomb"):
        engine.scan_bytes(bomb)
    with pytest.raises(engine.ScanError, match="not a valid zip"):
        engine.scan_bytes(b"not a zip")


def test_folder_mode_skips_pkgmeta_ignores(tmp_path):
    (tmp_path / "A").mkdir()
    (tmp_path / "A" / "A.toc").write_text("## Interface: 16001\nA.lua\n")
    (tmp_path / "A" / "A.lua").write_text("print(1)")
    (tmp_path / "A" / "tools").mkdir()
    (tmp_path / "A" / "tools" / "convert.exe").write_bytes(b"MZ")
    (tmp_path / "A" / ".pkgmeta").write_text("package-as: A\nignore:\n  - tools\n  - README.md\n")
    assert engine.scan_path(tmp_path / "A").severity == "info"
    (tmp_path / "A" / ".pkgmeta").write_text("package-as: A\n")
    assert engine.scan_path(tmp_path / "A").severity == "critical"


# ---------------------------------------------------------------- cli


def test_cli_json_and_exit_codes(capsys):
    assert cli.main([str(FIX / "Backdoor"), "-f", "json", "--lang", "en"]) == 1
    d = json.loads(capsys.readouterr().out)
    assert d["verdict"] == {"level": "critical", "text": "Dangerous"}
    assert d["findings"][0]["id"] == "REMOTE_CODE" and d["findings"][0]["severity_text"] == "critical"
    assert cli.main([str(FIX / "Clean"), "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "SIN SEÑALES DE RIESGO" in out and "No puede probar que un addon sea seguro" in out
    assert cli.main([str(FIX / "Profiler"), "--fail-on", "medium", "--no-color"]) == 1


def test_spanish_and_english_texts_exist_for_every_rule():
    from addon_sentry import rules

    for rid, r in rules.FINDINGS.items():
        assert r["severity"] in rules.SEVERITIES, rid
        for lang in ("es", "en"):
            title, explanation = r[lang]
            assert title and explanation.endswith((".", ")")), (rid, lang)


def test_locals_inside_a_callback_argument_are_local():
    # Regression: locals declared in a function passed to a call were taken for globals.
    from addon_sentry.lua import scan

    src = "C_Timer.After(1, function()\n  if x then\n    local SendMail = print\n    SendMail('a')\n  end\nend)\n"
    # SendMail is local; calling it calls what it stands for (print), not the global SendMail
    assert [r.name for r in scan("a.lua", src).refs] == ["C_Timer.After", "x", "print", "print"]


def test_local_table_then_function_on_the_next_line():
    from addon_sentry.lua import scan

    src = "local SendMail = {}\nfunction ns.On(t)\n  SendMail[t] = 1\nend\n"
    assert [r.name for r in scan("a.lua", src).refs] == ["ns"]


def test_calls_through_a_local_alias_count():
    # Details does "local load = loadstring" and calls load(code) later.
    from addon_sentry.lua import scan

    src = "local load = loadstring\nlocal C = C_TradeInfo\nfunction f(s)\n  load(s)()\n  C.SetTradeMoney(1)\nend\nlocal p = print\np = nil\np()\n"
    refs = [(r.name, r.is_call, r.alias) for r in scan("a.lua", src).refs]
    assert ("loadstring", True, True) in refs and ("C_TradeInfo.SetTradeMoney", True, True) in refs
    assert ("print", True, True) not in refs  # reassigned: no longer the global
    src = "local A, B = SendMail, GetMoney\nA(B())\n"
    assert [(r.name, r.alias) for r in scan("a.lua", src).refs][-2:] == [("SendMail", True), ("GetMoney", True)]
