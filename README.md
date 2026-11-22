# FireDownload 1.0.0

Gestor de descargas de vídeo y audio basado en **yt-dlp**, con interfaz **PySide6**
(tema oscuro con acento azul Arch). Linux, Windows y macOS.

## Características

- **Descargas**: cola con concurrencia, pausa/reanudación reales del proceso, cancelar, reintentar,
  varias URLs a la vez, arrastrar y soltar, importar lista `.txt`, vigilar el portapapeles (opcional).
- **Buscador** integrado (YouTube y SoundCloud) con miniaturas.
- **Visor de metadatos**: miniatura, autor, duración, fecha, visitas, capítulos, descripción y
  calidades disponibles. Incluye **vista previa** reproducible dentro de la app.
- **Pistas de audio**: elige una o varias (varias → `.mkv` con todas las pistas).
- **Subtítulos**: archivos `.srt`, incrustados, o solo subtítulos; manuales y automáticos.
- Metadatos y carátula incrustados, límite de velocidad, proxy, cookies del navegador,
  plantillas de nombre de archivo, actualización de yt-dlp desde Ajustes.
- **Cola persistente**: lo que no terminó al cerrar reaparece como «pendiente» y se reanuda con un clic.
- **Playlists**: aviso al pegar una playlist y selección de elementos concretos.
- **Diagnóstico**: «Comprobar instalación» (entorno + yt-dlp verbose + descarga real mínima), copiar el detalle de un error, visor del registro, instancia única.
- **Estado visible**: cada descarga muestra qué está haciendo (obteniendo información, uniendo, extrayendo audio…).
- **Menú y atajos**: Ctrl+O importar lista, Ctrl+Shift+V pegar y añadir, Ctrl+P pausar todo,
  Ctrl+R reanudar todo, Ctrl+L quitar terminadas, Ctrl+1…4 pestañas, Ctrl+F buscar, F1 «Acerca de».
- **Barra de estado** con la velocidad total, aviso de poco espacio en disco y memoria del
  tamaño de ventana y de la última pestaña.
- **Acerca de**: versión, sección sobre el autor con web y GitHub, componentes instalados (yt-dlp, FFmpeg, JavaScript…), créditos
  y aviso legal, con botón para copiar la información al reportar un problema.
- **Historial** con filtro, reproducir con el reproductor del sistema, abrir carpeta, descargar de nuevo.

## Logo

Copia tu `Logo.png` en `assets/Logo.png` (o junto a `main.py`). Se usa en la cabecera y como
icono de la ventana. Sin él, la app funciona igual y solo muestra el texto.

## Requisitos

- Python 3.10+
- **Deno** (recomendado) o Node 20+ (se ignora Node más antiguo): desde noviembre de 2025 yt-dlp lo necesita para YouTube
  (junto con el componente `yt-dlp-ejs`, que instala `yt-dlp[default]`). Sin él faltan formatos
  o aparece «video not available». La app lo detecta y avisa en la barra de estado.
- [FFmpeg](https://ffmpeg.org/) en el PATH (opcional; necesario para audio, unión de vídeo+audio,
  conversión/incrustado de subtítulos y metadatos)

## Instalación y uso

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                   # o: python -m firedownload
```

## Datos de usuario

| SO      | Carpeta                                       |
|---------|-----------------------------------------------|
| Linux   | `~/.config/firedownload/`                     |
| Windows | `%APPDATA%\FireDownload\`                     |
| macOS   | `~/Library/Application Support/FireDownload/` |

Contiene `config.json`, `history.json`, `logs/app.log` y `cache/` (miniaturas).

## Estructura

```
main.py, build_zip.py, requirements.txt, assets/Logo.png
firedownload/
  app.py  config.py
  core/  utils  ytdlp  info  tasks  thumbs  sounds  history  queue_store  worker  manager
  ui/    theme  main_window  about_dialog  check_dialog  download_tab  search_tab  info_dialog  preview_dialog
         history_tab  settings_tab  log_dialog
tests/                   pytest (args, info, config, worker, manager, ui)
```

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

Usan un yt-dlp falso (`tests/fake_ytdlp.py`) y Qt en modo offscreen; no necesitan red.

## Generar el .zip

```bash
python build_zip.py
```

## Autor y enlaces

Creado por **Dragoland** · [bitcriollo.pages.dev](https://bitcriollo.pages.dev) ·
[github.com/Dragoland/firedownload](https://github.com/Dragoland/firedownload)

Los datos de «Acerca de» salen de `firedownload/__init__.py` (`__author__`, `__contact__`,
`__github__`, `__site_web__`, `__copyright__`); el texto de la sección «Sobre el autor» está
en `firedownload/ui/about_dialog.py`.
