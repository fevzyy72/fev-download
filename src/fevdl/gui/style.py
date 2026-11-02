"""Erscheinungsbild "Sammelmappe": Creme, Tinte, ein Blau.

Werte aus der Vorlage design/looks2 (Konzept D). Das Blau ist die einzige
Akzentfarbe: Es markiert Auswahl, Fokus und die eine Hauptaktion. Flaechen sind
flach, Konturen 1 px, keine Schatten. Kennzeichen der Gestaltung ist die
angeschnittene Ecke oben rechts (Zettel, Hauptaktion).

Selbst gezeichnete Bedienelemente (widgets.py, trim_bar.py) lesen die Farben
hier; das Stylesheet unten deckt nur noch Standard-Widgets ab.

Kontraste (WCAG, gegen BG): INK 11,1:1 · MUTED 5,0:1 · ACCENT 7,0:1 ·
ERROR 5,4:1 · MUTED auf COLLECTION 4,6:1.
"""

# -- Palette ---------------------------------------------------------------

BG = "#f3efe5"           # Grundflaeche, Quelle
COLLECTION = "#e9e6dc"   # Sammelmappe - eine Spur dunkler, wie ein Ablagefach
SURFACE = "#fffcf5"      # Zettel, Felder, Karten
INK = "#2a344b"
MUTED = "#606777"
LINE = "#bebcb2"
LINE_SOFT = "#d6d3c8"
ACCENT = "#344fad"
ON_ACCENT = "#ffffff"
TINT = "#e0e5f6"
HOVER = "#e7e6e2"
PRESS = "#cbd4f0"
ACCENT_HOVER = "#263f98"
ACCENT_PRESS = "#20357f"
DISABLED = "#e6e3db"
DIM = "#7d7e7b"
WAVE = "#737e9a"
WAVE_BG = "#f4f1e8"
ERROR = "#ad3340"
STAGE = "#121614"        # Videoflaeche - Bewegtbild braucht dunklen Grund
STAGE_TEXT = "#c4c8cf"   # 10:1 auf STAGE

# Masse
RADIUS_CORNER = 12       # angeschnittene Ecke kleiner Flaechen
RADIUS_ACTION = 18       # Hauptaktion


