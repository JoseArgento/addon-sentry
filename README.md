# Addon Sentry

Revisá un addon de World of Warcraft **antes de instalarlo**. Lee el código Lua sin ejecutarlo y avisa si encuentra puertas traseras, trucos para mover tu oro, código escondido o archivos que no deberían estar ahí.

[Read in English](README.en.md)

```
$ addon-sentry FastBuyer.zip
addon-sentry 0.1.0 · FastBuyer.zip

 PELIGROSO

Qué puede hacer
  • Mueve oro u objetos (correo, comercio, casa de subastas, ...)

Señales
  CRÍTICO Mueve oro u objetos y lo esconde
    AuctionScam/Scam.lua:2  C_AuctionHouse.ConfirmCommoditiesPurchase = function(itemID, quantity)
```

Hay dos formas de usarlo, con el mismo motor:
- **La página web** (`dist/index.html`, un solo archivo): soltás el zip y se analiza en el navegador, sin subir nada.
- **La línea de comandos**: `pip install addon-sentry`, y después `addon-sentry archivo.zip` o `addon-sentry carpeta/`. Tiene opciones `--lang es|en`, `--format json` y `--fail-on high`.

## Auras de WeakAuras

Un aura es código que alguien te pasa como texto (`!WA:2!...`), y es una vía de estafa conocida. Addon Sentry lo lee **sin importarlo**: pegás el string en la página, o en la terminal:

```
addon-sentry --aura aura.txt        # o: pbpaste | addon-sentry --aura -
```

- Decodifica los tres formatos que importa WeakAuras: el actual (`!WA:2!`, LibDeflate + LibSerialize), el de 2019-2020 (`!`, LibDeflate + AceSerializer) y el anterior a 2018 (sin `!`, LibCompress + AceSerializer). Los decodificadores están escritos de nuevo a partir de esas librerías; nada se ejecuta.
- Revisa cada campo que WeakAuras convierte en función (disparadores, textos, acciones, animaciones, condiciones, grupos dinámicos), y además cualquier campo con nombre de código que parezca Lua, por si una versión nueva agrega uno.
- Las acciones de chat sin código (por ejemplo un susurro automático a un nombre fijo) cuentan como "manda mensajes".
- Señal propia: **usa cosas que WeakAuras bloquea** (`SendMail`, `SetTradeMoney`, `RunScript`, `getfenv`, `DEFAULT_CHAT_FRAME`, ... la lista de `AuraEnvironment.lua`). WeakAuras ya las anula, pero un aura normal no las necesita.
- Avisa si el string es de Plater, ElvUI o MDT: esos todavía no los lee.

## Qué busca

Separa lo que un addon **puede hacer** de las **señales de riesgo**. Muchos addons legítimos mueven oro (los de correo), mandan mensajes (los de raid) o ejecutan código del usuario (WeakAuras). Eso aparece en "Qué puede hacer" y no sube el veredicto.

| Veredicto | Cuándo |
|---|---|
| **Peligroso** | Ejecuta código que mandan otros jugadores (`CHAT_MSG_ADDON` + `loadstring`); código ofuscado que se ejecuta; mueve oro y reemplaza funciones de Blizzard para mentir sobre precios u oro; ejecutables; rutas que escapan de la carpeta (*zip slip*). |
| **Sospechoso** | Reemplaza funciones sensibles de Blizzard; arma de a pedazos nombres como `"Send".."Mail"`, `("liaMdneS"):reverse()` o `string.char(...)`; puede disolver la guild. |
| **Revisar** | Código ofuscado; mueve oro y además filtra el chat o acepta ventanas solo; junta estadísticas de otros jugadores y las guarda; archivos con contraseña o comprimidos adentro. |

Detalles que evitan falsos positivos:
- Solo cuenta el código que el juego **carga**, es decir, lo que listan los `.toc` y `.xml`, incluidos los scripts dentro de los XML.
- Distingue locales de funciones de Blizzard.
- Reconoce los polyfills y las plantillas de código, como el `loadstring` de CallbackHandler.
- En una carpeta de código fuente respeta el `ignore:` de `.pkgmeta`.
- **No respeta** comentarios de "ignorar" dentro del código que analiza, porque un autor malicioso los usaría.

## Cómo se probó

- **Calibración:** Questie, Details!, Bartender4, BigWigs, Deadly Boss Mods, ElvUI, WeakAuras y Plater dan "Sin señales de riesgo". En la carpeta de desarrollo de Questie aparece el `.exe` que tiene en `ExternalScripts(DONOTINCLUDEINRELEASE)`, que no va en la descarga.
- **Detección:** 8 addons de prueba con los patrones reales dan el veredicto esperado: puerta trasera por mensajes de addon, puerta trasera escondida en un `<OnEvent>` del XML, estafa de subasta, cargador ofuscado, nombres armados, disolver la guild, perfilador y addon limpio.
- **Paridad:** `tests/test_parity.py` corre el motor de Python y el de JavaScript sobre los mismos zips, incluidos los 8 addons reales (más de 200 mil líneas de Lua), y exige reportes idénticos en los dos idiomas. También sobre strings de auras, rotos incluidos.
- **Auras:** los strings de prueba los generan las librerías reales en Lua 5.1 (`tools/make_aura_fixtures.py`, con [lupa](https://pypi.org/project/lupa/)), y un test compara tabla por tabla lo que decodifica Addon Sentry con lo que decodifican LibDeflate, LibSerialize, AceSerializer y LibCompress. Se probó también con 135 strings públicos de un pack de UI viejo (2.024 auras, formato anterior a 2018): todos decodifican igual que con las librerías reales y dan "Sin señales de riesgo".

## Límites

Es un chequeo automático de patrones. No prueba que un addon sea seguro y una advertencia no prueba mala intención. En auras, todavía no se probó con strings actuales (`!WA:2!`) bajados de Wago: solo con los generados por las librerías reales. No sigue los datos entre archivos: si un archivo escucha mensajes y otro ejecuta código, lo marca como "bajo" y lo explica. En el navegador, los zips ZIP64 o con compresión distinta de deflate piden usar la CLI.

## Desarrollo

```bash
pytest                                  # unitarios + paridad (necesita Node 18+)
ADDON_SENTRY_REAL_ADDONS=../addons pytest tests/test_parity.py   # paridad sobre addons reales
ADDON_SENTRY_LUA_LIBS=../libs pytest tests/test_auras.py          # decodificador vs. las librerías en Lua (pip install lupa)
ADDON_SENTRY_REAL_AURAS=../strings pytest                         # carpeta con strings .txt reales
python tools/export_rules.py            # después de tocar rules.py
python tools/build_web.py               # arma dist/index.html
```

Sin relación con Blizzard Entertainment. World of Warcraft es marca registrada de Blizzard Entertainment, Inc. Licencia MIT.
