"""What the scanner looks for, and how it explains it (English and Spanish).

Capabilities are things an addon *can* do; many legitimate addons need them (a
mail addon sends mail). Risk comes from combinations and from hiding: code that
moves gold and also hides the confirmation, code that runs text received from
other players, obfuscated code that builds and runs more code.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- capabilities (API groups)

CAPABILITIES: dict[str, dict] = {
    "money": {
        "api": {
            # mail
            "SendMail",
            "SetSendMailMoney",
            "SetSendMailCOD",
            "ClickSendMailItemButton",
            "TakeInboxMoney",
            "TakeInboxItem",
            "AutoLootMailItem",
            "ReturnInboxItem",
            # trade
            "InitiateTrade",
            "AcceptTrade",
            "SetTradeMoney",
            "ClickTradeButton",
            "ClickTargetTradeButton",
            "DropItemOnUnit",
            "PickupPlayerMoney",
            "AddTradeMoney",
            # auction house (classic and modern)
            "PlaceAuctionBid",
            "PostAuction",
            "StartAuction",
            "C_AuctionHouse.PlaceBid",
            "C_AuctionHouse.StartCommoditiesPurchase",
            "C_AuctionHouse.ConfirmCommoditiesPurchase",
            "C_AuctionHouse.PostItem",
            "C_AuctionHouse.PostCommodity",
            "C_AuctionHouse.CancelAuction",
            "CancelAuction",
            "C_BlackMarket.ItemPlaceBid",
            # guild bank, merchants, destroying
            "WithdrawGuildBankMoney",
            "DepositGuildBankMoney",
            "PickupGuildBankItem",
            "AutoStoreGuildBankItem",
            "SplitGuildBankItem",
            "BuyMerchantItem",
            "BuybackItem",
            "DeleteCursorItem",
            "C_Container.UseContainerItem",
        },
        "en": "Moves gold or items (mail, trade, auction house, guild bank, vendors, deleting items)",
        "es": "Mueve oro u objetos (correo, comercio, casa de subastas, banco de la guild, vendedores, borrar objetos)",
    },
    "chat": {
        "api": {
            "SendChatMessage",
            "C_ChatInfo.SendChatMessage",
            "C_ChatInfo.SendAddonMessage",
            "C_ChatInfo.SendAddonMessageLogged",
            "SendAddonMessage",
            "BNSendWhisper",
            "C_BattleNet.SendWhisper",
            "BNSendGameData",
            "C_BattleNet.SendGameData",
            "JoinChannelByName",
            "JoinPermanentChannel",
            "JoinTemporaryChannel",
            "C_ChatInfo.RegisterAddonMessagePrefix",
        },
        "en": "Sends chat, whispers or hidden addon messages",
        "es": "Manda mensajes de chat, susurros o mensajes ocultos de addon",
    },
    "code": {
        "api": {"loadstring", "load", "RunScript", "setfenv", "getfenv", "setmetatable(_G"},
        "en": "Builds and runs code at runtime",
        "es": "Arma y ejecuta código mientras corre",
    },
    "account": {
        "api": {
            "BNGetInfo",
            "C_BattleNet.GetAccountInfoByID",
            "C_BattleNet.GetAccountInfoByGUID",
            "C_BattleNet.GetFriendAccountInfo",
            "BNGetNumFriends",
            "BNGetFriendInfo",
            "C_FriendList.GetFriendInfoByIndex",
            "C_FriendList.GetNumFriends",
            "GetGuildRosterInfo",
            "GetMoney",
            "GetGuildBankMoney",
        },
        "en": "Reads account data (BattleTag, friends list, guild roster, gold)",
        "es": "Lee datos de la cuenta (BattleTag, lista de amigos, roster de la guild, oro)",
    },
    "sabotage": {
        "api": {
            "GuildDisband",
            "GuildUninvite",
            "C_GuildInfo.RemoveFromGuild",
            "GuildSetLeader",
            "GuildDemote",
            "C_GuildInfo.Demote",
            "GuildLeave",
            "C_GuildInfo.Leave",
            "Logout",
            "Quit",
            "ForceQuit",
            "LeaveParty",
            "C_PartyInfo.LeaveParty",
            "AbandonQuest",
            "C_QuestLog.AbandonQuest",
            "AbandonSkill",
        },
        "en": "Can disband or kick from the guild, log out, leave the group, abandon a pet or abandon progress",
        "es": "Puede disolver la guild o echar gente, desconectarte, salir del grupo, abandonar una mascota o abandonar progreso",
    },
    "profiling": {
        "api": {
            "SetAchievementComparisonUnit",
            "GetComparisonStatistic",
            "GetComparisonAchievementPoints",
            "GetComparisonCategoryNumAchievements",
            "NotifyInspect",
            "C_PaperDollInfo.GetInspectItemLevel",
            "GetInspectHonorData",
            "GetPlayerInfoByGUID",
        },
        "en": "Inspects other players or reads their statistics",
        "es": "Inspecciona a otros jugadores o lee sus estadísticas",
    },
    "frames": {
        "api": {"GetFrameMetatable", "GetButtonMetatable", "GetEditBoxMetatable", "GetFontStringMetatable", "EnumerateFrames"},
        "en": "Walks through or changes every window of the interface (common in skins)",
        "es": "Recorre o modifica todas las ventanas de la interfaz (común en los skins)",
    },
    "macros": {
        "api": {
            "CreateMacro",
            "EditMacro",
            "DeleteMacro",
            "SetBinding",
            "SetBindingClick",
            "SetBindingMacro",
            "SetBindingSpell",
            "SetBindingItem",
            "SaveBindings",
            "SetOverrideBinding",
            "SetOverrideBindingClick",
        },
        "en": "Creates or edits macros and key bindings",
        "es": "Crea o modifica macros y atajos de teclado",
    },
}

API_CAPABILITY = {api: cap for cap, info in CAPABILITIES.items() for api in info["api"]}

# Blizzard functions whose replacement would let an addon lie about money, purchases or confirmations.
SENSITIVE_HOOK_TARGETS = {
    "StaticPopup_Show",
    "StaticPopup_OnClick",
    "StaticPopup_Hide",
    "StaticPopup_Visible",
    "GetMoney",
    "GetCoinTextureString",
    "GetMoneyString",
    "MoneyFrame_Update",
    "SetMoneyFrameColor",
    "PlaceAuctionBid",
    "SendMail",
    "AcceptTrade",
    "SetTradeMoney",
    "InitiateTrade",
    "C_AuctionHouse.PlaceBid",
    "C_AuctionHouse.StartCommoditiesPurchase",
    "C_AuctionHouse.ConfirmCommoditiesPurchase",
    "ChatFrame_OnHyperlinkShow",
    "SetItemRef",
    "GetAuctionItemInfo",
    "C_AuctionHouse.GetCommoditySearchResultInfo",
    "C_AuctionHouse.GetItemSearchResultInfo",
    "BuyMerchantItem",
    "SendChatMessage",
    "C_ChatInfo.SendChatMessage",
}

# Blizzard windows that confirm money or item movement. Matched as prefixes, so child buttons
# (StaticPopup1Button1, TradeFrameTradeButton, ...) count too.
SENSITIVE_FRAME_PREFIXES = (
    "StaticPopup1",
    "StaticPopup2",
    "StaticPopup3",
    "StaticPopup4",
    "TradeFrame",
    "SendMailFrame",
    "SendMailMailButton",
    "MailFrame",
    "OpenMailFrame",
    "InboxFrame",
    "AuctionHouseFrame",
    "AuctionFrame",
    "GuildBankFrame",
    "MerchantFrame",
)

# Chat events whose filtering can hide what happened to your gold or messages.
HIDING_FILTER_EVENTS = {
    "CHAT_MSG_SYSTEM",
    "CHAT_MSG_MONEY",
    "CHAT_MSG_LOOT",
    "CHAT_MSG_WHISPER",
    "CHAT_MSG_WHISPER_INFORM",
    "CHAT_MSG_BN_WHISPER",
    "CHAT_MSG_BN_WHISPER_INFORM",
    "CHAT_MSG_TRADESKILLS",
    "CHAT_MSG_CURRENCY",
}

# Events that deliver text written by other players.
REMOTE_INPUT_EVENTS = {
    "CHAT_MSG_ADDON",
    "CHAT_MSG_ADDON_LOGGED",
    "CHAT_MSG_WHISPER",
    "CHAT_MSG_BN_WHISPER",
    "CHAT_MSG_CHANNEL",
    "CHAT_MSG_GUILD",
    "CHAT_MSG_PARTY",
    "CHAT_MSG_PARTY_LEADER",
    "CHAT_MSG_RAID",
    "CHAT_MSG_RAID_LEADER",
    "CHAT_MSG_SAY",
    "CHAT_MSG_YELL",
    "CHAT_MSG_OFFICER",
    "CHAT_MSG_INSTANCE_CHAT",
    "BN_CHAT_MSG_ADDON",
}

# Files the game never loads from an addon. In an addon download they are a red flag.
EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".dll",
    ".scr",
    ".com",
    ".bat",
    ".cmd",
    ".ps1",
    ".psm1",
    ".vbs",
    ".vbe",
    ".js",
    ".jse",
    ".wsf",
    ".wsh",
    ".hta",
    ".msi",
    ".msp",
    ".lnk",
    ".jar",
    ".reg",
    ".cpl",
    ".sys",
    ".app",
    ".dmg",
    ".pkg",
}
# Developer scripts: common in source repos, harmless unless you run them yourself.
SCRIPT_EXTENSIONS = {".sh", ".command", ".py", ".pl", ".rb", ".so", ".dylib"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".xz", ".bz2", ".cab", ".iso"}
ADDON_EXTENSIONS = {
    ".lua",
    ".xml",
    ".toc",
    ".tga",
    ".blp",
    ".png",
    ".jpg",
    ".jpeg",
    ".ttf",
    ".otf",
    ".ogg",
    ".mp3",
    ".wav",
    ".m2",
    ".txt",
    ".md",
    ".html",
    ".htm",
    ".json",
    ".yml",
    ".yaml",
    ".pkgmeta",
    ".gitignore",
    ".editorconfig",
    ".luacheckrc",
    ".csv",
    ".bmp",
    ".gif",
    ".svg",
    ".license",
    ".gitattributes",
    ".gitmodules",
    ".luarc",
    ".code-workspace",
}

# --------------------------------------------------------------------------- findings

SEVERITIES = ["info", "low", "medium", "high", "critical"]
SEVERITY_NAMES = {
    "en": {"info": "info", "low": "low", "medium": "medium", "high": "high", "critical": "critical"},
    "es": {"info": "info", "low": "bajo", "medium": "medio", "high": "alto", "critical": "crítico"},
}

# What WeakAuras blocks inside aura code (WeakAuras/AuraEnvironment.lua: blockedFunctions,
# blockedNamespaceFunctions, blockedTables). The aura gets an empty stand-in and the player a warning.
AURA_BLOCKED: frozenset[str] = frozenset(
    {
        "getfenv",
        "setfenv",
        "loadstring",
        "pcall",
        "xpcall",
        "SendMail",
        "SetTradeMoney",
        "AddTradeMoney",
        "PickupTradeMoney",
        "PickupPlayerMoney",
        "TradeFrame",
        "MailFrame",
        "EnumerateFrames",
        "RunScript",
        "AcceptTrade",
        "SetSendMailMoney",
        "DevTools_DumpCommand",
        "hash_SlashCmdList",
        "RegisterNewSlashCommand",
        "CreateMacro",
        "EditMacro",
        "DeleteMacro",
        "SetBindingMacro",
        "GuildDisband",
        "GuildUninvite",
        "securecall",
        "DeleteCursorItem",
        "AbandonSkill",
        "PetAbandon",
        "ChatEdit_SendText",
        "ChatEdit_ActivateChat",
        "ChatEdit_ParseText",
        "ChatEdit_OnEnterPressed",
        "GetButtonMetatable",
        "GetEditBoxMetatable",
        "GetFontStringMetatable",
        "GetFrameMetatable",
        "C_PetInfo.PetAbandon",
        "C_GuildInfo.Disband",
        "C_GuildInfo.Uninvite",
        "C_TradeInfo.AddTradeMoney",
        "C_TradeInfo.SetTradeMoney",
        "C_TradeInfo.PickupTradeMoney",
        "SlashCmdList",
        "SendMailMailButton",
        "SendMailMoneyGold",
        "MailFrameTab2",
        "DEFAULT_CHAT_FRAME",
        "ChatFrame1",
        "WeakAurasSaved",
        "WeakAurasOptions",
        "WeakAurasOptionsSaved",
        "ItemRackUser",
        "ItemRackEvents",
    }
)

FINDINGS: dict[str, dict] = {
    # package
    "PKG_EXECUTABLE": {
        "severity": "critical",
        "en": (
            "Executable file in the addon",
            "WoW never runs files like this from an addon. A download that asks you to run one is almost always malware.",
        ),
        "es": (
            "Archivo ejecutable dentro del addon",
            "WoW nunca ejecuta archivos así desde un addon. Si una descarga te pide abrir uno, casi siempre es malware.",
        ),
    },
    "PKG_PATH_TRAVERSAL": {
        "severity": "critical",
        "en": (
            "File path escapes the addon folder",
            'Unzipping this would write files outside the folder ("zip slip"), for example into your startup folder.',
        ),
        "es": (
            "Ruta que sale de la carpeta del addon",
            'Al descomprimirlo escribiría archivos fuera de la carpeta ("zip slip"), por ejemplo en el inicio de Windows.',
        ),
    },
    "PKG_SCRIPT": {
        "severity": "low",
        "en": (
            "Developer script in the addon",
            "Build or tooling scripts are common in source repositories. The game never runs them; do not run them yourself unless you know what they do.",
        ),
        "es": (
            "Script de desarrollo dentro del addon",
            "Los scripts de build o herramientas son comunes en los repos. El juego nunca los ejecuta; no los ejecutes vos salvo que sepas qué hacen.",
        ),
    },
    "PKG_ENCRYPTED": {
        "severity": "medium",
        "en": ("Password-protected files", "The scanner cannot see inside them, and addons have no reason to ship encrypted files."),
        "es": (
            "Archivos con contraseña",
            "El escáner no puede ver qué tienen, y un addon no tiene motivo para traer archivos encriptados.",
        ),
    },
    "PKG_NESTED_ARCHIVE": {
        "severity": "medium",
        "en": (
            "Archive inside the archive",
            "The scanner cannot see inside it. Addons do not need nested archives; check where it came from.",
        ),
        "es": (
            "Archivo comprimido adentro del comprimido",
            "El escáner no puede ver qué tiene. Los addons no necesitan comprimidos adentro; fijate de dónde salió.",
        ),
    },
    "PKG_UNUSUAL_FILE": {
        "severity": "low",
        "en": ("File type the game does not use", "Not dangerous by itself, but unusual in an addon."),
        "es": ("Tipo de archivo que el juego no usa", "No es peligroso por sí solo, pero es raro en un addon."),
    },
    "PKG_NO_TOC": {
        "severity": "low",
        "en": ("No .toc file", "Without a .toc the game does not load it, so this is not a working addon as packaged."),
        "es": ("No hay archivo .toc", "Sin .toc el juego no lo carga: así como viene no es un addon que funcione."),
    },
    "PKG_UNLOADED_LUA": {
        "severity": "info",
        "en": ("Lua file not loaded by any .toc", "The game will not run it unless another file loads it."),
        "es": ("Archivo Lua que ningún .toc carga", "El juego no lo ejecuta, salvo que otro archivo lo cargue."),
    },
    # code
    "REMOTE_CODE": {
        "severity": "critical",
        "en": (
            "Can run code sent by other players",
            "It listens to chat or addon messages and also builds and runs code. Whoever sends the right message could run anything as you: trade away your gold, send mail, whisper scams to your friends.",
        ),
        "es": (
            "Puede ejecutar código que manden otros jugadores",
            "Escucha mensajes de chat o de addons y además arma y ejecuta código. Quien mande el mensaje justo podría hacer cualquier cosa en tu nombre: comerciar tu oro, mandar correo, susurrar estafas a tus amigos.",
        ),
    },
    "OBFUSCATED_LOADER": {
        "severity": "critical",
        "en": (
            "Hidden code that runs more code",
            "Part of the code is encoded so people cannot read it, and it is decoded and run. Legitimate addons have no reason to do this, and Blizzard's add-on policy forbids hidden code.",
        ),
        "es": (
            "Código escondido que ejecuta más código",
            "Una parte del código está codificada para que no se pueda leer, y se decodifica y ejecuta. Un addon legítimo no tiene motivo para hacer esto, y la política de addons de Blizzard prohíbe esconder código.",
        ),
    },
    "HIDDEN_MONEY": {
        "severity": "critical",
        "en": (
            "Moves gold or items and hides it",
            "It can move gold or items and also hides confirmations or chat notices about it. This is the pattern of the auction house scams.",
        ),
        "es": (
            "Mueve oro u objetos y lo esconde",
            "Puede mover oro u objetos y además esconde las confirmaciones o los avisos del chat. Es el patrón de las estafas de la casa de subastas.",
        ),
    },
    "BLIZZARD_OVERRIDE_SENSITIVE": {
        "severity": "high",
        "en": (
            "Replaces a Blizzard function about money or confirmations",
            "Replacing this function lets an addon show you something different from what really happens (a price, your gold, a confirmation).",
        ),
        "es": (
            "Reemplaza una función de Blizzard de plata o confirmaciones",
            "Reemplazar esta función permite mostrarte algo distinto de lo que pasa en realidad (un precio, tu oro, una confirmación).",
        ),
    },
    "SENSITIVE_FRAME": {
        "severity": "low",
        "en": (
            "Changes or clicks a money confirmation window",
            "It changes the behaviour of, or clicks, a window that confirms gold or item movement. Convenience addons do this too (auto-accept); combined with hiding it is a scam pattern.",
        ),
        "es": (
            "Modifica o aprieta una ventana que confirma plata",
            "Cambia el comportamiento de una ventana que confirma movimientos de oro u objetos, o la aprieta sola. Los addons de comodidad también lo hacen (aceptar automático); junto con esconder cosas es un patrón de estafa.",
        ),
    },
    "MONEY_AND_HIDING": {
        "severity": "medium",
        "en": (
            "Moves gold or items and also filters chat or confirms windows",
            "Convenience addons do both (auto-sell junk, hide spam, auto-accept). Check that the addon is what it says it is and where you downloaded it.",
        ),
        "es": (
            "Mueve oro u objetos y además filtra el chat o acepta ventanas solo",
            "Los addons de comodidad hacen las dos cosas (vender basura, esconder spam, aceptar solo). Fijate que el addon sea lo que dice y de dónde lo bajaste.",
        ),
    },
    "LISTENS_AND_RUNS": {
        "severity": "low",
        "en": (
            "Listens to other players and runs code built at runtime",
            "One file listens to chat or addon messages and another one runs code it builds at runtime. The scanner cannot follow the data between files, so check whether received text reaches the code runner.",
        ),
        "es": (
            "Escucha a otros jugadores y ejecuta código armado en el momento",
            "Un archivo escucha mensajes de chat o de addons y otro ejecuta código que arma en el momento. El escáner no puede seguir los datos entre archivos: hay que mirar si el texto recibido llega al que ejecuta.",
        ),
    },
    "HIDING_FILTER": {
        "severity": "low",
        "en": (
            "Hides chat messages about gold, loot or whispers",
            "Chat filters are common (spam blockers), but filtering system, money or whisper messages can hide what an addon did.",
        ),
        "es": (
            "Esconde mensajes del chat sobre oro, botín o susurros",
            "Los filtros de chat son comunes (anti-spam), pero filtrar mensajes del sistema, de oro o susurros puede esconder lo que hizo un addon.",
        ),
    },
    "SENSITIVE_HOOK": {
        "severity": "info",
        "en": (
            "Hooks a Blizzard function about money or chat",
            "A hook runs after Blizzard's function; it cannot change it, but it can react (for example hide a window right after it opens).",
        ),
        "es": (
            "Se engancha a una función de Blizzard de plata o chat",
            "El gancho corre después de la función de Blizzard: no la cambia, pero puede reaccionar (por ejemplo cerrar una ventana apenas se abre).",
        ),
    },
    "EXFILTRATION": {
        "severity": "low",
        "en": (
            "Reads your friends list and sends messages",
            "It reads your Battle.net or in-game friends and can send hidden messages. Showing friends is normal for chat and social addons; sending them somewhere is not.",
        ),
        "es": (
            "Lee tu lista de amigos y manda mensajes",
            "Lee tus amigos de Battle.net o del juego y puede mandar mensajes ocultos. Mostrar amigos es normal en addons de chat y sociales; mandarlos a algún lado, no.",
        ),
    },
    "DYNAMIC_CODE": {
        "severity": "low",
        "en": (
            "Builds and runs code at runtime",
            "Normal for developer tools and import strings; otherwise worth a look. What matters is where the code comes from.",
        ),
        "es": (
            "Arma y ejecuta código mientras corre",
            "Es normal en herramientas para desarrolladores y en strings de importación; si no, conviene mirarlo. Lo importante es de dónde sale ese código.",
        ),
    },
    "INDIRECT_GLOBAL": {
        "severity": "low",
        "en": (
            "Calls functions by computed name",
            'It looks up game functions with a name built at runtime (e.g. _G["Send".."Mail"]), which hides what it calls from readers and scanners.',
        ),
        "es": (
            "Llama funciones con un nombre calculado",
            'Busca funciones del juego con un nombre armado en el momento (por ejemplo _G["Send".."Mail"]), lo que esconde qué llama.',
        ),
    },
    "BUILT_API_NAME": {
        "severity": "high",
        "en": (
            "Builds the name of a sensitive function piece by piece",
            "Splitting the name of a money or chat function into pieces only makes sense to avoid being noticed.",
        ),
        "es": (
            "Arma de a pedazos el nombre de una función sensible",
            "Partir en pedazos el nombre de una función de plata o chat solo tiene sentido para que no se note.",
        ),
    },
    "OBFUSCATION": {
        "severity": "medium",
        "en": (
            "Hard-to-read code",
            "Long encoded strings, character-code tricks or scrambled names. Compressed profile data is legitimate, but Blizzard's add-on policy (rule 2) says an addon's code must in no way be hidden or obfuscated.",
        ),
        "es": (
            "Código difícil de leer",
            "Strings codificados largos, trucos con códigos de caracteres o nombres revueltos. Los perfiles comprimidos son legítimos, pero la política de addons de Blizzard (regla 2) dice que el código de un addon no puede estar escondido ni ofuscado de ninguna forma.",
        ),
    },
    "SABOTAGE": {
        "severity": "low",
        "en": (
            "Can disband or kick from the guild, or log you out",
            "Guild tools legitimately kick and demote; other addons have no reason to.",
        ),
        "es": (
            "Puede disolver o echar gente de la guild, o desconectarte",
            "Las herramientas de guild echan y degradan gente legítimamente; otros addons no tienen por qué.",
        ),
    },
    "GUILD_DISBAND": {
        "severity": "high",
        "en": ("Can disband the guild", "Disbanding is a one-click, irreversible action that almost no addon needs."),
        "es": ("Puede disolver la guild", "Disolver es una acción irreversible que casi ningún addon necesita."),
    },
    "PROFILING": {
        "severity": "medium",
        "en": (
            "Collects statistics about other players and saves them",
            "It reads other players' statistics (such as gold earned) and the addon keeps saved data. Check what it stores about people and whether it shares it.",
        ),
        "es": (
            "Junta estadísticas de otros jugadores y las guarda",
            "Lee estadísticas de otros jugadores (como el oro ganado) y el addon guarda datos. Fijate qué guarda de la gente y si lo comparte.",
        ),
    },
    "MACRO_WRITE": {
        "severity": "low",
        "en": (
            "Creates or edits macros or key bindings",
            "Normal for action bar and macro addons. A macro can run any command when you press the key.",
        ),
        "es": (
            "Crea o modifica macros o atajos",
            "Es normal en addons de barras y macros. Una macro puede ejecutar cualquier comando cuando apretás la tecla.",
        ),
    },
    "AURA_BLOCKED": {
        "severity": "medium",
        "en": (
            "Uses something WeakAuras blocks",
            "WeakAuras does not let aura code use this: it hands the aura an empty stand-in and warns you. A normal aura has no need for it. Either the code is old, or it tries exactly what WeakAuras blocks to stop scams (mail, trade, guild, macros, chat, escaping its sandbox).",
        ),
        "es": (
            "Usa cosas que WeakAuras bloquea",
            "WeakAuras no deja que el código de un aura use esto: le da algo vacío en su lugar y te avisa. Un aura normal no lo necesita. O es código viejo, o intenta justo lo que WeakAuras bloquea para frenar estafas (correo, comercio, hermandad, macros, chat, salirse de su sandbox).",
        ),
    },
    "URL": {
        "severity": "info",
        "en": (
            "Contains links",
            "Most are the author's site or Discord. Do not paste links from an addon into your browser without checking them.",
        ),
        "es": (
            "Tiene links",
            "La mayoría son la web o el Discord del autor. No pegues en el navegador links que te muestre un addon sin revisarlos.",
        ),
    },
}

VERDICTS = {
    "critical": {"en": "Dangerous", "es": "Peligroso"},
    "high": {"en": "Suspicious", "es": "Sospechoso"},
    "medium": {"en": "Review", "es": "Revisar"},
    "low": {"en": "No warning signs", "es": "Sin señales de riesgo"},
    "info": {"en": "No warning signs", "es": "Sin señales de riesgo"},
}

DISCLAIMER = {
    "en": "This is an automatic check of the code's patterns. It cannot prove an addon is safe, and a warning is not proof of bad intent. When in doubt, download addons only from their official page.",
    "es": "Es un chequeo automático de patrones en el código. No puede probar que un addon sea seguro, y una advertencia no prueba mala intención. Ante la duda, bajá los addons solo de su página oficial.",
}

# --------------------------------------------------------------------------- does it load in Forever?

# Forever's game type is "camelot" (alias "forever") in the "mainline" family, so the client looks for
# <Addon>_Camelot.toc, then _Forever, _Mainline and the plain <Addon>.toc (warcraft.wiki.gg, "TOC format").
FOREVER_TOC_SUFFIXES = ["_Camelot", "_Forever", "_Mainline", ""]
# Per-flavor Interface keys win over the plain one, in the same order.
FOREVER_INTERFACE_KEYS = ["interface-camelot", "interface-forever", "interface-mainline", "interface"]
TOC_FLAVOR_SUFFIX = r"[_-](Mainline|Standard|Forever|Camelot|Vanilla|Classic|TBC|BCC|Wrath|WOTLKC|Cata|Mists)$"
FOREVER_INTERFACE_RANGE = (16000, 16999)  # 1.60.x; a patch bumps 16001 to 16002 and the addon is still a Forever build

# What an Interface number says about the build (first digits of the version). Informational only.
INTERFACE_FLAVORS = [
    (16000, 16999, {"es": "Forever", "en": "Forever"}),
    (11000, 11999, {"es": "Classic Era / Anniversary", "en": "Classic Era / Anniversary"}),
    (20000, 29999, {"es": "Burning Crusade Classic", "en": "Burning Crusade Classic"}),
    (30000, 39999, {"es": "Wrath Classic", "en": "Wrath Classic"}),
    (40000, 49999, {"es": "Cataclysm Classic", "en": "Cataclysm Classic"}),
    (50000, 59999, {"es": "Mists Classic", "en": "Mists Classic"}),
    (100000, 999999, {"es": "retail", "en": "retail"}),
]

# Short label and the explanation shown under it. Placeholders: {name}, {toc}, {tocs}, {interface}, {flavor}.
FOREVER_LOAD = {
    "loads": {
        "en": ("Loads in Forever", "{toc} declares Interface {interface}: it is a Forever build."),
        "es": ("Carga en Forever", "{toc} declara Interface {interface}: es una build para Forever."),
    },
    "outdated": {
        "en": (
            "Not a Forever build",
            "{toc} declares Interface {interface} ({flavor}). Forever marks it as out of date, and even if you load it anyway it will fail wherever it uses API that Forever does not have. Look for a file marked Forever on the addon's page.",
        ),
        "es": (
            "No es una build de Forever",
            "{toc} declara Interface {interface} ({flavor}). Forever lo marca como desactualizado y, aunque lo cargues igual, va a fallar donde use API que Forever no tiene. Buscá en la página del addon el archivo marcado para Forever.",
        ),
    },
    "no_toc": {
        "en": (
            "Forever will not list it",
            "No TOC that Forever reads: it looks for {name}_Camelot.toc, {name}_Forever.toc, {name}_Mainline.toc or {name}.toc, and the folder has {tocs}. If this is a GitHub zip, the folder must be named {rename}.",
        ),
        "es": (
            "Forever no lo va a listar",
            "No tiene un TOC que Forever lea: busca {name}_Camelot.toc, {name}_Forever.toc, {name}_Mainline.toc o {name}.toc, y la carpeta trae {tocs}. Si es un zip de GitHub, la carpeta se tiene que llamar {rename}.",
        ),
    },
    "excluded": {
        "en": (
            "Excludes Forever on purpose",
            "{toc} leaves Forever out with AllowLoadGameType/ExcludeLoadGameType, so it does not load there.",
        ),
        "es": (
            "Excluye a Forever a propósito",
            "{toc} deja afuera a Forever con AllowLoadGameType/ExcludeLoadGameType, así que ahí no carga.",
        ),
    },
    "unknown": {
        "en": ("No Interface version", "{toc} does not say which game version it is for. Forever will list it as out of date."),
        "es": ("Sin versión de interfaz", "{toc} no dice para qué versión del juego es. Forever lo va a listar como desactualizado."),
    },
    "none": {
        "en": ("No TOC at all", "There is no .toc file: the game cannot load this as an addon."),
        "es": ("Sin TOC", "No hay ningún archivo .toc: el juego no puede cargar esto como addon."),
    },
}

# Texts for the per-addon table when a zip or folder holds several addons (a whole AddOns folder).
AUDIT = {
    "en": {
        "title": "Several addons",
        "count": "{n} addons",
        "addon": "Addon",
        "version": "Version",
        "verdict": "Verdict",
        "forever": "Forever",
        "caps": "Can do",
        "none": "nothing sensitive",
        "loose": "(loose files)",
        "worst": "Worst of the set",
    },
    "es": {
        "title": "Varios addons",
        "count": "{n} addons",
        "addon": "Addon",
        "version": "Versión",
        "verdict": "Veredicto",
        "forever": "Forever",
        "caps": "Puede",
        "none": "nada sensible",
        "loose": "(archivos sueltos)",
        "worst": "El peor del conjunto",
    },
}

# One or two words per capability, for the table.
CAPABILITY_SHORT = {
    "money": {"es": "oro", "en": "gold"},
    "chat": {"es": "mensajes", "en": "messages"},
    "code": {"es": "código", "en": "code"},
    "account": {"es": "cuenta", "en": "account"},
    "sabotage": {"es": "sabotaje", "en": "sabotage"},
    "profiling": {"es": "perfilado", "en": "profiling"},
    "frames": {"es": "interfaz", "en": "UI"},
    "macros": {"es": "macros", "en": "macros"},
}


def export() -> dict:
    """Everything the JavaScript engine needs, so both engines share one source of truth."""
    from . import auras as _auras

    return {
        "capabilities": {k: {"api": sorted(v["api"]), "en": v["en"], "es": v["es"]} for k, v in CAPABILITIES.items()},
        "sensitive_hook_targets": sorted(SENSITIVE_HOOK_TARGETS),
        "sensitive_frame_prefixes": list(SENSITIVE_FRAME_PREFIXES),
        "hiding_filter_events": sorted(HIDING_FILTER_EVENTS),
        "remote_input_events": sorted(REMOTE_INPUT_EVENTS),
        "executable_extensions": sorted(EXECUTABLE_EXTENSIONS),
        "script_extensions": sorted(SCRIPT_EXTENSIONS),
        "archive_extensions": sorted(ARCHIVE_EXTENSIONS),
        "addon_extensions": sorted(ADDON_EXTENSIONS),
        "severities": SEVERITIES,
        "severity_names": SEVERITY_NAMES,
        "findings": FINDINGS,
        "verdicts": VERDICTS,
        "disclaimer": DISCLAIMER,
        "forever": {
            "toc_suffixes": FOREVER_TOC_SUFFIXES,
            "interface_keys": FOREVER_INTERFACE_KEYS,
            "interface_range": list(FOREVER_INTERFACE_RANGE),
            "flavor_suffix": TOC_FLAVOR_SUFFIX,
            "flavors": [[lo, hi, names] for lo, hi, names in INTERFACE_FLAVORS],
            "load": FOREVER_LOAD,
        },
        "audit": AUDIT,
        "capability_short": CAPABILITY_SHORT,
        "aura": {
            "blocked": sorted(AURA_BLOCKED),
            "code_keys": sorted(_auras.CODE_KEYS),
            "send_chat_types": sorted(_auras.SEND_CHAT_TYPES),
        },
    }