STYLESHEET = f"""
/* Schriftgroessen stehen bewusst NICHT hier (siehe typography.py). */

QMainWindow, QDialog, QMessageBox, QProgressDialog {{
    background-color: {BG};
    color: {INK};
}}

QWidget {{
    color: {INK};
}}

QWidget#page, QWidget#sourceColumn, QWidget#sourceBody, QWidget#emptyView,
QWidget#libraryPage, QWidget#libraryBody {{
    background-color: {BG};
}}

QWidget#collection, QWidget#collectionBody {{
    background-color: {COLLECTION};
}}

QWidget#navRail {{
    background-color: {BG};
    border-right: 1px solid {LINE};
}}

QWidget#sourceColumn {{
    border-right: 1px solid {LINE};
}}

/* Beschriftungen erben sonst den Fensterhintergrund und zeichnen ihn als
   sichtbaren Balken auf die Zettel. */
QLabel {{
    background: transparent;
}}

QLabel#muted {{ color: {MUTED}; }}
QLabel#error {{ color: {ERROR}; }}
QLabel#accentText {{ color: {ACCENT}; }}
QLabel#live {{ color: {ERROR}; }}

QLabel#resolveNote {{
    color: {ACCENT};
    background-color: {TINT};
    border-left: 2px solid {ACCENT};
    padding: 6px 10px;
}}

QLabel#thumbnail {{
    background-color: {DISABLED};
    border: 1px solid {LINE_SOFT};
}}

QLabel#placeholder {{
    background-color: {STAGE};
    color: {STAGE_TEXT};
    padding: 16px;
}}

QFrame#rule {{
    background-color: {LINE};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

/* Der Zettel: Creme auf dem Ablagefach, eine angeschnittene Ecke. */
QFrame#slip {{
    background-color: {SURFACE};
    border: 1px solid {LINE};
    border-top-right-radius: {RADIUS_CORNER}px;
}}

QFrame#slipRule {{
    background-color: {LINE_SOFT};
    border: none;
    max-height: 1px;
    min-height: 1px;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {LINE};
    min-height: 32px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: {DIM};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* -- Eingaben: offene Felder mit Grundlinie ---------------------------- */

QLineEdit {{
    background-color: {SURFACE};
    border: none;
    border-bottom: 2px solid {LINE};
    padding: 6px 10px;
    color: {INK};
    selection-background-color: {TINT};
    selection-color: {INK};
}}

QLineEdit:hover {{
    border-bottom-color: {DIM};
}}

QLineEdit:focus {{
    border-bottom-color: {ACCENT};
}}

QLineEdit:disabled {{
    background-color: {DISABLED};
    color: {DIM};
    border-bottom-color: {DISABLED};
}}

QLineEdit#linkEdit {{
    padding: 8px 12px;
}}

QLineEdit#linkHero {{
    padding: 14px 12px;
}}

QLineEdit#timecode {{
    background-color: transparent;
    border-bottom: 1px solid {LINE};
    padding: 4px 2px;
}}

QLineEdit#timecode:hover {{
    border-bottom-color: {ACCENT};
}}

QLineEdit#timecode:focus {{
    border: 2px solid {ACCENT};
    background-color: {SURFACE};
}}

QLineEdit#search {{
    background-color: transparent;
    border-bottom: 1px solid {LINE};
    padding: 6px 4px;
}}

QLineEdit#search:focus {{
    border-bottom: 2px solid {ACCENT};
}}

/* Der Pfeil wird bewusst nicht selbst gezeichnet - eigene Regeln fuer
   ::down-arrow haben bei QComboBox die Textdarstellung zerstoert. */
QComboBox {{
    background-color: transparent;
    border: 1px solid transparent;
    border-bottom: 1px solid {LINE};
    padding: 5px 8px;
    color: {INK};
}}

QComboBox:hover {{
    background-color: {HOVER};
}}

QComboBox:focus {{
    border: 2px solid {ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {LINE};
    padding: 4px;
    selection-background-color: {TINT};
    selection-color: {INK};
    outline: none;
}}

/* -- Menue (hinter dem Menuesymbol) ------------------------------------ */

QMenu {{
    background-color: {SURFACE};
    border: 1px solid {LINE};
    padding: 6px;
}}

QMenu::item {{
    padding: 7px 34px 7px 12px;
    color: {INK};
}}

QMenu::item:selected {{
    background-color: {TINT};
    color: {ACCENT};
}}

QMenu::item:disabled {{
    color: {DIM};
}}

QMenu::separator {{
    height: 1px;
    background-color: {LINE_SOFT};
    margin: 5px 6px;
}}

/* -- Dialoge (Aktualisierung, Hinweise) ------------------------------- */

QDialog QPushButton, QMessageBox QPushButton, QProgressDialog QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {LINE};
    padding: 7px 18px;
    min-width: 72px;
    color: {INK};
}}

QDialog QPushButton:hover, QMessageBox QPushButton:hover,
QProgressDialog QPushButton:hover {{
    background-color: {HOVER};
}}

QDialog QPushButton:pressed, QMessageBox QPushButton:pressed,
QProgressDialog QPushButton:pressed {{
    background-color: {PRESS};
}}

QDialog QPushButton:focus, QMessageBox QPushButton:focus,
QProgressDialog QPushButton:focus {{
    border: 2px solid {ACCENT};
}}

QDialog QPushButton:default, QMessageBox QPushButton:default {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: {ON_ACCENT};
    border-top-right-radius: 8px;
}}

QDialog QPushButton:default:hover, QMessageBox QPushButton:default:hover {{
    background-color: {ACCENT_HOVER};
}}

QProgressBar {{
    background-color: {LINE_SOFT};
    border: none;
    min-height: 4px;
    max-height: 4px;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {ACCENT};
}}

/* -- Spulleiste des Players ------------------------------------------- */

QSlider::groove:horizontal {{
    height: 2px;
    background: {LINE};
}}

QSlider::sub-page:horizontal {{
    background: {ACCENT};
}}

QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 10px;
    height: 10px;
    margin: -4px 0;
    border-radius: 5px;
}}

QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}

QSlider::handle:horizontal:disabled {{
    background: {DIM};
}}

QSlider::sub-page:horizontal:disabled {{
    background: {LINE};
}}

QSlider:focus {{
    border: 2px solid {ACCENT};
}}

/* -- Bibliothek ------------------------------------------------------- */

QTreeWidget#libraryTable {{
    background-color: transparent;
    border: none;
    color: {INK};
    outline: none;
}}

QTreeWidget#libraryTable:focus {{
    border: 2px solid {ACCENT};
}}

QToolTip {{
    background-color: {INK};
    color: {BG};
    border: none;
    padding: 6px 8px;
}}
"""
