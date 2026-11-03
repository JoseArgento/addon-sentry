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
- **Paridad:** `tests/test_parity.py` corre el motor de Python y el de JavaScript sobre los mismos zips, incluidos los 8 addons reales (más de 200 mil líneas de Lua), y exige reportes idénticos en los dos idiomas.

## Límites

Es un chequeo automático de patrones. No prueba que un addon sea seguro y una advertencia no prueba mala intención. No sigue los datos entre archivos: si un archivo escucha mensajes y otro ejecuta código, lo marca como "bajo" y lo explica. En el navegador, los zips ZIP64 o con compresión distinta de deflate piden usar la CLI.

## Desarrollo

```bash
pytest                                  # unitarios + paridad (necesita Node 18+)
ADDON_SENTRY_REAL_ADDONS=../addons pytest tests/test_parity.py   # paridad sobre addons reales
python tools/export_rules.py            # después de tocar rules.py
python tools/build_web.py               # arma dist/index.html
```

Sin relación con Blizzard Entertainment. World of Warcraft es marca registrada de Blizzard Entertainment, Inc. Licencia MIT.
