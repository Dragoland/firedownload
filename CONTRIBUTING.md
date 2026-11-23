# Contribuir

1. Crea un entorno: `python -m venv .venv && . .venv/bin/activate` (en Windows, `.venv\Scripts\activate`).
2. Instala dependencias: `pip install -r requirements-dev.txt`.
3. Ejecuta las pruebas: `pytest` (usan un yt-dlp falso y Qt en modo offscreen; no necesitan red).
4. Estilo: `ruff check .` y `ruff format .`.
5. Abre una incidencia o un pull request en https://github.com/Dragoland/firedownload.

Al reportar un fallo adjunta el informe de **Ajustes → Comprobar instalación…** y el botón
**Copiar detalle** de la descarga fallida.
