# Cambios

## 1.0.0

Primera versión pública.

**Descargas**
- Cola con concurrencia, pausa real del proceso, cancelar, reintentar, reordenar y cola persistente.
- Progreso global entre pistas y elementos; estado visible de cada descarga; detalle copiable de errores.
- Reintento automático con otro formato cuando el pedido no está disponible.
- Archivo de descargas, política de archivos existentes, límite de velocidad, proxy, cookies (navegador o `cookies.txt`).
- SponsorBlock, recorte por rango o capítulos, selección de elementos de playlist, perfiles.

**Búsqueda y metadatos**
- Buscador (YouTube, SoundCloud) con miniaturas; visor de metadatos con vista previa,
  pistas de audio y subtítulos.

**Distribución**
- Gestor de herramientas dentro de la app: instala yt-dlp, FFmpeg y Deno con verificación SHA-256.
- `build_exe.py`: compila para el sistema actual (Windows, Linux o macOS) y empaqueta.
- Flujos de GitHub Actions para pruebas y publicación de binarios.

**Interfaz**
- Tema oscuro con acento azul Arch, menú con atajos, notificaciones, instancia única,
  «Acerca de» con sección del autor, comprobación de instalación y registro.
- Licencia MIT.
