"""Erscheinungsbild: warmes Monochrom, flach, viel Weissraum.

Farben sind hier eine knappe Ressource - sie tragen Bedeutung (Warnung,
Erfolg), nicht Dekoration. Keine Verlaeufe, keine Schlagschatten, ueberall
dieselbe 1px-Linie.
"""

# -- Palette ---------------------------------------------------------------

CANVAS = "#F7F6F3"        # warmes Knochenweiss
SURFACE = "#FFFFFF"
SURFACE_SUNK = "#FBFBFA"
BORDER = "#EAEAEA"
BORDER_STRONG = "#DDDCD8"

INK = "#111111"           # nie reines Schwarz fuer Flaechen, nur fuer Text
INK_MUTED = "#787774"
INK_FAINT = "#A5A29B"

STAGE = "#141414"         # Videoflaeche - Bewegtbild braucht dunklen Grund

PALE_RED_BG, PALE_RED_INK = "#FDEBEC", "#9F2F2D"
PALE_BLUE_BG, PALE_BLUE_INK = "#E1F3FE", "#1F6C9F"
PALE_GREEN_BG, PALE_GREEN_INK = "#EDF3EC", "#346538"
PALE_YELLOW_BG, PALE_YELLOW_INK = "#FBF3DB", "#956400"


