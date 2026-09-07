"""Telegram presentation layer for Historical Bloodlines.

Keep this package initializer intentionally lightweight. Utility modules such as
``vless`` are used directly on a bare VPS Python installation and must not pull
in renderer dependencies (openpyxl, Graphviz, Cairo, etc.) merely because the
package was imported.
"""
