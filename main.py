#!/usr/bin/env python3
"""
PS2 a PS4 - Conversor ISO a PKG
================================

Punto de entrada principal de la aplicación.
Ejecutar con: python main.py [--gui] [--cli ISO_PATH OUTPUT_DIR]

Modos:
    --gui           Lanzar la interfaz gráfica (predeterminado)
    --cli           Modo línea de comandos
    --help          Mostrar ayuda
"""

import sys
import os
import argparse
import logging

# Agregar el directorio padre al path para importaciones
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def setup_logging(verbose: bool = False) -> None:
    """Configura el sistema de logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def run_gui() -> None:
    """Lanza la interfaz gráfica."""
    try:
        from src.gui import PS2toPKGApp
        app = PS2toPKGApp()
        app.run()
    except ImportError as e:
        print(f"Error al importar módulos de la GUI: {e}")
        print("Asegúrate de que tkinter está instalado.")
        sys.exit(1)
    except Exception as e:
        print(f"Error al iniciar la GUI: {e}")
        sys.exit(1)


def run_cli(args: argparse.Namespace) -> None:
    """Ejecuta la conversión en modo línea de comandos."""
    from src.pkg_builder import PKGProject, quick_convert
    from src.iso_utils import validate_ps2_iso
    from src.config_generator import get_game_config

    logger = logging.getLogger("CLI")

    # Validar ISO de entrada
    iso_path = args.iso
    if not os.path.isfile(iso_path):
        logger.error(f"Archivo ISO no encontrado: {iso_path}")
        sys.exit(1)

    logger.info(f"Validando ISO: {iso_path}")
    validation = validate_ps2_iso(iso_path)

    if not validation["valid"]:
        logger.error("La ISO no es válida:")
        for error in validation["errors"]:
            logger.error(f"  - {error}")
        sys.exit(1)

    logger.info(f"ISO válida - Game ID: {validation.get('game_id', 'Desconocido')}")
    logger.info(f"Tipo de disco: {validation.get('disc_type', 'Desconocido')}")
    logger.info(f"Tamaño: {validation.get('file_size', 0) / (1024*1024):.1f} MB")

    # Preparar argumentos de conversión
    kwargs = {}
    if args.title:
        kwargs["title"] = args.title
    if args.title_id:
        kwargs["title_id"] = args.title_id
    if args.icon:
        kwargs["icon_path"] = args.icon
    if args.eboot:
        kwargs["eboot_path"] = args.eboot

    # Ejecutar conversión rápida
    output_dir = args.output or os.path.join(os.path.dirname(iso_path), "PKG_Output")
    logger.info(f"Directorio de salida: {output_dir}")

    try:
        project_dir = quick_convert(
            iso_path=iso_path,
            output_dir=output_dir,
            eboot_path=args.eboot,
            **kwargs,
        )
        logger.info("=" * 60)
        logger.info("¡Proyecto construido exitosamente!")
        logger.info(f"Directorio del proyecto: {project_dir}")
        logger.info("=" * 60)
        logger.info("")
        logger.info("Próximos pasos:")
        logger.info("  1. Copia el eboot.bin del emulador PS2 Classics al directorio del proyecto")
        logger.info("  2. Usa orbis-pub-cmd para generar el PKG final:")
        logger.info(f'     orbis-pub-cmd.exe img_create --oformat pkg "{project_dir}"')
        logger.info("")
    except Exception as e:
        logger.error(f"Error durante la conversión: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def run_info(args: argparse.Namespace) -> None:
    """Muestra información detallada de una ISO."""
    from src.iso_utils import get_iso_info, validate_ps2_iso
    from src.config_generator import get_game_config

    logger = logging.getLogger("INFO")

    iso_path = args.iso
    if not os.path.isfile(iso_path):
        logger.error(f"Archivo no encontrado: {iso_path}")
        sys.exit(1)

    # Validación
    validation = validate_ps2_iso(iso_path)
    info = get_iso_info(iso_path)

    print("\n" + "=" * 60)
    print("  INFORMACIÓN DE LA ISO PS2")
    print("=" * 60)
    print(f"  Archivo:      {os.path.basename(iso_path)}")
    print(f"  Tamaño:       {info.get('file_size', 0) / (1024*1024):.1f} MB")
    print(f"  Tipo disco:   {info.get('disc_type', 'Desconocido')}")
    print(f"  Game ID:      {info.get('game_id', 'No detectado')}")
    print(f"  Volume ID:    {info.get('volume_id', 'N/A')}")
    print(f"  System ID:    {info.get('system_id', 'N/A')}")
    print(f"  Válida:       {'Sí ✓' if validation['valid'] else 'No ✗'}")

    if not validation["valid"]:
        print(f"\n  Errores:")
        for err in validation["errors"]:
            print(f"    - {err}")

    # Buscar en base de datos de compatibilidad
    game_id = info.get("game_id")
    if game_id:
        config = get_game_config(game_id)
        if config:
            print(f"\n  Compatibilidad: Encontrado en la base de datos ✓")
            print(f"  Título:         {config.get('title', 'N/A')}")
            print(f"  Notas:          {config.get('notes', 'N/A')}")
        else:
            print(f"\n  Compatibilidad: No encontrado en la base de datos")
            print(f"    (El juego podría funcionar con configuración por defecto)")

    # Listar archivos raíz
    root_files = info.get("root_files", [])
    if root_files:
        print(f"\n  Archivos raíz ({len(root_files)}):")
        for f in sorted(root_files)[:20]:
            print(f"    {f}")
        if len(root_files) > 20:
            print(f"    ... y {len(root_files) - 20} más")

    print("=" * 60 + "\n")


def main() -> None:
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        prog="PS2-to-PKG",
        description="Conversor de ISO PS2 a PKG PS4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py                              # Lanzar GUI
  python main.py --gui                        # Lanzar GUI
  python main.py --cli game.iso -o ./output   # Conversión por CLI
  python main.py --info game.iso              # Ver info de ISO

Notas:
  Esta herramienta genera la estructura del proyecto PKG.
  Para crear el archivo PKG final, necesitas:
  - eboot.bin del emulador PS2 Classics (extraído de un juego PS2 Classic oficial)
  - orbis-pub-cmd.exe (herramienta de Sony para generar PKGs)
        """,
    )

    # Modos mutuamente excluyentes
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--gui",
        action="store_true",
        default=True,
        help="Lanzar la interfaz gráfica (predeterminado)",
    )
    mode.add_argument(
        "--cli",
        action="store_true",
        help="Modo línea de comandos",
    )
    mode.add_argument(
        "--info",
        action="store_true",
        help="Mostrar información de una ISO",
    )

    # Argumentos para CLI e INFO
    parser.add_argument("iso", nargs="?", help="Ruta al archivo ISO de PS2")
    parser.add_argument("-o", "--output", help="Directorio de salida")
    parser.add_argument("-t", "--title", help="Título del juego (override)")
    parser.add_argument("--title-id", help="Title ID CUSA (override)")
    parser.add_argument("--icon", help="Ruta a icon0.png personalizado")
    parser.add_argument("--eboot", help="Ruta al eboot.bin del emulador")
    parser.add_argument("-v", "--verbose", action="store_true", help="Modo verboso")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.info:
        if not args.iso:
            parser.error("--info requiere una ruta ISO")
        run_info(args)
    elif args.cli:
        if not args.iso:
            parser.error("--cli requiere una ruta ISO")
        run_cli(args)
    else:
        run_gui()


if __name__ == "__main__":
    main()

