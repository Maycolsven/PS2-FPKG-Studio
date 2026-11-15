"""
gui.py - Interfaz gráfica principal para el conversor PS2 a PS4 (ISO → PKG).

Construida con tkinter + ttk, tema oscuro, interfaz completamente en español.
Usa hilos para no congelar la GUI durante la construcción del PKG.
"""

import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------------------
# Importaciones de módulos hermanos
# ---------------------------------------------------------------------------
from .pkg_builder import PKGProject, quick_convert
from .config_generator import COMPATIBILITY_DB, EmulatorConfig, get_game_config
from .iso_utils import validate_ps2_iso, get_iso_info

# ---------------------------------------------------------------------------
# Constantes de estilo
# ---------------------------------------------------------------------------
_BG_DARK = "#1e1e1e"
_BG_MID = "#2d2d2d"
_BG_LIGHT = "#3c3c3c"
_FG_WHITE = "#e0e0e0"
_FG_DIM = "#aaaaaa"
_ACCENT = "#0078d4"
_ACCENT_HOVER = "#1a8cff"
_ERROR = "#ff4444"
_SUCCESS = "#44cc44"
_FONT_FAMILY = "Segoe UI"
_FONT_MAIN = (_FONT_FAMILY, 10)
_FONT_BOLD = (_FONT_FAMILY, 10, "bold")
_FONT_TITLE = (_FONT_FAMILY, 14, "bold")
_FONT_LOG = ("Consolas", 9)


# ============================================================================
# TextHandler — redirige mensajes de logging al widget Text de tkinter
# ============================================================================
class TextHandler(logging.Handler):
    """Handler de logging que escribe en un widget ``tk.Text`` de forma segura
    desde cualquier hilo, usando ``widget.after()``."""

    def __init__(self, text_widget: tk.Text) -> None:
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record) + "\n"
        # after() es thread-safe en tkinter
        self.text_widget.after(0, self._append, msg)

    def _append(self, msg: str) -> None:
        self.text_widget.configure(state=tk.NORMAL)
        self.text_widget.insert(tk.END, msg)
        self.text_widget.see(tk.END)
        self.text_widget.configure(state=tk.DISABLED)


# ============================================================================
# Configuración del tema oscuro (ttk.Style)
# ============================================================================
def _apply_dark_theme(style: ttk.Style) -> None:
    """Configura un tema oscuro personalizado para todos los widgets ttk."""

    style.theme_use("clam")

    # ---------- widgets generales ----------
    style.configure(".", background=_BG_DARK, foreground=_FG_WHITE,
                    font=_FONT_MAIN, borderwidth=0, focuscolor=_ACCENT)

    style.configure("TFrame", background=_BG_DARK)
    style.configure("TLabel", background=_BG_DARK, foreground=_FG_WHITE)
    style.configure("TLabelframe", background=_BG_DARK, foreground=_ACCENT,
                    font=_FONT_BOLD)
    style.configure("TLabelframe.Label", background=_BG_DARK,
                    foreground=_ACCENT, font=_FONT_BOLD)

    # ---------- botones ----------
    style.configure("TButton", background=_BG_LIGHT, foreground=_FG_WHITE,
                    padding=(10, 5), font=_FONT_MAIN)
    style.map("TButton",
              background=[("active", _ACCENT), ("pressed", _ACCENT_HOVER)],
              foreground=[("active", "#ffffff")])

    style.configure("Accent.TButton", background=_ACCENT,
                    foreground="#ffffff", font=_FONT_BOLD, padding=(16, 10))
    style.map("Accent.TButton",
              background=[("active", _ACCENT_HOVER), ("pressed", "#005fa3")])

    # ---------- entrada de texto ----------
    style.configure("TEntry", fieldbackground=_BG_MID, foreground=_FG_WHITE,
                    insertcolor=_FG_WHITE, padding=4)

    # ---------- combobox ----------
    style.configure("TCombobox", fieldbackground=_BG_MID,
                    foreground=_FG_WHITE, selectbackground=_ACCENT,
                    padding=4)
    style.map("TCombobox", fieldbackground=[("readonly", _BG_MID)])

    # ---------- checkbutton ----------
    style.configure("TCheckbutton", background=_BG_DARK,
                    foreground=_FG_WHITE, font=_FONT_MAIN)
    style.map("TCheckbutton",
              background=[("active", _BG_DARK)],
              foreground=[("active", _FG_WHITE)])

    # ---------- notebook (pestañas) ----------
    style.configure("TNotebook", background=_BG_DARK, borderwidth=0)
    style.configure("TNotebook.Tab", background=_BG_LIGHT,
                    foreground=_FG_DIM, padding=(14, 6), font=_FONT_MAIN)
    style.map("TNotebook.Tab",
              background=[("selected", _BG_DARK)],
              foreground=[("selected", _FG_WHITE)])

    # ---------- progressbar ----------
    style.configure("Horizontal.TProgressbar", troughcolor=_BG_MID,
                    background=_ACCENT, thickness=22)

    # ---------- treeview ----------
    style.configure("Treeview", background=_BG_MID, foreground=_FG_WHITE,
                    fieldbackground=_BG_MID, rowheight=26, font=_FONT_MAIN)
    style.configure("Treeview.Heading", background=_BG_LIGHT,
                    foreground=_FG_WHITE, font=_FONT_BOLD)
    style.map("Treeview",
              background=[("selected", _ACCENT)],
              foreground=[("selected", "#ffffff")])

    # ---------- scrollbar ----------
    style.configure("Vertical.TScrollbar", background=_BG_LIGHT,
                    troughcolor=_BG_DARK, arrowcolor=_FG_WHITE)


