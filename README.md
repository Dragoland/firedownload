# FireDownload 1.0.0

Gestor de descargas de vídeo y audio basado en **yt-dlp**, con interfaz **PySide6**
(tema oscuro con acento azul Arch). Linux, Windows y macOS. Licencia **MIT**.

## Características

- **Descargas**: cola con concurrencia, pausa real del proceso, cancelar, reintentar, reordenar
  (▲ ▼ Primero) y cola persistente entre sesiones.
- **Buscador** integrado (YouTube y SoundCloud) con miniaturas.
- **Visor de metadatos** con vista previa, pistas de audio, subtítulos, selección de elementos de
  playlist y **recorte** por rango de tiempo o por capítulos.
- **Perfiles**: «Música · MP3», «Vídeo 1080p», «Solo subtítulos»… y los tuyos.
- **SponsorBlock** (marcar o eliminar patrocinios), **archivo de descargas** (no repetir vídeos),
  política de archivos existentes, cookies desde navegador o `cookies.txt`, proxy y límite de velocidad.
- **Se instala solo lo que necesita**: yt-dlp, FFmpeg y Deno se descargan desde la propia app.
- Reintento automático con otro formato, estado visible de cada descarga, progreso global.
- Notificaciones del sistema, menú con atajos, instancia única (pasa las URLs a la ventana abierta).
- **Diagnóstico**: «Comprobar instalación», registro, y «Copiar detalle» en cada error.

## Instalación

### Ejecutable (sin Python)

Descarga el paquete de tu sistema desde *Releases* y ábrelo:

| Sistema | Paquete | Arranque |
|---------|---------|----------|
| Windows | `FireDownload-1.0.0-windows-x64.zip` | `FireDownload\FireDownload.exe` |
| Linux   | `FireDownload-1.0.0-linux-x64.tar.gz` | `./FireDownload/FireDownload` o `./install.sh` |
| macOS   | `FireDownload-1.0.0-macos-<arq>.zip` | `FireDownload.app` |

La primera vez, la app ofrece instalar **yt-dlp, FFmpeg y Deno** (Ajustes → Gestionar herramientas).

### Desde el código

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                   # o: python -m firedownload  /  firedownload (tras pip install .)
```

Requiere Python 3.10+. Puedes pasar URLs como argumentos: `python main.py https://…`.

## Herramientas externas

| Herramienta | Para qué | Instalación desde la app |
|-------------|----------|--------------------------|
| yt-dlp | descargar | binario oficial de GitHub, verificado con `SHA2-256SUMS` |
| FFmpeg | unir vídeo+audio, MP3, subtítulos, SponsorBlock, recortes | builds de BtbN (Windows y Linux; en macOS: `brew install ffmpeg`) |
| Deno | exigido por YouTube desde yt-dlp 2025.11.12 | release oficial de Deno |

Se guardan en la carpeta de datos (`bin/`) y cada descarga se **verifica por SHA-256**; si el hash no
coincide o no existe, no se instala nada. También se detectan las que ya tengas en el sistema, o
en una carpeta `tools/` junto al ejecutable (modo portable).

## Compilar un ejecutable

```bash
pip install -r requirements-dev.txt pyinstaller pillow
python build_exe.py                 # carpeta + .zip/.tar.gz en dist/
python build_exe.py --onefile       # un único ejecutable
python build_exe.py --with-tools    # incluye yt-dlp, FFmpeg y Deno en tools/ (portable)
python build_exe.py --dry-run       # muestra el plan sin compilar
```

`build_exe.py` detecta el sistema donde se ejecuta (PyInstaller no compila de forma cruzada):
Windows genera `dist/FireDownload/FireDownload.exe`, Linux una carpeta con el binario, un `.desktop`
y un `install.sh`, y macOS un `FireDownload.app`. En GitHub, el flujo `release.yml` lo hace en los
tres sistemas al publicar una etiqueta `v*`. En Linux se necesitan las librerías de Qt (`libxcb-cursor0`).

> Con `--with-tools` el paquete incluye FFmpeg (GPL): si lo publicas, cumple sus condiciones de licencia.

## Datos de usuario

| SO      | Carpeta                                       |
|---------|-----------------------------------------------|
| Linux   | `~/.config/firedownload/`                     |
| Windows | `%APPDATA%\FireDownload\`                     |
| macOS   | `~/Library/Application Support/FireDownload/` |

Contiene `config.json`, `history.json`, `queue.json`, `archive.txt`, `bin/`, `cache/` y `logs/`.

## Logo

Copia tu `Logo.png` a `assets/Logo.png`: se usa en la cabecera, el icono de la ventana,
«Acerca de» y el icono del ejecutable (con Pillow).

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```

Usan un yt-dlp falso y Qt en modo offscreen, y un servidor HTTP local para el instalador.

## Estructura

```
main.py  build_exe.py  build_zip.py  pyproject.toml  LICENSE
firedownload/
  app.py  config.py
  core/  utils ytdlp info tools tasks thumbs sounds notify profiles history queue_store
         single_instance worker manager
  ui/    theme main_window download_tab search_tab info_dialog tools_dialog about_dialog
         check_dialog log_dialog history_tab settings_tab preview_dialog
tests/   .github/workflows/ (ci, release)
```

## Autor y enlaces

Creado por **Dragoland** · [bitcriollo.pages.dev](https://bitcriollo.pages.dev) ·
[github.com/Dragoland/firedownload](https://github.com/Dragoland/firedownload)

Los datos de «Acerca de» salen de `firedownload/__init__.py`; el texto de «Sobre el autor» está en
`firedownload/ui/about_dialog.py`.

## Licencia

[MIT](LICENSE) © 2026 Dragoland. Usa yt-dlp (Unlicense), PySide6/Qt (LGPLv3) y psutil (BSD-3);
FFmpeg y Deno son proyectos independientes. Descarga solo contenido sobre el que tengas derechos
o permiso y respeta los términos de cada plataforma.