STYLESHEET = f"""
/* Schriftgroessen stehen bewusst NICHT hier: Angaben im Stylesheet haetten
   Vorrang vor setFont() und wuerden die Laufweite aus typography.py
   aushebeln. Das Stylesheet regelt nur Farbe, Rahmen und Abstand. */

QMainWindow, QWidget {{
    background-color: {CANVAS};
    color: {INK};
}}

/* Beschriftungen erben sonst den Fensterhintergrund und zeichnen ihn als
   sichtbaren Balken auf die weissen Karten. */
QLabel {{
    background: transparent;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: #D8D6D1;
    border-radius: 5px;
    min-height: 32px;
}}

QScrollBar::handle:vertical:hover {{
    background: #BFBDB7;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* -- Menueleiste ------------------------------------------------------ */

QMenuBar {{
    background-color: {CANVAS};
    border-bottom: 1px solid {BORDER};
    padding: 2px 6px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
    color: {INK_MUTED};
}}

QMenuBar::item:selected {{
    background-color: {SURFACE};
    color: {INK};
}}

QMenu {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
}}

QMenu::item {{
    padding: 7px 28px 7px 14px;
    border-radius: 4px;
    color: {INK};
}}

QMenu::item:selected {{
    background-color: {CANVAS};
}}

QMenu::item:disabled {{
    color: {INK_FAINT};
}}

QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 6px 8px;
}}

/* -- Textbausteine ---------------------------------------------------- */

QLabel#hero {{
    color: {INK};
}}

QLabel#subtitle, QLabel#muted {{
    color: {INK_MUTED};
}}

QLabel#eyebrow {{
    color: {INK_FAINT};
}}

QLabel#error {{
    color: {PALE_RED_INK};
}}

QLabel#banner {{
    background-color: {PALE_GREEN_BG};
    color: {PALE_GREEN_INK};
    border: 1px solid #DDE7DC;
    border-radius: 6px;
    padding: 9px 12px;
}}

QLabel#title {{
    color: {INK};
}}

QLabel#tag {{
    background-color: {PALE_BLUE_BG};
    color: {PALE_BLUE_INK};
    border-radius: 9px;
    padding: 3px 10px;
}}

QLabel#tagLive {{
    background-color: {PALE_RED_BG};
    color: {PALE_RED_INK};
    border-radius: 9px;
    padding: 3px 10px;
}}

QFrame#rule {{
    background-color: {BORDER};
    max-height: 1px;
    border: none;
}}

/* Die Fusszeile sitzt fest am unteren Rand, ausserhalb des Rollbereichs. */
QWidget#footer {{
    background-color: {CANVAS};
    border-top: 1px solid {BORDER};
}}

/* -- Flaechen --------------------------------------------------------- */

QFrame#card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QFrame#libraryEmpty {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QLabel#thumbnail {{
    background-color: {SURFACE_SUNK};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}

QLabel#placeholder {{
    background-color: {STAGE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: #8A8A85;
}}

/* -- Eingaben --------------------------------------------------------- */

QLineEdit, QComboBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 9px 12px;
    color: {INK};
    selection-background-color: {INK};
    selection-color: {SURFACE};
}}

QLineEdit:focus, QComboBox:focus {{
    border-color: {INK};
}}

QLineEdit:disabled, QComboBox:disabled {{
    background-color: {SURFACE_SUNK};
    color: {INK_FAINT};
}}

QLineEdit#timecode {{
    padding: 7px 8px;
}}

/* Der Pfeil wird bewusst nicht selbst gezeichnet - eigene Regeln fuer
   ::down-arrow haben bei QComboBox die Textdarstellung zerstoert. */
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {CANVAS};
    selection-color: {INK};
    outline: none;
}}

/* -- Schaltflaechen --------------------------------------------------- */

QPushButton {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 8px 14px;
    color: {INK};
}}

QPushButton:hover {{
    background-color: {CANVAS};
}}

QPushButton:pressed {{
    background-color: {BORDER};
}}

QPushButton:disabled {{
    color: {INK_FAINT};
    border-color: {BORDER};
    background-color: {SURFACE_SUNK};
}}

QPushButton#primary {{
    background-color: {INK};
    border: 1px solid {INK};
    color: {SURFACE};
    font-weight: 600;
    padding: 9px 20px;
}}

QPushButton#primary:hover {{
    background-color: #333333;
    border-color: #333333;
}}

QPushButton#primary:disabled {{
    background-color: #C9C7C1;
    border-color: #C9C7C1;
    color: {SURFACE};
}}

QPushButton#quiet {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {INK_MUTED};
    padding: 8px 10px;
}}

QPushButton#quiet:hover {{
    color: {INK};
    border-color: {BORDER};
    background-color: {SURFACE};
}}

/* Die Navigation bleibt ruhig, ist aber eindeutig als Navigation erkennbar. */
QPushButton#nav, QPushButton#navActive {{
    border-radius: 5px;
    padding: 7px 13px;
}}

QPushButton#nav {{
    background-color: transparent;
    border-color: transparent;
    color: {INK_MUTED};
}}

QPushButton#nav:hover {{
    background-color: {SURFACE};
    border-color: {BORDER};
    color: {INK};
}}

QPushButton#navActive {{
    background-color: {INK};
    border-color: {INK};
    color: {SURFACE};
    font-weight: 600;
}}

/* Ausschnitt-Aktionen bekommen eigene, gedeckte Farben. So wirken sie wie
   echte Knoepfe und lassen sich trotzdem semantisch unterscheiden. */
QPushButton#trimMark {{
    background-color: {PALE_BLUE_BG};
    border-color: #CFE6F3;
    color: {PALE_BLUE_INK};
    font-weight: 600;
}}

QPushButton#trimMark:hover {{
    background-color: #D5EDFA;
    border-color: #BBDCEA;
}}

QPushButton#trimReset {{
    background-color: {PALE_YELLOW_BG};
    border-color: #EEE4C9;
    color: {PALE_YELLOW_INK};
    font-weight: 600;
}}

QPushButton#trimReset:hover {{
    background-color: #F7ECCB;
    border-color: #E6D8B5;
}}

/* Das Merken eines Ausschnitts legt etwas an - dieselbe Farbe wie die anderen
   Aktionen, die wirklich etwas erzeugen. */
QPushButton#waveformAction, QPushButton#resolveAction, QPushButton#trimAdd {{
    background-color: {PALE_GREEN_BG};
    border-color: #D9E5D7;
    color: {PALE_GREEN_INK};
    font-weight: 600;
}}

QPushButton#waveformAction:hover, QPushButton#resolveAction:hover,
QPushButton#trimAdd:hover {{
    background-color: #E2ECDD;
    border-color: #CBDCC8;
}}

QPushButton#softAction {{
    background-color: {PALE_BLUE_BG};
    border-color: #CFE6F3;
    color: {PALE_BLUE_INK};
}}

QPushButton#softAction:hover {{
    background-color: #D5EDFA;
    border-color: #BBDCEA;
}}

QPushButton#trimMark:disabled, QPushButton#trimReset:disabled,
QPushButton#waveformAction:disabled, QPushButton#resolveAction:disabled,
QPushButton#softAction:disabled, QPushButton#trimAdd:disabled {{
    background-color: {SURFACE_SUNK};
    border-color: {BORDER};
    color: {INK_FAINT};
}}

/* -- Gemerkte Ausschnitte --------------------------------------------- */

QListWidget#segmentList {{
    background-color: {SURFACE_SUNK};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 3px;
    color: {INK};
    outline: none;
}}

QListWidget#segmentList::item {{
    padding: 5px 8px;
    border-radius: 4px;
    color: {INK_MUTED};
}}

QListWidget#segmentList::item:selected {{
    background-color: {PALE_BLUE_BG};
    color: {PALE_BLUE_INK};
}}

QListWidget#segmentList::item:hover:!selected {{
    background-color: {SURFACE};
}}

/* -- Bibliothek ------------------------------------------------------- */

QLabel#libraryCount {{
    color: {INK};
}}

QTreeWidget#libraryTable {{
    background-color: {SURFACE};
    alternate-background-color: {SURFACE_SUNK};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {INK};
    outline: none;
}}

QTreeWidget#libraryTable::item {{
    border-bottom: 1px solid {BORDER};
    padding: 10px 8px;
}}

QTreeWidget#libraryTable::item:selected {{
    background-color: {PALE_BLUE_BG};
    color: {INK};
}}

QTreeWidget#libraryTable::item:hover:!selected {{
    background-color: {SURFACE_SUNK};
}}

QHeaderView::section {{
    background-color: {CANVAS};
    color: {INK_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 9px 8px;
}}

QLineEdit#librarySearch {{
    background-color: {SURFACE_SUNK};
}}

/* -- Kontrollkaestchen ------------------------------------------------ */

QCheckBox {{
    spacing: 9px;
    color: {INK_MUTED};
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 3px;
    background-color: {SURFACE};
}}

QCheckBox::indicator:checked {{
    background-color: {INK};
    border-color: {INK};
}}

/* -- Fortschritt ------------------------------------------------------ */

QProgressBar {{
    background-color: {BORDER};
    border: none;
    border-radius: 1px;
}}

QProgressBar::chunk {{
    background-color: {INK};
    border-radius: 1px;
}}

/* -- Schieberegler des Players ---------------------------------------- */

QSlider::groove:horizontal {{
    height: 3px;
    background: {BORDER};
    border-radius: 1px;
}}

QSlider::sub-page:horizontal {{
    background: {INK};
    border-radius: 1px;
}}

QSlider::handle:horizontal {{
    background: {INK};
    width: 11px;
    height: 11px;
    margin: -4px 0;
    border-radius: 5px;
}}

QSlider::handle:horizontal:disabled {{
    background: {INK_FAINT};
}}

QToolTip {{
    background-color: {INK};
    color: {SURFACE};
    border: none;
    border-radius: 4px;
    padding: 7px 9px;
}}
"""