# ============================================================================
# Clase principal de la aplicación
# ============================================================================
class PS2toPKGApp:
    """Ventana principal del conversor PS2 → PS4 PKG."""

    VERSION = "1.0.0"

    def __init__(self) -> None:
        # ----- ventana raíz -----
        self.root = tk.Tk()
        self.root.title("PS2 a PS4 - Conversor ISO a PKG")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        self.root.configure(bg=_BG_DARK)

        # Intentar icono (no bloquear si falla)
        try:
            self.root.iconbitmap(default="")
        except tk.TclError:
            pass

        # ----- estilo -----
        self.style = ttk.Style(self.root)
        _apply_dark_theme(self.style)

        # ----- variables de estado -----
        self.iso_paths: list[str] = []
        
        # Auto-detectar eboot.bin si existe en assets
        _default_eboot = ""
        _candidate_eboot = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "eboot.bin"))
        if os.path.isfile(_candidate_eboot):
            _default_eboot = _candidate_eboot

        self.eboot_path = tk.StringVar(value=_default_eboot)
        self.icon_path = tk.StringVar(value="")
        self.pic_path = tk.StringVar(value="")
        self.output_dir = tk.StringVar(value="")

        self.game_id_var = tk.StringVar(value="")
        self.game_title_var = tk.StringVar(value="")
        self.title_id_var = tk.StringVar(value="")
        self.content_id_var = tk.StringVar(value="")

        # Configuración del emulador y gráficos
        self.gs_render_var = tk.StringVar(value="2x2")
        self.gs_scale_var = tk.StringVar(value="edgesmooth")
        self.fullscreen_var = tk.BooleanVar(value=True)
        self.trophies_var = tk.BooleanVar(value=False)
        self.widescreen_var = tk.BooleanVar(value=True)
        self.host_audio_var = tk.BooleanVar(value=True)

        # Modificadores gráficos HD & Rendimiento
        self.fps_60_var = tk.BooleanVar(value=True)
        self.deblur_var = tk.BooleanVar(value=True)
        self.force_prog_var = tk.BooleanVar(value=True)
        self.mtvu_var = tk.BooleanVar(value=True)
        self.scanlines_var = tk.StringVar(value="None")

        self.compat_info_var = tk.StringVar(
            value="Seleccione un juego de la BD para ver parches de compatibilidad."
        )

        # Control de hilo
        self._build_thread: threading.Thread | None = None
        self._building = False

        # ----- logging -----
        self.logger = logging.getLogger("PS2toPKG")
        self.logger.setLevel(logging.DEBUG)

        # ----- construir interfaz -----
        self._build_ui()

    # -----------------------------------------------------------------------
    # Construcción de la interfaz
    # -----------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Construye toda la interfaz de la ventana."""

        # Notebook (pestañas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Pestañas
        self._tab_quick = ttk.Frame(self.notebook)
        self._tab_config = ttk.Frame(self.notebook)
        self._tab_compat = ttk.Frame(self.notebook)
        self._tab_about = ttk.Frame(self.notebook)

        self.notebook.add(self._tab_quick, text=" Conversión Rápida ")
        self.notebook.add(self._tab_config, text=" Configuración del Emulador ")
        self.notebook.add(self._tab_compat, text=" Base de Datos de Compatibilidad ")
        self.notebook.add(self._tab_about, text=" Acerca de ")

        self._build_tab_quick()
        self._build_tab_config()
        self._build_tab_compat()
        self._build_tab_about()

    # ========================= TAB 1: CONVERSIÓN RÁPIDA ====================
    def _build_tab_quick(self) -> None:
        """Pestaña de conversión rápida."""

        # Canvas + Scrollbar para contenido largo
        canvas = tk.Canvas(self._tab_quick, bg=_BG_DARK, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self._tab_quick, orient=tk.VERTICAL,
                                  command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        # Vincular scroll del ratón
        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        parent = scroll_frame

        # --- Sección: Archivos de Entrada ---
        frm_input = ttk.LabelFrame(parent, text="  Archivos de Entrada  ",
                                   padding=10)
        frm_input.pack(fill=tk.X, padx=10, pady=(10, 5))

        btn_row = ttk.Frame(frm_input)
        btn_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_row, text="Agregar ISO...",
                   command=self._add_iso).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Quitar ISO",
                   command=self._remove_iso).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_row, text="Limpiar todo",
                   command=self._clear_isos).pack(side=tk.LEFT)

        self.iso_listbox = tk.Listbox(
            frm_input, height=4, bg=_BG_MID, fg=_FG_WHITE,
            selectbackground=_ACCENT, selectforeground="#ffffff",
            font=_FONT_MAIN, borderwidth=1, relief=tk.FLAT,
            activestyle="none"
        )
        self.iso_listbox.pack(fill=tk.X, pady=(0, 2))

        lbl_hint = ttk.Label(
            frm_input,
            text="Formatos soportados: .iso, .bin, .img  —  "
                 "Agregue múltiples ISOs para juegos multi-disco.",
            foreground=_FG_DIM, font=(_FONT_FAMILY, 9)
        )
        lbl_hint.pack(anchor=tk.W)

        # --- Sección: Información del Juego ---
        frm_info = ttk.LabelFrame(parent, text="  Información del Juego  ",
                                  padding=10)
        frm_info.pack(fill=tk.X, padx=10, pady=5)

        self._labeled_entry(frm_info, "ID del Juego:", self.game_id_var, row=0)
        self._labeled_entry(frm_info, "Título del Juego:", self.game_title_var,
                            row=1)

        # Title ID con botón auto-generar
        lbl_tid = ttk.Label(frm_info, text="Title ID / CUSA:")
        lbl_tid.grid(row=2, column=0, sticky=tk.W, pady=3)
        tid_frame = ttk.Frame(frm_info)
        tid_frame.grid(row=2, column=1, sticky=tk.EW, pady=3)
        tid_entry = ttk.Entry(tid_frame, textvariable=self.title_id_var,
                              width=30)
        tid_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(tid_frame, text="Auto-generar",
                   command=self._autogenerate_title_id).pack(side=tk.LEFT)

        self._labeled_entry(frm_info, "Content ID:", self.content_id_var,
                            row=3)

        frm_info.columnconfigure(1, weight=1)

        # --- Sección: Archivos del Emulador ---
        frm_emu = ttk.LabelFrame(parent,
                                 text="  Archivos del Emulador  ", padding=10)
        frm_emu.pack(fill=tk.X, padx=10, pady=5)

        emu_row = ttk.Frame(frm_emu)
        emu_row.pack(fill=tk.X)

        ttk.Button(emu_row, text="Seleccionar eboot.bin...",
                   command=self._select_eboot).pack(side=tk.LEFT, padx=(0, 8))
        self.lbl_eboot = ttk.Label(emu_row, textvariable=self.eboot_path,
                                   foreground=_FG_DIM,
                                   font=(_FONT_FAMILY, 9))
        self.lbl_eboot.pack(side=tk.LEFT, fill=tk.X, expand=True)

        lbl_note = ttk.Label(
            frm_emu,
            text="⚠ Requiere el eboot.bin del emulador PS2 Classics para PS4.",
            foreground="#ffcc00", font=(_FONT_FAMILY, 9)
        )
        lbl_note.pack(anchor=tk.W, pady=(5, 0))

        # --- Sección: Personalización ---
        frm_custom = ttk.LabelFrame(parent, text="  Personalización  ",
                                    padding=10)
        frm_custom.pack(fill=tk.X, padx=10, pady=5)

        icon_row = ttk.Frame(frm_custom)
        icon_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(icon_row, text="Icono (icon0.png, 512×512)...",
                   command=self._select_icon).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(icon_row, textvariable=self.icon_path,
                  foreground=_FG_DIM,
                  font=(_FONT_FAMILY, 9)).pack(side=tk.LEFT, fill=tk.X,
                                                expand=True)

        pic_row = ttk.Frame(frm_custom)
        pic_row.pack(fill=tk.X)
        ttk.Button(pic_row, text="Fondo (pic0.png)...",
                   command=self._select_pic).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(pic_row, textvariable=self.pic_path,
                  foreground=_FG_DIM,
                  font=(_FONT_FAMILY, 9)).pack(side=tk.LEFT, fill=tk.X,
                                                expand=True)

        # --- Sección: Carpeta de Salida ---
        frm_out = ttk.LabelFrame(parent, text="  Carpeta de Salida  ",
                                 padding=10)
        frm_out.pack(fill=tk.X, padx=10, pady=5)

        out_row = ttk.Frame(frm_out)
        out_row.pack(fill=tk.X)
        ttk.Button(out_row, text="Seleccionar carpeta...",
                   command=self._select_output).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(out_row, textvariable=self.output_dir,
                  foreground=_FG_DIM,
                  font=(_FONT_FAMILY, 9)).pack(side=tk.LEFT, fill=tk.X,
                                                expand=True)

        # --- Botón principal de construcción ---
        self.btn_build = ttk.Button(
            parent, text="🔧  CONSTRUIR PROYECTO PKG",
            style="Accent.TButton", command=self._start_build
        )
        self.btn_build.pack(fill=tk.X, padx=10, pady=10, ipady=4)

        # --- Barra de progreso ---
        self.progress = ttk.Progressbar(
            parent, orient=tk.HORIZONTAL, mode="determinate",
            style="Horizontal.TProgressbar"
        )
        self.progress.pack(fill=tk.X, padx=10, pady=(0, 5))

        # --- Área de log ---
        lbl_log = ttk.Label(parent, text="Registro de operaciones:",
                            font=_FONT_BOLD)
        lbl_log.pack(anchor=tk.W, padx=10, pady=(5, 2))

        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.txt_log = tk.Text(
            log_frame, height=8, bg="#111111", fg="#cccccc",
            font=_FONT_LOG, state=tk.DISABLED, wrap=tk.WORD,
            borderwidth=1, relief=tk.FLAT, insertbackground=_FG_WHITE
        )
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL,
                                   command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scroll.set)
        self.txt_log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Vincular handler de logging
        handler = TextHandler(self.txt_log)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                              datefmt="%H:%M:%S")
        )
        self.logger.addHandler(handler)

    # =================== TAB 2: CONFIGURACIÓN DEL EMULADOR =================
    def _build_tab_config(self) -> None:
        """Pestaña de configuración del emulador."""

        parent = self._tab_config

        frm_main = ttk.LabelFrame(parent,
                                  text="  Opciones del Emulador PS2  ",
                                  padding=15)
        frm_main.pack(fill=tk.X, padx=10, pady=10)

        row = 0

        # Renderizado GS
        ttk.Label(frm_main, text="Resolución Interna GS:").grid(
            row=row, column=0, sticky=tk.W, pady=6)
        combo_render = ttk.Combobox(
            frm_main, textvariable=self.gs_render_var,
            values=["none", "2x2"], state="readonly", width=18
        )
        combo_render.grid(row=row, column=1, sticky=tk.W, pady=6, padx=(10, 0))
        ttk.Label(frm_main, text="(2x2 = Super-sampling 1080p, none = Nativo)",
                  foreground=_FG_DIM, font=(_FONT_FAMILY, 8)).grid(
            row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1

        # Escalado GS
        ttk.Label(frm_main, text="Filtro Anti-Aliasing GS:").grid(
            row=row, column=0, sticky=tk.W, pady=6)
        combo_scale = ttk.Combobox(
            frm_main, textvariable=self.gs_scale_var,
            values=["edgesmooth", "motionvec", "gpu", "none"], state="readonly",
            width=18
        )
        combo_scale.grid(row=row, column=1, sticky=tk.W, pady=6, padx=(10, 0))
        ttk.Label(frm_main, text="(edgesmooth suaviza bordes, motionvec añade anti-ghosting)",
                  foreground=_FG_DIM, font=(_FONT_FAMILY, 8)).grid(
            row=row, column=2, sticky=tk.W, padx=(10, 0))
        row += 1

        # Filtro Scanlines / CRT
        ttk.Label(frm_main, text="Filtro Retro Scanlines:").grid(
            row=row, column=0, sticky=tk.W, pady=6)
        combo_scan = ttk.Combobox(
            frm_main, textvariable=self.scanlines_var,
            values=["None", "Light", "CRT"], state="readonly", width=18
        )
        combo_scan.grid(row=row, column=1, sticky=tk.W, pady=6, padx=(10, 0))
        row += 1

        # Sección de Modificadores HD & Rendimiento
        frm_mods = ttk.LabelFrame(parent, text="  Modificadores Gráficos HD & Rendimiento  ", padding=15)
        frm_mods.pack(fill=tk.X, padx=10, pady=(0, 10))

        mod_row = 0
        for text, var, hint in [
            ("🚀 Desbloquear 60 FPS estables (--framerate=60)", self.fps_60_var, "Aprovecha la CPU para mayor fluidez"),
            ("✨ Eliminar Desenfoque / De-Blur HD (--gs-deblur=1)", self.deblur_var, "Quita el filtro borroso original de PS2"),
            ("📺 Forzar Progresivo 480p (--force-progressive=1)", self.force_prog_var, "Elimina el parpadeo de imagen entrelazada 480i"),
            ("⚡ Aceleración Multihilo MTVU (--mtvu=1)", self.mtvu_var, "Acelera el render con múltiples núcleos de CPU"),
            ("🖥 Pantalla Ancha Nativa 16:9 (--widescreen=1)", self.widescreen_var, "Campo de visión expandido sin deformar imagen"),
            ("🎮 Pantalla Completa", self.fullscreen_var, "Ajustar al tamaño total de la pantalla"),
            ("🔊 Audio del Host", self.host_audio_var, "Procesamiento de audio de baja latencia"),
            ("🏆 Soporte de Trofeos", self.trophies_var, "Habilitar soporte interno de trofeos si existen"),
        ]:
            chk = ttk.Checkbutton(frm_mods, text=text, variable=var)
            chk.grid(row=mod_row, column=0, sticky=tk.W, pady=3)
            ttk.Label(frm_mods, text=hint, foreground=_FG_DIM, font=(_FONT_FAMILY, 8)).grid(
                row=mod_row, column=1, sticky=tk.W, padx=(15, 0))
            mod_row += 1

        # Parches personalizados
        frm_patches = ttk.LabelFrame(parent,
                                     text="  Parches Personalizados  ",
                                     padding=10)
        frm_patches.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        ttk.Label(
            frm_patches,
            text="Agregue líneas de configuración personalizadas "
                 "(una por línea):",
            foreground=_FG_DIM, font=(_FONT_FAMILY, 9)
        ).pack(anchor=tk.W, pady=(0, 5))

        self.txt_patches = tk.Text(
            frm_patches, height=6, bg=_BG_MID, fg=_FG_WHITE,
            font=_FONT_LOG, insertbackground=_FG_WHITE,
            borderwidth=1, relief=tk.FLAT
        )
        self.txt_patches.pack(fill=tk.BOTH, expand=True)

        # Info de compatibilidad
        frm_compat_info = ttk.Frame(parent)
        frm_compat_info.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Label(
            frm_compat_info, textvariable=self.compat_info_var,
            foreground=_FG_DIM, font=(_FONT_FAMILY, 9), wraplength=850
        ).pack(anchor=tk.W)

    # =============== TAB 3: BASE DE DATOS DE COMPATIBILIDAD ================
    def _build_tab_compat(self) -> None:
        """Pestaña con la base de datos de compatibilidad."""

        parent = self._tab_compat

        # Barra de búsqueda
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(search_frame, text="🔍 Buscar:").pack(side=tk.LEFT,
                                                         padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._filter_compat_db)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var,
                                 width=40)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ttk.Button(search_frame, text="Aplicar config. seleccionada",
                   command=self._apply_compat_config).pack(side=tk.RIGHT)

        # Treeview
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        columns = ("game_id", "title", "status", "notes")
        self.compat_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse"
        )
        self.compat_tree.heading("game_id", text="ID del Juego")
        self.compat_tree.heading("title", text="Título")
        self.compat_tree.heading("status", text="Estado")
        self.compat_tree.heading("notes", text="Notas")

        self.compat_tree.column("game_id", width=120, minwidth=80)
        self.compat_tree.column("title", width=280, minwidth=150)
        self.compat_tree.column("status", width=100, minwidth=70)
        self.compat_tree.column("notes", width=320, minwidth=150)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                    command=self.compat_tree.yview)
        self.compat_tree.configure(yscrollcommand=tree_scroll.set)

        self.compat_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Poblar con datos
        self._populate_compat_db()

    # ========================== TAB 4: ACERCA DE ===========================
    def _build_tab_about(self) -> None:
        """Pestaña de información del proyecto."""

        parent = self._tab_about

        frm = ttk.Frame(parent, padding=20)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frm, text="PS2 a PS4 — Conversor ISO a PKG",
            font=_FONT_TITLE, foreground=_ACCENT
        ).pack(pady=(10, 2))

        ttk.Label(
            frm, text=f"Versión {self.VERSION}",
            font=(_FONT_FAMILY, 11), foreground=_FG_DIM
        ).pack(pady=(0, 15))

        info_text = (
            "Esta herramienta convierte imágenes ISO de juegos de PlayStation 2\n"
            "en paquetes PKG compatibles con PlayStation 4, utilizando el emulador\n"
            "PS2 Classics integrado en el sistema.\n"
            "\n"
            "Proceso de conversión:\n"
            "  1. Se lee y valida la imagen ISO del juego PS2.\n"
            "  2. Se detecta el ID del juego y se buscan parches de compatibilidad.\n"
            "  3. Se genera la configuración del emulador (lua/config).\n"
            "  4. Se empaqueta todo en la estructura de un PKG para PS4.\n"
            "\n"
            "Archivos necesarios:\n"
            "  • eboot.bin del emulador PS2 Classics para PS4\n"
            "  • Imagen ISO del juego PS2 (.iso, .bin, .img)\n"
            "\n"
            "Archivos opcionales:\n"
            "  • icon0.png (512×512) — Icono del juego\n"
            "  • pic0.png — Imagen de fondo\n"
            "\n"
            "Créditos:\n"
            "  Desarrollado como herramienta homebrew de código abierto.\n"
            "  Basado en la documentación comunitaria del formato PKG de PS4."
        )

        txt_about = tk.Text(
            frm, bg=_BG_MID, fg=_FG_WHITE, font=(_FONT_FAMILY, 10),
            wrap=tk.WORD, height=18, borderwidth=0, relief=tk.FLAT,
            padx=15, pady=15
        )
        txt_about.insert("1.0", info_text)
        txt_about.configure(state=tk.DISABLED)
        txt_about.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    # -----------------------------------------------------------------------
    # Helpers de UI
    # -----------------------------------------------------------------------
    def _labeled_entry(self, parent: ttk.Frame, label: str,
                       var: tk.StringVar, row: int) -> ttk.Entry:
        """Crea un par Label + Entry dentro de un grid."""
        lbl = ttk.Label(parent, text=label)
        lbl.grid(row=row, column=0, sticky=tk.W, pady=3)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=3, padx=(10, 0))
        return entry

    # -----------------------------------------------------------------------
    # Acciones de la pestaña Conversión Rápida
    # -----------------------------------------------------------------------
    def _add_iso(self) -> None:
        """Abre un diálogo para seleccionar archivos ISO y los agrega."""
        paths = filedialog.askopenfilenames(
            title="Seleccionar archivo(s) ISO de PS2",
            filetypes=[
                ("Imágenes de disco", "*.iso *.bin *.img"),
                ("Todos los archivos", "*.*"),
            ]
        )
        if not paths:
            return

        for path in paths:
            if path in self.iso_paths:
                self.logger.warning("ISO ya en la lista: %s", os.path.basename(path))
                continue
            self.iso_paths.append(path)
            self.iso_listbox.insert(tk.END, path)
            self.logger.info("ISO agregada: %s", os.path.basename(path))

        # Auto-detectar info del primer ISO si los campos están vacíos
        if self.iso_paths and not self.game_id_var.get():
            self._detect_game_info(self.iso_paths[0])

    def _remove_iso(self) -> None:
        """Quita el ISO seleccionado de la lista."""
        sel = self.iso_listbox.curselection()
        if not sel:
            messagebox.showwarning("Atención",
                                   "Seleccione un ISO de la lista para quitar.")
            return
        idx = sel[0]
        removed = self.iso_paths.pop(idx)
        self.iso_listbox.delete(idx)
        self.logger.info("ISO quitada: %s", os.path.basename(removed))

    def _clear_isos(self) -> None:
        """Limpia toda la lista de ISOs."""
        self.iso_paths.clear()
        self.iso_listbox.delete(0, tk.END)
        self.game_id_var.set("")
        self.game_title_var.set("")
        self.title_id_var.set("")
        self.content_id_var.set("")
        self.logger.info("Lista de ISOs limpiada.")

    def _detect_game_info(self, iso_path: str) -> None:
        """Intenta detectar la información del juego a partir de la ISO."""
        try:
            info = get_iso_info(iso_path)
            if info:
                self.game_id_var.set(info.get("game_id", ""))
                self.game_title_var.set(info.get("title", ""))
                self.logger.info(
                    "Información detectada — ID: %s, Título: %s",
                    info.get("game_id", "?"), info.get("title", "?")
                )
                # Auto-generar Title ID y Content ID
                self._autogenerate_title_id()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("No se pudo detectar info de la ISO: %s", exc)

    def _autogenerate_title_id(self) -> None:
        """Genera un Title ID / CUSA a partir del Game ID."""
        raw_id = self.game_id_var.get().strip()
        game_id = raw_id.replace("-", "").replace("_", "").replace(".", "")
        if not game_id:
            messagebox.showinfo("Info",
                                "Ingrese un ID del Juego primero.")
            return

        # Generar CUSA basado en hash del game_id (placeholder determinístico)
        hash_val = sum(ord(c) for c in game_id) % 99999
        title_id = f"CUSA{hash_val:05d}"
        self.title_id_var.set(title_id)

        # Content ID (exactamente 36 caracteres: UP9000-CUSAXXXXX_00-XXXXXXXXXXXXXXXX)
        suffix = game_id.upper()[:16].ljust(16, "0")
        content_id = f"UP9000-{title_id}_00-{suffix}"
        self.content_id_var.set(content_id)
        self.logger.info("Title ID generado: %s | Content ID: %s",
                         title_id, content_id)

    def _select_eboot(self) -> None:
        """Selecciona el archivo eboot.bin del emulador."""
        path = filedialog.askopenfilename(
            title="Seleccionar eboot.bin (Emulador PS2 Classics)",
            filetypes=[("eboot.bin", "eboot.bin"), ("Todos", "*.*")]
        )
        if path:
            self.eboot_path.set(path)
            self.logger.info("eboot.bin seleccionado: %s", path)

    def _select_icon(self) -> None:
        """Selecciona un icono personalizado (icon0.png)."""
        path = filedialog.askopenfilename(
            title="Seleccionar icono (icon0.png, 512×512)",
            filetypes=[("PNG", "*.png"), ("Todos", "*.*")]
        )
        if path:
            self.icon_path.set(path)
            self.logger.info("Icono seleccionado: %s", path)

    def _select_pic(self) -> None:
        """Selecciona una imagen de fondo (pic0.png)."""
        path = filedialog.askopenfilename(
            title="Seleccionar fondo (pic0.png)",
            filetypes=[("PNG", "*.png"), ("Todos", "*.*")]
        )
        if path:
            self.pic_path.set(path)
            self.logger.info("Fondo seleccionado: %s", path)

    def _select_output(self) -> None:
        """Selecciona la carpeta de salida."""
        path = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if path:
            self.output_dir.set(path)
            self.logger.info("Carpeta de salida: %s", path)

    # -----------------------------------------------------------------------
    # Proceso de construcción
    # -----------------------------------------------------------------------
    def _validate_inputs(self) -> bool:
        """Valida que todos los campos obligatorios estén completos."""
        errors: list[str] = []

        if not self.iso_paths:
            errors.append("• No se ha agregado ningún archivo ISO.")
        if not self.eboot_path.get():
            errors.append("• No se ha seleccionado el eboot.bin del emulador.")
        if not self.output_dir.get():
            errors.append("• No se ha seleccionado la carpeta de salida.")
        if not self.game_id_var.get().strip():
            errors.append("• El ID del Juego está vacío.")
        if not self.title_id_var.get().strip():
            errors.append("• El Title ID / CUSA está vacío.")
        if not self.content_id_var.get().strip():
            errors.append("• El Content ID está vacío.")

        if errors:
            messagebox.showerror(
                "Campos obligatorios faltantes",
                "Corrija los siguientes errores:\n\n" + "\n".join(errors)
            )
            return False

        # Validar ISOs
        for iso_path in self.iso_paths:
            if not os.path.isfile(iso_path):
                messagebox.showerror(
                    "Archivo no encontrado",
                    f"El archivo ISO no existe:\n{iso_path}"
                )
                return False

        if not os.path.isfile(self.eboot_path.get()):
            messagebox.showerror(
                "Archivo no encontrado",
                f"eboot.bin no encontrado:\n{self.eboot_path.get()}"
            )
            return False

        return True

    def _start_build(self) -> None:
        """Inicia el proceso de construcción en un hilo separado."""
        if self._building:
            messagebox.showwarning("En proceso",
                                   "Ya hay una construcción en curso.")
            return

        if not self._validate_inputs():
            return

        self._building = True
        self.btn_build.configure(state=tk.DISABLED)
        self.progress["value"] = 0

        self._build_thread = threading.Thread(
            target=self._build_worker, daemon=True
        )
        self._build_thread.start()

    def _update_progress(self, value: float) -> None:
        """Actualiza la barra de progreso desde cualquier hilo."""
        self.root.after(0, self._set_progress, value)

    def _set_progress(self, value: float) -> None:
        """Establece el valor de la barra de progreso (en hilo principal)."""
        self.progress["value"] = value

    def _build_worker(self) -> None:
        """Hilo de trabajo para la construcción del PKG."""
        try:
            self.logger.info("=" * 60)
            self.logger.info("Iniciando construcción del proyecto PKG...")
            self.logger.info("=" * 60)

            # Recopilar información del juego
            game_id = self.game_id_var.get().strip()
            game_title = self.game_title_var.get().strip()
            title_id = self.title_id_var.get().strip()
            content_id = self.content_id_var.get().strip()

            # Recopilar configuración del emulador
            self._update_progress(5)
            self.logger.info("Preparando configuración del emulador con modificadores HD...")

            emu_config = EmulatorConfig(
                ps2_title_id=game_id or "SLUS-20946",
                num_discs=len(self.iso_paths),
                gs_render=self.gs_render_var.get(),
                gs_scale=self.gs_scale_var.get(),
                fullscreen=self.fullscreen_var.get(),
                trophies=self.trophies_var.get(),
                widescreen=self.widescreen_var.get(),
                host_audio=self.host_audio_var.get(),
                deblur=self.deblur_var.get(),
                fps_60=self.fps_60_var.get(),
                force_progressive=self.force_prog_var.get(),
                mtvu=self.mtvu_var.get(),
                scanlines=self.scanlines_var.get(),
                custom_patches=self.txt_patches.get("1.0", tk.END).strip(),
            )

            # Buscar parches de compatibilidad
            self._update_progress(10)
            game_config = get_game_config(game_id)
            if game_config:
                self.logger.info(
                    "Parches de compatibilidad encontrados para '%s': %s",
                    game_id, game_config.get("title", "")
                )
                # Auto-aplicar parches de la base de datos
                emu_config.apply_compatibility_patches(game_id)
            else:
                self.logger.info(
                    "No se encontraron parches específicos para '%s'. Se usará perfil optimizado.", game_id
                )

            # Validar ISOs
            self._update_progress(15)
            for i, iso_path in enumerate(self.iso_paths, 1):
                self.logger.info("Validando ISO %d/%d: %s",
                                 i, len(self.iso_paths),
                                 os.path.basename(iso_path))
                val_result = validate_ps2_iso(iso_path)
                if isinstance(val_result, dict):
                    valid = val_result.get("valid", False)
                    msg = ", ".join(val_result.get("errors", []))
                else:
                    valid, msg = val_result
                if not valid:
                    raise ValueError(
                        f"ISO inválida ({os.path.basename(iso_path)}): {msg}"
                    )
                self.logger.info("  ✓ ISO válida.")

            self._update_progress(25)

            # Crear proyecto PKG
            self.logger.info("Creando estructura del proyecto PKG...")

            project = PKGProject(
                iso_paths=self.iso_paths,
                eboot_path=self.eboot_path.get(),
                game_id=game_id,
                game_title=self.game_title_var.get().strip(),
                title_id=self.title_id_var.get().strip(),
                content_id=self.content_id_var.get().strip(),
                output_dir=self.output_dir.get(),
                emu_config=emu_config,
                game_config=game_config,
                icon_path=self.icon_path.get() or None,
                pic_path=self.pic_path.get() or None,
                progress_callback=self._update_progress,
            )

            self._update_progress(30)
            self.logger.info("Construyendo PKG — esto puede tardar unos minutos...")

            result_path = project.build()

            self._update_progress(100)
            self.logger.info("=" * 60)
            self.logger.info("¡CONSTRUCCIÓN EXITOSA!")
            self.logger.info("PKG generado en: %s", result_path)
            self.logger.info("=" * 60)

            self.root.after(0, lambda: messagebox.showinfo(
                "¡Éxito!",
                f"El PKG se ha generado correctamente:\n\n{result_path}"
            ))

        except Exception as exc:  # noqa: BLE001
            self.logger.error("ERROR durante la construcción: %s", exc)
            self._update_progress(0)
            self.root.after(0, lambda: messagebox.showerror(
                "Error de Construcción",
                f"Ocurrió un error:\n\n{exc}"
            ))
        finally:
            self._building = False
            self.root.after(0, lambda: self.btn_build.configure(
                state=tk.NORMAL
            ))

    # -----------------------------------------------------------------------
    # Base de datos de compatibilidad
    # -----------------------------------------------------------------------
    def _populate_compat_db(self, filter_text: str = "") -> None:
        """Llena el Treeview con los datos de COMPATIBILITY_DB."""
        # Limpiar entradas existentes
        for item in self.compat_tree.get_children():
            self.compat_tree.delete(item)

        filter_lower = filter_text.lower()

        for game_id, data in COMPATIBILITY_DB.items():
            title = data.get("title", "Desconocido")
            status = data.get("status", "Desconocido")
            notes = data.get("notes", "")

            # Filtrar
            if filter_lower and not any(
                filter_lower in field.lower()
                for field in (game_id, title, status, notes)
            ):
                continue

            self.compat_tree.insert("", tk.END, values=(
                game_id, title, status, notes
            ))

    def _filter_compat_db(self, *_args) -> None:
        """Callback para filtrar la BD de compatibilidad."""
        self._populate_compat_db(self.search_var.get())

    def _apply_compat_config(self) -> None:
        """Aplica la configuración del juego seleccionado en la BD."""
        sel = self.compat_tree.selection()
        if not sel:
            messagebox.showwarning(
                "Atención",
                "Seleccione un juego de la tabla primero."
            )
            return

        values = self.compat_tree.item(sel[0], "values")
        game_id = values[0]

        config = get_game_config(game_id)
        if not config:
            messagebox.showinfo(
                "Sin configuración",
                f"No hay configuración específica para '{game_id}'."
            )
            return

        # Aplicar parches a la caja de texto
        patches = "\n".join(config.get("config_lines", []))
        if patches:
            self.txt_patches.delete("1.0", tk.END)
            self.txt_patches.insert("1.0", patches)

        self.compat_info_var.set(
            f"Configuración cargada para: {values[1]} ({game_id}) — "
            f"Estado: {values[2]}"
        )

        # Cambiar a la pestaña de configuración
        self.notebook.select(self._tab_config)

        self.logger.info(
            "Configuración de compatibilidad aplicada: %s (%s)",
            values[1], game_id
        )

    # -----------------------------------------------------------------------
    # Ejecución
    # -----------------------------------------------------------------------
    def run(self) -> None:
        """Inicia el bucle principal de la aplicación."""
        self.logger.info("Aplicación iniciada — PS2 a PS4 Conversor v%s",
                         self.VERSION)
        self.root.mainloop()


# ===========================================================================
# Punto de entrada
# ===========================================================================
if __name__ == "__main__":
    app = PS2toPKGApp()
    app.run()
