"""
╔══════════════════════════════════════════╗
║     SISTEMA BARRIL&BARRICA               ║
║     Versión 1.1                          ║
║     Requiere: Python 3.8+ con tkinter    ║
╚══════════════════════════════════════════╝

Instalación de dependencias:
  pip install pillow  (opcional, para iconos)

Uso:
  python stock_manager.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
import os
import sys
import shutil
import glob
import traceback
from datetime import datetime, date
import json

# ─────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────
APP_TITLE  = "Barril&Barrica"

# Carpeta donde vive el .exe / main.py (normalmente el pendrive)
APP_DIR = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))

# Ubicación "remota" (pendrive) — es la que el usuario transporta entre PCs
REMOTE_DB_FILE = os.path.join(APP_DIR, "stock.db")

# Carpeta local de trabajo en el disco de la PC (nunca en el pendrive).
# Usamos %LOCALAPPDATA% en Windows; si no existe, caemos a una carpeta junto al home del usuario.
_local_base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
LOCAL_APP_DIR = os.path.join(_local_base, "BarrilBarrica")
LOCAL_DB_FILE = os.path.join(LOCAL_APP_DIR, "stock.db")

# Backups automáticos (siempre en disco local, nunca en el pendrive)
BACKUP_DIR   = os.path.join(LOCAL_APP_DIR, "backups")
MAX_BACKUPS  = 20                 # cuántos backups se conservan (se borran los más viejos)
AUTOSAVE_MS  = 5 * 60 * 1000      # cada cuánto se guarda automáticamente al pendrive (5 min)

DB_FILE = LOCAL_DB_FILE  # el resto del programa trabaja SIEMPRE contra la copia local


# ─────────────────────────────────────────
#  SINCRONIZACIÓN CON EL PENDRIVE + BACKUPS
# ─────────────────────────────────────────
def _ensure_dirs():
    os.makedirs(LOCAL_APP_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def hacer_backup(path_origen, etiqueta=""):
    """Copia path_origen a la carpeta de backups locales, con fecha/hora en el nombre."""
    try:
        if not os.path.exists(path_origen):
            return None
        _ensure_dirs()
        nombre = f"stock_{_timestamp()}{('_' + etiqueta) if etiqueta else ''}.db"
        destino = os.path.join(BACKUP_DIR, nombre)
        shutil.copy2(path_origen, destino)
        _limpiar_backups_viejos()
        return destino
    except Exception:
        traceback.print_exc()
        return None


def _limpiar_backups_viejos():
    try:
        backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "stock_*.db")), key=os.path.getmtime)
        exceso = len(backups) - MAX_BACKUPS
        for viejo in backups[:max(exceso, 0)]:
            os.remove(viejo)
    except Exception:
        traceback.print_exc()


def _copia_atomica(origen, destino):
    """Copia origen -> destino de forma segura: escribe a un archivo temporal
    en el mismo destino y recién al final lo renombra (evita dejar el archivo
    final a medio escribir si se corta la luz o se desconecta el pendrive)."""
    tmp = destino + ".tmp_copia"
    shutil.copy2(origen, tmp)
    os.replace(tmp, destino)


def sincronizar_desde_pendrive():
    """Al abrir el programa: trae la base del pendrive a la PC para trabajar ahí.
    Devuelve (ok, mensaje)."""
    _ensure_dirs()
    try:
        if os.path.exists(REMOTE_DB_FILE):
            # Backup de seguridad de lo que había en el pendrive ANTES de tocar nada
            hacer_backup(REMOTE_DB_FILE, "al_abrir")
            _copia_atomica(REMOTE_DB_FILE, LOCAL_DB_FILE)
            return True, "Base copiada desde el pendrive."
        elif os.path.exists(LOCAL_DB_FILE):
            # No hay pendrive conectado pero sí una copia local previa
            return True, "⚠️ No se encontró stock.db en el pendrive. Se usó la última copia local guardada."
        else:
            return True, "No existía una base previa: se creará una nueva."
    except Exception as e:
        traceback.print_exc()
        return False, f"No se pudo sincronizar desde el pendrive: {e}"


def guardar_hacia_pendrive(silencioso=False):
    """Al cerrar (o periódicamente): guarda la copia local de vuelta al pendrive.
    Devuelve (ok, mensaje)."""
    if not os.path.exists(LOCAL_DB_FILE):
        return False, "No hay base local para guardar."
    try:
        hacer_backup(LOCAL_DB_FILE, "auto")
        _copia_atomica(LOCAL_DB_FILE, REMOTE_DB_FILE)
        return True, "Guardado en el pendrive."
    except Exception as e:
        traceback.print_exc()
        return False, f"No se pudo guardar en el pendrive ({e}). Tus datos siguen a salvo en:\n{LOCAL_DB_FILE}"

# Paleta de colores
C = {
    "bg":         "#0F1117",
    "surface":    "#1A1D27",
    "card":       "#22263A",
    "border":     "#2E3350",
    "accent":     "#722F37",
    "accent2":    "#7C3AED",
    "success":    "#22C55E",
    "warning":    "#F59E0B",
    "danger":     "#EF4444",
    "text":       "#E8EAF6",
    "subtext":    "#8892B0",
    "white":      "#FFFFFF",
}

FONT_TITLE   = ("Segoe UI", 20, "bold")
FONT_HEAD    = ("Segoe UI", 13, "bold")
FONT_BODY    = ("Segoe UI", 11)
FONT_SMALL   = ("Segoe UI", 9)
FONT_MONO    = ("Consolas", 11)

# ─────────────────────────────────────────
#  BASE DE DATOS
# ─────────────────────────────────────────
class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        c = self.conn.cursor()
        c.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS categorias (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre  TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS productos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre          TEXT NOT NULL,
                descripcion     TEXT,
                categoria_id    INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
                precio_costo    REAL DEFAULT 0,
                precio_estimado REAL DEFAULT 0,
                precio_venta    REAL DEFAULT 0,
                stock           INTEGER DEFAULT 0,
                stock_min       INTEGER DEFAULT 5,
                tamaño          TEXT DEFAULT '-',
                activo          INTEGER DEFAULT 1,
                creado_en       TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS ventas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha       TEXT DEFAULT (datetime('now','localtime')),
                total       REAL DEFAULT 0,
                descuento   REAL DEFAULT 0,
                observacion TEXT
            );

            CREATE TABLE IF NOT EXISTS venta_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                venta_id    INTEGER REFERENCES ventas(id) ON DELETE CASCADE,
                producto_id INTEGER REFERENCES productos(id),
                cantidad    INTEGER NOT NULL,
                precio_unit REAL NOT NULL,
                subtotal    REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ingresos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha       TEXT DEFAULT (datetime('now','localtime')),
                producto_id INTEGER REFERENCES productos(id),
                cantidad    INTEGER NOT NULL,
                costo_unit  REAL DEFAULT 0,
                proveedor   TEXT,
                observacion TEXT
            );
        """)
        # Migraciones
        migraciones = [
            "ALTER TABLE productos ADD COLUMN precio_estimado REAL DEFAULT 0",
            "ALTER TABLE productos ADD COLUMN tamaño TEXT DEFAULT '-'",
        ]
        try:
            count = self.conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0]
            if count == 0:
                self.conn.execute("INSERT INTO categorias (nombre) VALUES ('General')")
                self.conn.execute("INSERT INTO categorias (nombre) VALUES ('Otros')")
                self.conn.commit()
        except Exception:
            pass

    # ── Categorías ──────────────────────────
    def get_categorias(self):
        return self.conn.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()

    def add_categoria(self, nombre):
        self.conn.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre,))
        self.conn.commit()

    def del_categoria(self, cid):
        self.conn.execute("DELETE FROM categorias WHERE id=?", (cid,))
        self.conn.commit()

    # ── Productos ───────────────────────────
    def get_productos(self, buscar="", cat_id=None, solo_bajo_stock=False):
        q = """
            SELECT p.*, c.nombre AS categoria
            FROM productos p
            LEFT JOIN categorias c ON p.categoria_id = c.id
            WHERE p.activo=1
        """
        params = []
        if buscar:
            q += " AND (p.nombre LIKE ? OR c.nombre LIKE ? OR p.descripcion LIKE ?)"
            b = f"%{buscar}%"
            params += [b, b, b]
        if cat_id:
            q += " AND p.categoria_id=?"
            params.append(cat_id)
        if solo_bajo_stock:
            q += " AND p.stock <= p.stock_min"
        q += " ORDER BY p.nombre"
        return self.conn.execute(q, params).fetchall()

    def get_producto(self, pid):
        return self.conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()

    def add_producto(self, data: dict):
        cols = ", ".join(data.keys())
        phs  = ", ".join(["?"] * len(data))
        self.conn.execute(f"INSERT INTO productos ({cols}) VALUES ({phs})", list(data.values()))
        self.conn.commit()

    def update_producto(self, pid, data: dict):
        sets = ", ".join(f"{k}=?" for k in data)
        self.conn.execute(f"UPDATE productos SET {sets} WHERE id=?", list(data.values()) + [pid])
        self.conn.commit()

    def del_producto(self, pid):
        self.conn.execute("UPDATE productos SET activo=0 WHERE id=?", (pid,))
        self.conn.commit()

    def ajustar_stock(self, pid, delta):
        self.conn.execute("UPDATE productos SET stock = stock + ? WHERE id=?", (delta, pid))
        self.conn.commit()

    # ── Ventas ──────────────────────────────
    def nueva_venta(self, items: list, descuento=0, obs=""):
        """items = list of (producto_id, cantidad, precio_unit)"""
        total = sum(c * p for _, c, p in items) * (1 - descuento/100)
        c = self.conn.cursor()
        c.execute("INSERT INTO ventas (total, descuento, observacion) VALUES (?,?,?)",
                  (total, descuento, obs))
        vid = c.lastrowid
        for pid, cant, precio in items:
            c.execute("INSERT INTO venta_items (venta_id, producto_id, cantidad, precio_unit, subtotal) VALUES (?,?,?,?,?)",
                      (vid, pid, cant, precio, cant*precio))
            c.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (cant, pid))
        self.conn.commit()
        return vid

    def get_ventas(self, desde=None, hasta=None):
        q = "SELECT * FROM ventas WHERE 1=1"
        p = []
        if desde:
            q += " AND fecha >= ?"; p.append(desde)
        if hasta:
            q += " AND fecha <= ?"; p.append(hasta + " 23:59:59")
        q += " ORDER BY fecha DESC"
        return self.conn.execute(q, p).fetchall()

    def get_venta_items(self, vid):
        return self.conn.execute("""
            SELECT vi.*, p.id AS codigo, p.nombre FROM venta_items vi
            JOIN productos p ON vi.producto_id = p.id
            WHERE vi.venta_id=?
        """, (vid,)).fetchall()

    # ── Ingresos ────────────────────────────
    def nuevo_ingreso(self, pid, cantidad, costo, proveedor="", obs=""):
        self.conn.execute(
            "INSERT INTO ingresos (producto_id, cantidad, costo_unit, proveedor, observacion) VALUES (?,?,?,?,?)",
            (pid, cantidad, costo, proveedor, obs))
        self.conn.execute("UPDATE productos SET stock = stock + ? WHERE id=?", (cantidad, pid))
        self.conn.commit()

    def get_ingresos(self, desde=None, hasta=None):
        q = """
            SELECT i.*, p.nombre AS producto
            FROM ingresos i JOIN productos p ON i.producto_id=p.id
            WHERE 1=1
        """
        params = []
        if desde:
            q += " AND i.fecha >= ?"; params.append(desde)
        if hasta:
            q += " AND i.fecha <= ?"; params.append(hasta + " 23:59:59")
        q += " ORDER BY i.fecha DESC"
        return self.conn.execute(q, params).fetchall()

    # ── Reportes ────────────────────────────
    def resumen_dashboard(self):
        c = self.conn.cursor()
        total_productos = c.execute("SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0]
        bajo_stock      = c.execute("SELECT COUNT(*) FROM productos WHERE activo=1 AND stock<=stock_min").fetchone()[0]
        ventas_hoy      = c.execute(
            "SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=date('now','localtime')").fetchone()[0]
        ventas_mes      = c.execute(
            "SELECT COALESCE(SUM(total),0) FROM ventas WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now','localtime')").fetchone()[0]
        num_ventas_mes  = c.execute(
            "SELECT COUNT(*) FROM ventas WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now','localtime')").fetchone()[0]
        valor_stock     = c.execute(
            "SELECT COALESCE(SUM(stock*precio_costo),0) FROM productos WHERE activo=1").fetchone()[0]
        return {
            "total_productos": total_productos,
            "bajo_stock":      bajo_stock,
            "ventas_hoy":      ventas_hoy,
            "ventas_mes":      ventas_mes,
            "num_ventas_mes":  num_ventas_mes,
            "valor_stock":     valor_stock,
        }

    def ventas_por_dia(self, dias=30):
        return self.conn.execute("""
            SELECT date(fecha) as dia, SUM(total) as total, COUNT(*) as cantidad
            FROM ventas
            WHERE fecha >= date('now','localtime',?)
            GROUP BY dia ORDER BY dia
        """, (f"-{dias} days",)).fetchall()

    def top_productos_vendidos(self, limit=10):
        return self.conn.execute("""
            SELECT p.nombre, SUM(vi.cantidad) as total_vendido, SUM(vi.subtotal) as total_ingresos
            FROM venta_items vi JOIN productos p ON vi.producto_id=p.id
            GROUP BY vi.producto_id ORDER BY total_vendido DESC LIMIT ?
        """, (limit,)).fetchall()

    def close(self):
        self.conn.close()


# ─────────────────────────────────────────
#  HELPERS UI
# ─────────────────────────────────────────
def make_frame(parent, **kw):
    return tk.Frame(parent, bg=kw.pop("bg", C["surface"]), **kw)

def make_label(parent, text, **kw):
    return tk.Label(parent, text=text, bg=kw.pop("bg", C["surface"]),
                    fg=kw.pop("fg", C["text"]), font=kw.pop("font", FONT_BODY), **kw)

def make_entry(parent, **kw):
    e = tk.Entry(parent,
                 bg=C["card"], fg=C["text"], insertbackground=C["text"],
                 relief="flat", font=FONT_BODY, **kw)
    e.configure(highlightthickness=1, highlightbackground=C["border"], highlightcolor=C["accent"])
    return e

def make_button(parent, text, cmd, color=None, **kw):
    color = color or C["accent"]
    btn = tk.Button(parent, text=text, command=cmd,
                    bg=color, fg=C["white"], font=FONT_BODY,
                    relief="flat", cursor="hand2", padx=14, pady=6,
                    activebackground=color, activeforeground=C["white"], **kw)
    return btn

def fmt_money(v):
    try:
        return f"$ {float(v):,.2f}"
    except Exception:
        return "$ 0.00"

def row_tag(i):
    return "odd" if i % 2 else "even"

def style_tree(tree):
    tree.configure(style="Custom.Treeview")

def configure_styles():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("Custom.Treeview",
                 background=C["card"],
                 foreground=C["text"],
                 fieldbackground=C["card"],
                 rowheight=28,
                 font=FONT_BODY)
    s.configure("Custom.Treeview.Heading",
                 background=C["border"],
                 foreground=C["text"],
                 font=("Segoe UI", 10, "bold"),
                 relief="flat")
    s.map("Custom.Treeview",
          background=[("selected", C["accent"])],
          foreground=[("selected", C["white"])])
    s.configure("TScrollbar", background=C["border"], troughcolor=C["surface"])
    s.configure("TCombobox",
                 fieldbackground=C["card"],
                 background=C["card"],
                 foreground=C["text"],
                 selectbackground=C["accent"])
    s.map("TCombobox", fieldbackground=[("readonly", C["card"])],
          foreground=[("readonly", C["text"])])


def scrollable_tree(parent, columns, headings, widths, show="headings"):
    frame = make_frame(parent, bg=C["surface"])
    tree = ttk.Treeview(frame, columns=columns, show=show, style="Custom.Treeview")
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    for col, hdg, w in zip(columns, headings, widths):
        tree.heading(col, text=hdg)
        tree.column(col, width=w, minwidth=40, anchor="center")
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree


# ─────────────────────────────────────────
#  DIÁLOGOS GENÉRICOS
# ─────────────────────────────────────────
class FormDialog(tk.Toplevel):
    """Ventana modal con campos de formulario."""
    def __init__(self, parent, title, fields, initial=None, db=None):
        """
        fields: list of (label, key, type, options)
          type: 'text','int','float','combo','text_area'
          options: list for combo
        """
        super().__init__(parent)
        self.title(title)
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.result = None
        self.db = db

        # Centrar
        self.transient(parent)
        self.grab_set()

        wrap = make_frame(self, bg=C["bg"])
        wrap.pack(fill="both", expand=True, padx=16, pady=10)

        make_label(wrap, title, font=FONT_HEAD, bg=C["bg"], fg=C["accent"]).pack(anchor="w", pady=(0,14))

        self._vars = {}
        self._widgets = {}

        for label, key, ftype, *opts in fields:
            row = make_frame(wrap, bg=C["bg"])
            row.pack(fill="x", pady=2)
            make_label(row, label, bg=C["bg"], fg=C["subtext"], font=FONT_SMALL).pack(anchor="w")

            val = (initial or {}).get(key, "")

            if ftype == "combo":
                choices = opts[0] if opts else []
                var = tk.StringVar(value=str(val))
                cb = ttk.Combobox(row, textvariable=var, values=choices,
                                  state="readonly", font=FONT_BODY)
                cb.pack(fill="x", ipady=4)
                self._vars[key] = var
                self._widgets[key] = cb
            elif ftype == "text_area":
                var = tk.StringVar(value=str(val))
                t = tk.Text(row, bg=C["card"], fg=C["text"], insertbackground=C["text"],
                            relief="flat", font=FONT_BODY, height=2,
                            highlightthickness=1, highlightbackground=C["border"])
                t.insert("1.0", str(val))
                t.pack(fill="x")
                self._vars[key] = None
                self._widgets[key] = t
            else:
                var = tk.StringVar(value=str(val))
                e = make_entry(row, textvariable=var)
                e.pack(fill="x", ipady=4)
                self._vars[key] = var
                self._widgets[key] = e

        btns = make_frame(wrap, bg=C["bg"])
        btns.pack(fill="x", pady=(16, 0))
        make_button(btns, "Cancelar", self.destroy, color=C["border"]).pack(side="right", padx=(6,0))
        make_button(btns, "Guardar", self._save, color=C["accent"]).pack(side="right")

        self.wait_window()

    def _save(self):
        self.result = {}
        for key, var in self._vars.items():
            if var is None:
                w = self._widgets[key]
                self.result[key] = w.get("1.0", "end-1c")
            else:
                self.result[key] = var.get()
        self.destroy()


# ─────────────────────────────────────────
#  MÓDULOS / PESTAÑAS
# ─────────────────────────────────────────

class DashboardTab(tk.Frame):
    def __init__(self, parent, db: Database, app):
        super().__init__(parent, bg=C["bg"])
        self.db  = db
        self.app = app
        self._build()

    def _build(self):
        # Encabezado
        hdr = make_frame(self, bg=C["bg"])
        hdr.pack(fill="x", padx=24, pady=(20, 8))
        make_label(hdr, f"Bienvenido a {APP_TITLE}", font=FONT_TITLE,
                   bg=C["bg"], fg=C["white"]).pack(side="left")
        now = datetime.now().strftime("%d/%m/%Y  %H:%M")
        make_label(hdr, now, bg=C["bg"], fg=C["subtext"], font=FONT_SMALL).pack(side="right", pady=10)

        # Cards de resumen
        self.cards_frame = make_frame(self, bg=C["bg"])
        self.cards_frame.pack(fill="x", padx=24, pady=8)

        # Últimas ventas
        lbl_frame = make_frame(self, bg=C["bg"])
        lbl_frame.pack(fill="x", padx=24, pady=(14, 4))
        make_label(lbl_frame, "Últimas ventas del mes", font=FONT_HEAD,
                   bg=C["bg"], fg=C["text"]).pack(side="left")

        tf, self.ventas_tree = scrollable_tree(
            self,
            ("fecha", "total", "descuento", "obs"),
            ("Fecha / Hora", "Total", "Descuento %", "Observación"),
            (180, 130, 100, 250)
        )
        tf.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # Top productos
        lbl2 = make_frame(self, bg=C["bg"])
        lbl2.pack(fill="x", padx=24, pady=(8, 4))
        make_label(lbl2, "Top 5 productos más vendidos", font=FONT_HEAD,
                   bg=C["bg"], fg=C["text"]).pack(side="left")

        tf2, self.top_tree = scrollable_tree(
            self,
            ("nombre", "vendido", "ingresos"),
            ("Producto", "Unidades vendidas", "Total ingresos"),
            (280, 160, 160)
        )
        tf2.pack(fill="both", expand=False, padx=24, pady=(0, 16))

        self.refresh()

    def _make_card(self, parent, label, value, color, icon=""):
        f = tk.Frame(parent, bg=color, padx=18, pady=14)
        tk.Label(f, text=icon + "  " + label, bg=color, fg=C["white"],
                 font=FONT_SMALL).pack(anchor="w")
        tk.Label(f, text=value, bg=color, fg=C["white"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(4, 0))
        return f

    def refresh(self):
        d = self.db.resumen_dashboard()

        for w in self.cards_frame.winfo_children():
            w.destroy()

        cards = [
            ("Productos activos",   str(d["total_productos"]),     C["accent"],  "📦"),
            ("Stock bajo mínimo",   str(d["bajo_stock"]),          C["danger"],  "⚠️"),
            ("Ventas hoy",          fmt_money(d["ventas_hoy"]),    C["success"], "💰"),
            ("Ventas este mes",     fmt_money(d["ventas_mes"]),    C["accent2"], "📈"),
            ("Transacciones/mes",   str(d["num_ventas_mes"]),      C["warning"], "🧾"),
            ("Valor inventario",    fmt_money(d["valor_stock"]),   "#1E6B4A",   "🏭"),
        ]
        for i, (lbl, val, col, ico) in enumerate(cards):
            c = self._make_card(self.cards_frame, lbl, val, col, ico)
            c.grid(row=0, column=i, padx=6, pady=4, sticky="ew")
            self.cards_frame.columnconfigure(i, weight=1)

        # Últimas ventas
        for row in self.ventas_tree.get_children():
            self.ventas_tree.delete(row)
        for i, v in enumerate(self.db.get_ventas()[:30]):
            self.ventas_tree.insert("", "end", values=(
                v["fecha"], fmt_money(v["total"]),
                f"{v['descuento']}%", v["observacion"] or ""
            ), tags=(row_tag(i),))
        self.ventas_tree.tag_configure("odd",  background=C["card"])
        self.ventas_tree.tag_configure("even", background=C["surface"])

        # Top productos
        for row in self.top_tree.get_children():
            self.top_tree.delete(row)
        for i, p in enumerate(self.db.top_productos_vendidos(5)):
            self.top_tree.insert("", "end", values=(
                p["nombre"], p["total_vendido"], fmt_money(p["total_ingresos"])
            ), tags=(row_tag(i),))
        self.top_tree.tag_configure("odd",  background=C["card"])
        self.top_tree.tag_configure("even", background=C["surface"])


class ProductosTab(tk.Frame):
    def __init__(self, parent, db: Database, app):
        super().__init__(parent, bg=C["bg"])
        self.db  = db
        self.app = app
        self._build()
        self.refresh()

    def _build(self):
        # Barra superior
        top = make_frame(self, bg=C["bg"])
        top.pack(fill="x", padx=20, pady=12)
        make_label(top, "Gestión de Productos", font=FONT_HEAD,
                   bg=C["bg"], fg=C["white"]).pack(side="left")

        make_button(top, "➕ Nuevo producto", self._nuevo, color=C["accent"]).pack(side="right", padx=4)
        make_button(top, "✏️ Editar", self._editar, color=C["accent2"]).pack(side="right", padx=4)
        make_button(top, "🗑 Eliminar", self._eliminar, color=C["danger"]).pack(side="right", padx=4)
        make_button(top, "📁 Categorías", self._categorias, color=C["warning"]).pack(side="right", padx=4)

        # Filtros
        fil = make_frame(self, bg=C["surface"])
        fil.pack(fill="x", padx=20, pady=(0,8))

        make_label(fil, "Buscar:", bg=C["surface"]).pack(side="left", padx=(10,4), pady=8)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *_: self.refresh())
        make_entry(fil, textvariable=self.search_var, width=28).pack(side="left", ipady=4, pady=8)

        make_label(fil, "  Categoría:", bg=C["surface"]).pack(side="left", padx=(12,4))
        self.cat_var = tk.StringVar(value="Todas")
        self.cat_combo = ttk.Combobox(fil, textvariable=self.cat_var,
                                      state="readonly", font=FONT_BODY, width=18)
        self.cat_combo.pack(side="left", ipady=4, pady=8)
        self.cat_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        self.bajo_var = tk.BooleanVar()
        tk.Checkbutton(fil, text="Solo bajo stock", variable=self.bajo_var,
                       bg=C["surface"], fg=C["text"], selectcolor=C["accent"],
                       activebackground=C["surface"], activeforeground=C["text"],
                       command=self.refresh).pack(side="left", padx=14)

        # Tabla
        tf, self.tree = scrollable_tree(
            self,
            ("nombre", "categoria", "descripcion", "stock", "stock_min", "costo", "precio_estimado", "precio", "tamaño"),
            ("Nombre", "Categoría", "Descripción", "Stock", "Mín.", "Costo", "Precio Estimado", "Precio venta", "Tamaño"),
            (140, 80, 100, 40, 40, 90, 90, 90, 50)
        )
        tf.pack(fill="both", expand=True, padx=20, pady=(0,16))

        self.tree.bind("<Double-1>", lambda _: self._editar())

    def _load_cats(self):
        cats = ["Todas"] + [c["nombre"] for c in self.db.get_categorias()]
        self.cat_combo["values"] = cats

    def refresh(self):
        self._load_cats()
        buscar = self.search_var.get()
        cat_name = self.cat_var.get()
        cat_id = None
        if cat_name and cat_name != "Todas":
            for c in self.db.get_categorias():
                if c["nombre"] == cat_name:
                    cat_id = c["id"]
                    break
        bajo = self.bajo_var.get()

        for row in self.tree.get_children():
            self.tree.delete(row)

        for i, p in enumerate(self.db.get_productos(buscar, cat_id, bajo)):
            tag = "bajo" if p["stock"] <= p["stock_min"] else row_tag(i)
            self.tree.insert("", "end", iid=str(p["id"]), values=(
                p["nombre"], p["categoria"] or "—", p["descripcion"],
                p["stock"], p["stock_min"],
                fmt_money(p["precio_costo"]), fmt_money(p["precio_estimado"]), fmt_money(p["precio_venta"]),
                p["tamaño"]
            ), tags=(tag,))

        self.tree.tag_configure("bajo",  background="#3B1A1A", foreground=C["danger"])
        self.tree.tag_configure("odd",   background=C["card"])
        self.tree.tag_configure("even",  background=C["surface"])

    def _get_fields(self):
        cats = [c["nombre"] for c in self.db.get_categorias()]
        return [
            ("Nombre *",           "nombre",        "text",  ),
            ("Descripción",        "descripcion",   "text_area",),
            ("Categoría",          "categoria_id",  "combo", cats),
            ("Precio costo",       "precio_costo",  "float", ),
            ("Precio venta",       "precio_venta",  "float", ),
            ("Stock inicial",      "stock",         "int",   ),
            ("Stock mínimo",       "stock_min",     "int",   ),
            ("Tamaño",             "tamaño",        "text",  ),
        ]

    def _nuevo(self):
        dlg = FormDialog(self, "Nuevo Producto", self._get_fields())
        if dlg.result:
            r = dlg.result
            if not r.get("nombre"):
                messagebox.showwarning("Error", "El nombre es obligatorio.")
                return
            # Resolver cat_id
            cat_id = None
            cat_name = r.get("categoria_id", "")
            for c in self.db.get_categorias():
                if c["nombre"] == cat_name:
                    cat_id = c["id"]; break
            try:
                self.db.add_producto({
                    "nombre":       r["nombre"],
                    "descripcion":  r["descripcion"],
                    "categoria_id": cat_id,
                    "precio_costo": float(r["precio_costo"] or 0),
                    "precio_estimado": round(float(r["precio_costo"] or 0) * 1.30, 2),
                    "precio_venta": float(r["precio_venta"] or 0),
                    "stock":        int(r["stock"] or 0),
                    "stock_min":    int(r["stock_min"] or 5),
                    "tamaño":       r["tamaño"] or "-",
                })
                self.refresh()
                self.app.dashboard.refresh()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _editar(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Seleccionar", "Seleccioná un producto primero.")
            return
        pid = int(sel[0])
        p   = self.db.get_producto(pid)
        cats = self.db.get_categorias()
        # Nombre de categoría actual
        cat_name = ""
        for c in cats:
            if c["id"] == p["categoria_id"]:
                cat_name = c["nombre"]; break
        initial = dict(p)
        initial["categoria_id"] = cat_name

        dlg = FormDialog(self, "Editar Producto", self._get_fields(), initial=initial)
        if dlg.result:
            r = dlg.result
            cat_id = None
            for c in cats:
                if c["nombre"] == r.get("categoria_id", ""):
                    cat_id = c["id"]; break
            try:
                self.db.update_producto(pid, {
                    "nombre":       r["nombre"],
                    "descripcion":  r["descripcion"],
                    "categoria_id": cat_id,
                    "precio_costo": float(r["precio_costo"] or 0),
                    "precio_estimado": round(float(r["precio_costo"] or 0) * 1.30, 2),
                    "precio_venta": float(r["precio_venta"] or 0),
                    "stock":        int(r["stock"] or 0),
                    "stock_min":    int(r["stock_min"] or 5),
                    "tamaño":       r["tamaño"] or "-",
                })
                self.refresh()
                self.app.dashboard.refresh()
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _eliminar(self):
        sel = self.tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        p = self.db.get_producto(pid)
        if messagebox.askyesno("Confirmar", f"¿Eliminar '{p['nombre']}'?"):
            self.db.del_producto(pid)
            self.refresh()
            self.app.dashboard.refresh()

    def _categorias(self):
        w = tk.Toplevel(self)
        w.title("Categorías")
        w.configure(bg=C["bg"])
        w.resizable(False, False)
        w.transient(self)
        w.grab_set()

        make_label(w, "Categorías", font=FONT_HEAD, bg=C["bg"], fg=C["accent"]).pack(padx=20, pady=12, anchor="w")

        lb = tk.Listbox(w, bg=C["card"], fg=C["text"], font=FONT_BODY,
                        selectbackground=C["accent"], relief="flat", height=10, width=30)
        lb.pack(padx=20, pady=4)

        def load():
            lb.delete(0, "end")
            for c in self.db.get_categorias():
                lb.insert("end", c["nombre"])

        load()

        btns = make_frame(w, bg=C["bg"])
        btns.pack(padx=20, pady=8, fill="x")

        def add():
            n = simpledialog.askstring("Nueva", "Nombre de categoría:", parent=w)
            if n:
                try:
                    self.db.add_categoria(n.strip())
                    load(); self.refresh()
                except Exception as e:
                    messagebox.showerror("Error", str(e), parent=w)

        def delete():
            sel = lb.curselection()
            if not sel: return
            name = lb.get(sel[0])
            cats = {c["nombre"]: c["id"] for c in self.db.get_categorias()}
            if messagebox.askyesno("Confirmar", f"¿Eliminar '{name}'?", parent=w):
                self.db.del_categoria(cats[name])
                load(); self.refresh()

        make_button(btns, "➕ Agregar", add, color=C["accent"]).pack(side="left", padx=4)
        make_button(btns, "🗑 Eliminar", delete, color=C["danger"]).pack(side="left", padx=4)
        make_button(btns, "Cerrar", w.destroy, color=C["border"]).pack(side="right", padx=4)


class NuevaVentaTab(tk.Frame):
    def __init__(self, parent, db: Database, app):
        super().__init__(parent, bg=C["bg"])
        self.db  = db
        self.app = app
        self._carrito = []
        self._build()

    def _build(self):
        # ── Panel izquierdo: búsqueda y agregar ──
        left = make_frame(self, bg=C["bg"])
        left.pack(side="left", fill="y", expand=False, padx=(20,8), pady=12)
        left.configure(width=480)
        left.pack_propagate(False)

        make_label(left, "Nueva Venta", font=FONT_HEAD, bg=C["bg"], fg=C["white"]).pack(anchor="w", pady=(0,8))

        # Buscador de producto
        sr = make_frame(left, bg=C["surface"])
        sr.pack(fill="x", pady=4)
        make_label(sr, "Producto:", bg=C["surface"], font=FONT_SMALL).pack(anchor="w", padx=8, pady=(6,0))
        self.prod_var = tk.StringVar()
        self.prod_var.trace("w", self._buscar_prod)
        make_entry(sr, textvariable=self.prod_var).pack(fill="x", padx=8, ipady=4, pady=(0,4))

        self.prod_listbox = tk.Listbox(sr, bg=C["card"], fg=C["text"], font=FONT_BODY,
                                       selectbackground=C["accent"], relief="flat", height=5)
        self.prod_listbox.pack(fill="x", padx=8, pady=(0,6))
        self.prod_listbox.bind("<Double-1>", self._seleccionar_prod)
        self._productos_encontrados = []

        # Cantidad y precio
        qr = make_frame(left, bg=C["surface"])
        qr.pack(fill="x", pady=4)

        sub1 = make_frame(qr, bg=C["surface"])
        sub1.pack(side="left", expand=True, fill="x", padx=8, pady=6)
        make_label(sub1, "Cantidad:", bg=C["surface"], font=FONT_SMALL).pack(anchor="w")
        self.cant_var = tk.StringVar(value="1")
        make_entry(sub1, textvariable=self.cant_var, width=10).pack(fill="x", ipady=4)

        sub2 = make_frame(qr, bg=C["surface"])
        sub2.pack(side="left", expand=True, fill="x", padx=8, pady=6)
        make_label(sub2, "Precio unit. $:", bg=C["surface"], font=FONT_SMALL).pack(anchor="w")
        self.precio_var = tk.StringVar()
        make_entry(sub2, textvariable=self.precio_var, width=12).pack(fill="x", ipady=4)

        make_button(left, "➕ Agregar al carrito", self._agregar_carrito,
                    color=C["accent"]).pack(fill="x", pady=8)

        # ── Panel derecho: carrito + totales ──
        right_outer = make_frame(self, bg=C["bg"])
        right_outer.pack(side="right", fill="x", expand=True, padx=(8,20), pady=12)

        right_top = make_frame(right_outer, bg=C["bg"])
        right_top.pack(side="top", fill="both", expand=True)

        make_label(right_top, "Carrito", font=FONT_HEAD, bg=C["bg"], fg=C["white"]).pack(anchor="w", pady=(0,8))
        ct, self.carrito_tree = scrollable_tree(
            right_top,
            ("nombre","cant","precio","sub"),
            ("Producto","Cant.","Precio","Subtotal"),
            (220, 65, 110, 110)
        )
        self.carrito_tree.configure(height=8)
        ct.pack(fill="x", expand=False)
        make_button(right_top, "❌ Quitar seleccionado", self._quitar_carrito,
                    color=C["danger"]).pack(fill="x", pady=(4,0))

        # Totales y confirmar (fijo abajo a la derecha)
        bot = make_frame(right_outer, bg=C["surface"])
        bot.pack(side="top", fill="x", pady=(6,0))

        tr = make_frame(bot, bg=C["surface"])
        tr.pack(fill="x", padx=10, pady=6)
        make_label(tr, "Descuento %:", bg=C["surface"], font=FONT_SMALL).pack(side="left")
        self.desc_var = tk.StringVar(value="0")
        make_entry(tr, textvariable=self.desc_var, width=6).pack(side="left", padx=6, ipady=3)
        self.desc_var.trace("w", lambda *_: self._update_total())

        self.total_lbl = make_label(bot, "TOTAL:  $ 0.00", bg=C["surface"],
                                    fg=C["success"], font=("Segoe UI", 16, "bold"))
        self.total_lbl.pack(pady=4)

        obs_frame = make_frame(bot, bg=C["surface"])
        obs_frame.pack(fill="x", padx=10, pady=(0,4))
        make_label(obs_frame, "Observación:", bg=C["surface"], font=FONT_SMALL).pack(anchor="w")
        self.obs_var = tk.StringVar()
        make_entry(obs_frame, textvariable=self.obs_var).pack(fill="x", ipady=3)

        make_button(bot, "✅ CONFIRMAR VENTA", self._confirmar_venta,
                    color=C["success"]).pack(fill="x", padx=10, pady=10)

    def _buscar_prod(self, *_):
        q = self.prod_var.get()
        self.prod_listbox.delete(0, "end")
        self._productos_encontrados = []
        if len(q) < 1:
            return
        prods = self.db.get_productos(buscar=q)[:12]
        for p in prods:
            stock_txt = f"[{p['stock']}]"
            self.prod_listbox.insert("end", f"{p['nombre']}  {stock_txt}  {fmt_money(p['precio_venta'])}")
            self._productos_encontrados.append(p)

    def _seleccionar_prod(self, _=None):
        sel = self.prod_listbox.curselection()
        if not sel:
            return
        p = self._productos_encontrados[sel[0]]
        self.prod_var.set(p["nombre"])
        self.precio_var.set(str(p["precio_venta"]))
        self._selected_pid = p["id"]
        self._selected_nombre = p["nombre"]
        self._selected_stock = p["stock"]
        self.prod_listbox.delete(0, "end")

    _selected_pid = None
    _selected_nombre = ""
    _selected_stock = 0

    def _agregar_carrito(self):
        if not self._selected_pid:
            messagebox.showwarning("Atención", "Seleccioná un producto de la lista.")
            return
        try:
            cant = int(self.cant_var.get())
            precio = float(self.precio_var.get())
        except ValueError:
            messagebox.showerror("Error", "Cantidad y precio deben ser numéricos.")
            return
        if cant <= 0:
            messagebox.showwarning("Atención", "La cantidad debe ser mayor a 0.")
            return
        if cant > self._selected_stock:
            messagebox.showwarning("Stock insuficiente", f"Stock disponible: {self._selected_stock}")
            return
        for i, item in enumerate(self._carrito):
            if item[0] == self._selected_pid:
                nueva_cant = item[2] + cant
                if nueva_cant > self._selected_stock:
                    messagebox.showwarning("Stock", f"Stock disponible: {self._selected_stock}")
                    return
                self._carrito[i] = (item[0], item[1], nueva_cant, precio)
                self._refresh_carrito()
                return
        self._carrito.append((self._selected_pid, self._selected_nombre, cant, precio))
        self._refresh_carrito()
        self.prod_var.set("")
        self.cant_var.set("1")
        self.precio_var.set("")
        self._selected_pid = None

    def _refresh_carrito(self):
        for row in self.carrito_tree.get_children():
            self.carrito_tree.delete(row)
        for i, (pid, nom, cant, precio) in enumerate(self._carrito):
            self.carrito_tree.insert("", "end", iid=str(i), values=(
                nom, cant, fmt_money(precio), fmt_money(cant*precio)
            ), tags=(row_tag(i),))
        self.carrito_tree.tag_configure("odd",  background=C["card"])
        self.carrito_tree.tag_configure("even", background=C["surface"])
        self._update_total()

    def _quitar_carrito(self):
        sel = self.carrito_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self._carrito.pop(idx)
        self._refresh_carrito()

    def _update_total(self):
        bruto = sum(c * p for _, _, c, p in self._carrito)
        try:
            desc = float(self.desc_var.get() or 0)
        except ValueError:
            desc = 0
        total = bruto * (1 - desc/100)
        self.total_lbl.config(text=f"TOTAL:  {fmt_money(total)}")

    def _confirmar_venta(self):
        if not self._carrito:
            messagebox.showwarning("Carrito vacío", "Agregá productos antes de confirmar.")
            return
        try:
            desc = float(self.desc_var.get() or 0)
        except ValueError:
            desc = 0
        bruto = sum(c * p for _, _, c, p in self._carrito)
        total = bruto * (1 - desc/100)
        msg = f"Confirmar venta por {fmt_money(total)}?\n\nProductos:\n"
        for _, nom, cant, precio in self._carrito:
            msg += f"  • {nom} x{cant}  {fmt_money(cant*precio)}\n"
        if not messagebox.askyesno("Confirmar venta", msg):
            return
        items = [(pid, cant, precio) for pid, _, cant, precio in self._carrito]
        obs = self.obs_var.get()
        vid = self.db.nueva_venta(items, desc, obs)
        self._carrito.clear()
        self._refresh_carrito()
        self.obs_var.set("")
        self.desc_var.set("0")
        messagebox.showinfo("✅ Venta registrada", f"Venta #{vid} guardada correctamente.")
        self.app.historial_ventas_tab.refresh_historial()
        self.app.dashboard.refresh()
        self.app.productos_tab.refresh()


class HistorialVentasTab(tk.Frame):
    def __init__(self, parent, db: Database, app):
        super().__init__(parent, bg=C["bg"])
        self.db  = db
        self.app = app
        self._build()
        self.refresh_historial()

    def _build(self):
        make_label(self, "Historial de Ventas", font=FONT_HEAD,
                   bg=C["bg"], fg=C["white"]).pack(padx=20, pady=(16,8), anchor="w")

        # Filtro fecha
        ff = make_frame(self, bg=C["surface"])
        ff.pack(fill="x", padx=20, pady=4)
        make_label(ff, "Desde:", bg=C["surface"], font=FONT_SMALL).pack(side="left", padx=(10,4), pady=8)
        self.desde_var = tk.StringVar(value=date.today().strftime("%Y-%m-01"))
        make_entry(ff, textvariable=self.desde_var, width=12).pack(side="left", ipady=3, pady=8)
        make_label(ff, "  Hasta:", bg=C["surface"], font=FONT_SMALL).pack(side="left", padx=4)
        self.hasta_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        make_entry(ff, textvariable=self.hasta_var, width=12).pack(side="left", ipady=3, pady=8)
        make_button(ff, "🔍 Filtrar", self.refresh_historial, color=C["accent"]).pack(side="left", padx=10)

        # Totalizador
        self.total_periodo_lbl = make_label(ff, "", bg=C["surface"],
                                            fg=C["success"], font=("Segoe UI", 11, "bold"))
        self.total_periodo_lbl.pack(side="right", padx=16)

        hf, self.hist_tree = scrollable_tree(
            self,
            ("id","fecha","total","descuento","obs"),
            ("#","Fecha / Hora","Total","Descuento %","Observación"),
            (55, 180, 130, 100, 300)
        )
        hf.pack(fill="both", expand=True, padx=20, pady=(4,4))
        self.hist_tree.bind("<Double-1>", self._ver_detalle)

        make_label(self, "Doble clic en una venta para ver el detalle",
                   bg=C["bg"], fg=C["subtext"], font=FONT_SMALL).pack(pady=(0,12))

    def refresh_historial(self):
        desde = self.desde_var.get()
        hasta = self.hasta_var.get()
        for row in self.hist_tree.get_children():
            self.hist_tree.delete(row)
        ventas = self.db.get_ventas(desde, hasta)
        total_periodo = 0
        for i, v in enumerate(ventas):
            self.hist_tree.insert("", "end", iid=str(v["id"]), values=(
                v["id"], v["fecha"], fmt_money(v["total"]),
                f"{v['descuento']}%", v["observacion"] or ""
            ), tags=(row_tag(i),))
            total_periodo += v["total"]
        self.hist_tree.tag_configure("odd",  background=C["card"])
        self.hist_tree.tag_configure("even", background=C["surface"])
        self.total_periodo_lbl.config(text=f"Total período:  {fmt_money(total_periodo)}")

    def _ver_detalle(self, _=None):
        sel = self.hist_tree.selection()
        if not sel:
            return
        vid = int(sel[0])
        items = self.db.get_venta_items(vid)

        w = tk.Toplevel(self)
        w.title(f"Detalle Venta #{vid}")
        w.configure(bg=C["bg"])
        w.geometry("620x400")
        w.transient(self)

        make_label(w, f"Detalle de Venta #{vid}", font=FONT_HEAD,
                   bg=C["bg"], fg=C["accent"]).pack(padx=20, pady=12, anchor="w")

        tf, tree = scrollable_tree(
            w,
            ("cod","nombre","cant","precio","sub"),
            ("Código","Producto","Cant.","Precio unit.","Subtotal"),
            (90, 220, 70, 120, 120)
        )
        tf.pack(fill="both", expand=True, padx=20, pady=8)

        total = 0
        for i, it in enumerate(items):
            tree.insert("", "end", values=(
                it["codigo"] or "", it["nombre"], it["cantidad"],
                fmt_money(it["precio_unit"]), fmt_money(it["subtotal"])
            ), tags=(row_tag(i),))
            total += it["subtotal"]
        tree.tag_configure("odd",  background=C["card"])
        tree.tag_configure("even", background=C["surface"])

        make_label(w, f"Total:  {fmt_money(total)}", bg=C["bg"],
                   fg=C["success"], font=("Segoe UI", 14, "bold")).pack(pady=8)
        make_button(w, "Cerrar", w.destroy, color=C["border"]).pack(pady=(0,12))


class IngresosTab(tk.Frame):
    def __init__(self, parent, db: Database, app):
        super().__init__(parent, bg=C["bg"])
        self.db  = db
        self.app = app
        self._build()
        self.refresh_historial()

    def _build(self):
        left = make_frame(self, bg=C["bg"])
        left.pack(side="left", fill="both", expand=False, padx=(20,8), pady=12)
        left.configure(width=400)
        left.pack_propagate(False)

        hdr = make_frame(left, bg=C["bg"])
        hdr.pack(fill="x", pady=(0,10))
        make_label(hdr, "Ingreso de Mercadería", font=FONT_HEAD,
                bg=C["bg"], fg=C["white"]).pack(side="left")
        make_button(hdr, "➕ Nuevo producto", self._nuevo_producto,
            color=C["accent2"]).pack(side="right")

        fields_frame = make_frame(left, bg=C["surface"])
        fields_frame.pack(fill="x", pady=4)

        def lbl_entry(parent, label, var, row):
            make_label(parent, label, bg=C["surface"], font=FONT_SMALL).grid(
                row=row, column=0, sticky="w", padx=10, pady=4)
            e = make_entry(parent, textvariable=var, width=24)
            e.grid(row=row, column=1, padx=10, pady=4, ipady=4, sticky="ew")
            parent.columnconfigure(1, weight=1)

        # Producto search
        make_label(fields_frame, "Producto:", bg=C["surface"], font=FONT_SMALL).grid(
            row=0, column=0, sticky="w", padx=10, pady=4)
        self.ing_prod_var = tk.StringVar()
        self.ing_prod_var.trace("w", self._buscar_prod)
        make_entry(fields_frame, textvariable=self.ing_prod_var).grid(
            row=0, column=1, padx=10, pady=4, ipady=4, sticky="ew")

        self.ing_listbox = tk.Listbox(fields_frame, bg=C["card"], fg=C["text"], font=FONT_BODY,
                                      selectbackground=C["accent"], relief="flat", height=4)
        self.ing_listbox.grid(row=1, column=0, columnspan=2, padx=10, pady=(0,4), sticky="ew")
        self.ing_listbox.bind("<Double-1>", self._seleccionar_prod)
        self._ing_prods = []
        self._ing_pid   = None

        self.ing_cant_var = tk.StringVar(value="1")
        lbl_entry(fields_frame, "Cantidad:", self.ing_cant_var, 2)

        self.ing_costo_var = tk.StringVar(value="0")
        lbl_entry(fields_frame, "Costo unitario $:", self.ing_costo_var, 3)

        self.ing_prov_var = tk.StringVar()
        lbl_entry(fields_frame, "Proveedor:", self.ing_prov_var, 4)

        self.ing_obs_var = tk.StringVar()
        lbl_entry(fields_frame, "Observación:", self.ing_obs_var, 5)

        make_button(left, " ✅ REGISTRAR INGRESO", self._registrar,
                    color=C["success"]).pack(fill="x", pady=12)

        # ── Derecha: historial ──────────────
        right = make_frame(self, bg=C["bg"])
        right.pack(side="right", fill="both", expand=True, padx=(8,20), pady=12)

        make_label(right, "Historial de Ingresos", font=FONT_HEAD,
                   bg=C["bg"], fg=C["white"]).pack(anchor="w", pady=(0,8))

        ff = make_frame(right, bg=C["surface"])
        ff.pack(fill="x", pady=4)
        make_label(ff, "Desde:", bg=C["surface"], font=FONT_SMALL).pack(side="left", padx=(10,4), pady=8)
        self.ing_desde = tk.StringVar(value=date.today().strftime("%Y-%m-01"))
        make_entry(ff, textvariable=self.ing_desde, width=12).pack(side="left", ipady=3, pady=8)
        make_label(ff, "  Hasta:", bg=C["surface"], font=FONT_SMALL).pack(side="left", padx=4)
        self.ing_hasta = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        make_entry(ff, textvariable=self.ing_hasta, width=12).pack(side="left", ipady=3, pady=8)
        make_button(ff, "🔍 Filtrar", self.refresh_historial, color=C["accent"]).pack(side="left", padx=10)

        hf, self.hist_tree = scrollable_tree(
            right,
            ("fecha","producto","cantidad","costo","proveedor","obs"),
            ("Fecha","Producto","Cantidad","Costo unit.","Proveedor","Observación"),
            (155, 200, 80, 100, 140, 160)
        )
        hf.pack(fill="both", expand=True)

    def _nuevo_producto(self):
        cats = [c["nombre"] for c in self.db.get_categorias()]
        fields = [
            ("Nombre *",            "nombre",       "text",     ),
            ("Descripción",         "descripcion",  "text_area",),
            ("Categoría",           "categoria_id", "combo", cats),
            ("Precio costo",        "precio_costo", "float",    ),
            ("Precio venta",        "precio_venta", "float",    ),
            ("Stock mínimo",        "stock_min",    "int",      ),
            ("Tamaño",              "tamaño",       "text",     ),
        ]
        dlg = FormDialog(self, "Nuevo Producto", fields)
        if dlg.result:
            r = dlg.result
            if not r.get("nombre"):
                messagebox.showwarning("Error", "El nombre es obligatorio.")
                return
            cat_id = None
            for c in self.db.get_categorias():
                if c["nombre"] == r.get("categoria_id", ""):
                    cat_id = c["id"]; break
            try:
                self.db.add_producto({
                    "nombre":       r["nombre"],
                    "descripcion":  r["descripcion"],
                    "categoria_id": cat_id,
                    "precio_costo": float(r["precio_costo"] or 0),
                    "precio_venta": float(r["precio_venta"] or 0),
                    "stock":        0,
                    "stock_min":    int(r["stock_min"] or 5),
                    "tamaño":       r["tamaño"] or "tamaño",
                })
                self.app.productos_tab.refresh()
                self.app.dashboard.refresh()
                messagebox.showinfo("✅ Producto creado", f"'{r['nombre']}' agregado. Ahora podés registrar el ingreso.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def _buscar_prod(self, *_):
        q = self.ing_prod_var.get()
        self.ing_listbox.delete(0, "end")
        self._ing_prods = []
        if len(q) < 1:
            return
        prods = self.db.get_productos(buscar=q)[:10]
        for p in prods:
            self.ing_listbox.insert("end", f"{p['nombre']}  [{p['stock']}] {fmt_money(p['precio_venta'])}") 
            self._ing_prods.append(p)

    def _seleccionar_prod(self, _=None):
        sel = self.ing_listbox.curselection()
        if not sel:
            return
        p = self._ing_prods[sel[0]]
        self.ing_prod_var.set(p["nombre"])
        self.ing_costo_var.set(str(p["precio_costo"]))
        self._ing_pid = p["id"]
        self.ing_listbox.delete(0, "end")

    def _registrar(self):
        if not self._ing_pid:
            messagebox.showwarning("Atención", "Seleccioná un producto de la lista.")
            return
        try:
            cant  = int(self.ing_cant_var.get())
            costo = float(self.ing_costo_var.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Cantidad y costo deben ser numéricos.")
            return
        if cant <= 0:
            messagebox.showwarning("Atención", "La cantidad debe ser mayor a 0.")
            return
        prov = self.ing_prov_var.get()
        obs  = self.ing_obs_var.get()
        self.db.nuevo_ingreso(self._ing_pid, cant, costo, prov, obs)
        self.db.update_producto(self._ing_pid, {
            "precio_costo": costo,
            "precio_estimado": round(costo * 1.30 , 2),
        })
        messagebox.showinfo("✅ Ingreso registrado", f"Se agregaron {cant} unidades al stock.")
        # Reset
        self.ing_prod_var.set("")
        self.ing_cant_var.set("1")
        self.ing_costo_var.set("0")
        self.ing_prov_var.set("")
        self.ing_obs_var.set("")
        self._ing_pid = None
        self.refresh_historial()
        self.app.dashboard.refresh()
        self.app.productos_tab.refresh()

    def refresh_historial(self):
        desde = self.ing_desde.get() if hasattr(self, "ing_desde") else None
        hasta = self.ing_hasta.get() if hasattr(self, "ing_hasta") else None
        for row in self.hist_tree.get_children():
            self.hist_tree.delete(row)
        for i, ing in enumerate(self.db.get_ingresos(desde, hasta)):
            self.hist_tree.insert("", "end", values=(
                ing["fecha"], ing["producto"], ing["cantidad"],
                fmt_money(ing["costo_unit"]), ing["proveedor"] or "", ing["observacion"] or ""
            ), tags=(row_tag(i),))
        self.hist_tree.tag_configure("odd",  background=C["card"])
        self.hist_tree.tag_configure("even", background=C["surface"])


class ReportesTab(tk.Frame):
    def __init__(self, parent, db: Database, app):
        super().__init__(parent, bg=C["bg"])
        self.db  = db
        self.app = app
        self._build()
        self.refresh()

    def _build(self):
        make_label(self, "Reportes y Estadísticas", font=FONT_HEAD,
                   bg=C["bg"], fg=C["white"]).pack(padx=20, pady=(16,10), anchor="w")

        # Botones de reporte
        btns = make_frame(self, bg=C["bg"])
        btns.pack(fill="x", padx=20, pady=4)
        make_button(btns, "📊 Ventas por día (30d)", self._reporte_ventas_dia, color=C["accent"]).pack(side="left", padx=4)
        make_button(btns, "📦 Top productos vendidos", self._reporte_top_prods, color=C["accent2"]).pack(side="left", padx=4)
        make_button(btns, "⚠️ Bajo stock", self._reporte_bajo_stock, color=C["warning"]).pack(side="left", padx=4)
        make_button(btns, "📋 Exportar CSV", self._exportar_csv, color=C["success"]).pack(side="right", padx=4)

        # Tabla principal
        self.tree_frame = make_frame(self, bg=C["bg"])
        self.tree_frame.pack(fill="both", expand=True, padx=20, pady=12)

        self._current_report = "ventas_dia"
        self._build_ventas_dia_tree()

    def _clear_tree(self):
        for w in self.tree_frame.winfo_children():
            w.destroy()

    def _build_ventas_dia_tree(self):
        self._clear_tree()
        tf, self.rep_tree = scrollable_tree(
            self.tree_frame,
            ("dia","total","cantidad"),
            ("Día","Total ventas","Cantidad transacciones"),
            (160, 180, 200)
        )
        tf.pack(fill="both", expand=True)
        self._current_report = "ventas_dia"
        self.refresh()

    def _build_top_prods_tree(self):
        self._clear_tree()
        tf, self.rep_tree = scrollable_tree(
            self.tree_frame,
            ("nombre","vendido","ingresos"),
            ("Producto","Unidades vendidas","Total ingresos"),
            (280, 160, 160)
        )
        tf.pack(fill="both", expand=True)
        self._current_report = "top_prods"
        self.refresh()

    def _build_bajo_stock_tree(self):
        self._clear_tree()
        tf, self.rep_tree = scrollable_tree(
            self.tree_frame,
            ("codigo","nombre","categoria","stock","stock_min"),
            ("Código","Nombre","Categoría","Stock actual","Stock mínimo"),
            (90, 220, 120, 100, 100)
        )
        tf.pack(fill="both", expand=True)
        self._current_report = "bajo_stock"
        self.refresh()

    def _reporte_ventas_dia(self):
        self._build_ventas_dia_tree()

    def _reporte_top_prods(self):
        self._build_top_prods_tree()

    def _reporte_bajo_stock(self):
        self._build_bajo_stock_tree()

    def refresh(self):
        if not hasattr(self, "rep_tree"):
            return
        for row in self.rep_tree.get_children():
            self.rep_tree.delete(row)

        if self._current_report == "ventas_dia":
            for i, r in enumerate(self.db.ventas_por_dia(30)):
                self.rep_tree.insert("", "end", values=(
                    r["dia"], fmt_money(r["total"]), r["cantidad"]
                ), tags=(row_tag(i),))

        elif self._current_report == "top_prods":
            for i, r in enumerate(self.db.top_productos_vendidos(20)):
                self.rep_tree.insert("", "end", values=(
                    r["nombre"], r["total_vendido"], fmt_money(r["total_ingresos"])
                ), tags=(row_tag(i),))

        elif self._current_report == "bajo_stock":
            for i, p in enumerate(self.db.get_productos(solo_bajo_stock=True)):
                self.rep_tree.insert("", "end", values=(
                    p["id"], p["nombre"], p["categoria"] or "—",
                    p["stock"], p["stock_min"]
                ), tags=(row_tag(i),))

        self.rep_tree.tag_configure("odd",  background=C["card"])
        self.rep_tree.tag_configure("even", background=C["surface"])

    def _exportar_csv(self):
        import csv
        try:
            fname = f"reporte_{self._current_report}_{date.today().strftime('%Y%m%d')}.csv"
            fpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
            cols = [self.rep_tree.heading(c)["text"] for c in self.rep_tree["columns"]]
            with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for iid in self.rep_tree.get_children():
                    w.writerow(self.rep_tree.item(iid, "values"))
            messagebox.showinfo("✅ Exportado", f"Archivo guardado:\n{fpath}")
        except Exception as e:
            messagebox.showerror("Error", str(e))


# ─────────────────────────────────────────
#  APLICACIÓN PRINCIPAL
# ─────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  —  Sistema de Gestión de Stock")
        self.configure(bg=C["bg"])
        try:
            self.iconbitmap("logo.ico")
        except Exception:
            pass
        self.geometry("1280x780")
        self.minsize(900, 600)

        configure_styles()

        # 1) Traer la base del pendrive a la PC antes de abrir nada
        ok, msg = sincronizar_desde_pendrive()
        if not ok:
            messagebox.showerror("Error al sincronizar", msg)
        elif msg.startswith("⚠️"):
            messagebox.showwarning("Aviso", msg)

        # 2) Trabajar siempre sobre la copia local (rápida y segura)
        self.db = Database(DB_FILE)

        self._build_sidebar()
        self._build_content()
        self._build_tabs()
        self._select_tab("dashboard")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 3) Guardado automático periódico hacia el pendrive (silencioso)
        self.after(AUTOSAVE_MS, self._autosave_periodico)

    def _autosave_periodico(self):
        ok, msg = guardar_hacia_pendrive(silencioso=True)
        if not ok:
            print("Autosave:", msg)
        self.after(AUTOSAVE_MS, self._autosave_periodico)

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=C["surface"], width=190)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # Logo / nombre
        logo = tk.Frame(sb, bg=C["accent"], height=64)
        logo.pack(fill="x")
        logo.pack_propagate(False)
        tk.Label(logo, text="Barril&Barrica", bg=C["accent"], fg=C["white"],
                 font=("Segoe UI", 16, "bold")).pack(expand=True)

        # DB path
        db_name = os.path.basename(REMOTE_DB_FILE)
        tk.Label(sb, text=f"📁 {db_name}  (trabajando en copia local)", bg=C["surface"], fg=C["subtext"],
                 font=FONT_SMALL, wraplength=170, justify="left").pack(pady=(10,6), padx=10)

        tk.Button(sb, text="💾 Guardar ahora", command=self._guardar_ahora,
                  bg=C["success"], fg=C["white"], font=FONT_SMALL,
                  relief="flat", cursor="hand2", pady=4).pack(fill="x", padx=10, pady=(0,6))

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=12, pady=4)

        # Nav buttons
        self._nav_btns = {}
        nav_items = [
            ("dashboard",        "🏠  Dashboard"),
            ("productos",        "📦  Productos"),
            ("nueva_venta",      "💰  Nueva Venta"),
            ("historial_ventas", "📋  Historial Ventas"),
            ("ingresos",         "📥  Ingresos"),
            ("reportes",         "📊  Reportes"),
        ]
        for key, label in nav_items:
            btn = tk.Button(sb, text=label, command=lambda k=key: self._select_tab(k),
                            bg=C["surface"], fg=C["text"], font=FONT_BODY,
                            relief="flat", anchor="w", padx=20, pady=10,
                            activebackground=C["accent"], activeforeground=C["white"],
                            cursor="hand2")
            btn.pack(fill="x", padx=0)
            self._nav_btns[key] = btn

        # Footer
        tk.Frame(sb, bg=C["bg"]).pack(expand=True)
        tk.Label(sb, text="v1.0 • SQLite local", bg=C["surface"],
                 fg=C["subtext"], font=FONT_SMALL).pack(pady=12)

    def _guardar_ahora(self):
        ok, msg = guardar_hacia_pendrive()
        if ok:
            messagebox.showinfo("✅ Guardado", msg)
        else:
            messagebox.showwarning("No se pudo guardar", msg)

    def _build_content(self):
        self.content = tk.Frame(self, bg=C["bg"])
        self.content.pack(side="right", fill="both", expand=True)

    def _build_tabs(self):
        self.dashboard           = DashboardTab(self.content, self.db, self)
        self.productos_tab       = ProductosTab(self.content, self.db, self)
        self.nueva_venta_tab     = NuevaVentaTab(self.content, self.db, self)
        self.historial_ventas_tab = HistorialVentasTab(self.content, self.db, self)
        self.ingresos_tab        = IngresosTab(self.content, self.db, self)
        self.reportes_tab        = ReportesTab(self.content, self.db, self)

        self._tabs = {
            "dashboard":        self.dashboard,
            "productos":        self.productos_tab,
            "nueva_venta":      self.nueva_venta_tab,
            "historial_ventas": self.historial_ventas_tab,
            "ingresos":         self.ingresos_tab,
            "reportes":         self.reportes_tab,
        }

    def _select_tab(self, key):
        for k, tab in self._tabs.items():
            tab.pack_forget()
        self._tabs[key].pack(fill="both", expand=True)
        self._current_tab = key

        for k, btn in self._nav_btns.items():
            btn.configure(bg=C["accent"] if k == key else C["surface"],
                          fg=C["white"] if k == key else C["text"])

        # Refresh al entrar
        if key == "dashboard":
            self.dashboard.refresh()
        elif key == "historial_ventas":
            self.historial_ventas_tab.refresh_historial()
        elif key == "reportes":
            self.reportes_tab.refresh()

    def _on_close(self):
        self.db.close()
        ok, msg = guardar_hacia_pendrive()
        if not ok:
            messagebox.showwarning(
                "No se pudo guardar en el pendrive",
                f"{msg}\n\nVolvé a conectar el pendrive y usá 'Guardar ahora' "
                f"o copiá manualmente el archivo:\n{LOCAL_DB_FILE}"
            )
        self.destroy()


# ─────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────
if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        import traceback
        with open("error_log.txt", "w") as f:
            f.write(traceback.format_exc())
        input(f"ERROR: {e}\nPresioná Enter para cerrar...")
