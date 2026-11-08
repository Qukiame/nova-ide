#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nova IDE — красивая лёгкая IDE на PySide6.
Тёмная тема, вкладки, файловое дерево, подсветка синтаксиса,
нумерация строк, поиск/замена, запуск Python.
"""

import os
import re
import sys
import subprocess
import platform

from PySide6.QtCore import (
    Qt, QRect, QSize
)
from PySide6.QtGui import (
    QAction, QColor, QTextFormat, QPainter, QFont, QKeySequence,
    QPalette, QTextCursor, QSyntaxHighlighter,
    QTextCharFormat, QShortcut
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTreeView, QTabWidget, QPlainTextEdit, QLabel, QFileDialog,
    QMessageBox, QLineEdit, QPushButton, QToolBar, QStatusBar,
    QSplitter, QFrame, QFileSystemModel, QTextEdit
)

# ---------- Палитра (тёмная тема "Nova") ----------
C_BG          = "#0d1117"
C_BG_ALT      = "#161b22"
C_BG_HOVER    = "#1f2630"
C_BORDER      = "#21262d"
C_TEXT        = "#c9d1d9"
C_TEXT_DIM    = "#8b949e"
C_ACCENT      = "#58a6ff"
C_ACCENT_2    = "#7ee787"
C_WARN        = "#f0883e"
C_ERROR       = "#ff7b72"
C_KEYWORD     = "#ff7b72"
C_BUILTIN     = "#d2a8ff"
C_STRING      = "#a5d6ff"
C_COMMENT     = "#8b949e"
C_NUMBER      = "#79c0ff"
C_OPERATOR    = "#ff7b72"
C_FUNC        = "#d2a8ff"
C_CLASS       = "#ffa657"
C_DECORATOR   = "#7ee787"
C_CURRENT     = "#161b22"


# ---------- Номера строк ----------
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


# ---------- Редактор кода ----------
class CodeEditor(QPlainTextEdit):
    def __init__(self, filepath=None, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        # Шрифт
        font = None
        for name in ["JetBrains Mono", "Fira Code", "Menlo", "Consolas",
                     "DejaVu Sans Mono", "Monospace"]:
            f = QFont(name, 10)
            if f.exactMatch() or name == "DejaVu Sans Mono":
                font = f
                break
        if font is None:
            font = QFont("Monospace", 10)
        self.setFont(font)

        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        p = self.palette()
        p.setColor(QPalette.Base, QColor(C_BG))
        p.setColor(QPalette.Text, QColor(C_TEXT))
        p.setColor(QPalette.Highlight, QColor(C_ACCENT))
        p.setColor(QPalette.HighlightedText, QColor(C_BG))
        self.setPalette(p)

        self.setTabStopDistance(self.fontMetrics().horizontalAdvance("    "))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFrameStyle(QFrame.NoFrame)

        self.highlighter = None
        self.set_highlighter_for(filepath)

    def set_highlighter_for(self, filepath):
        if not filepath:
            self.highlighter = PythonHighlighter(self.document())
            return
        ext = os.path.splitext(filepath)[1].lower()
        hmap = {
            ".py": PythonHighlighter,
            ".js": JsHighlighter, ".mjs": JsHighlighter, ".ts": JsHighlighter,
            ".html": HtmlHighlighter, ".htm": HtmlHighlighter,
            ".css": CssHighlighter,
            ".json": JsonHighlighter,
            ".c": CppHighlighter, ".cpp": CppHighlighter,
            ".h": CppHighlighter, ".hpp": CppHighlighter,
            ".sh": ShHighlighter, ".bash": ShHighlighter,
            ".md": MarkdownHighlighter,
        }
        cls = hmap.get(ext)
        self.highlighter = cls(self.document()) if cls else None

    def line_number_area_width(self):
        digits = max(1, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self.line_number_area_width(), cr.height())
        )

    def highlight_current_line(self):
        extra = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor(C_CURRENT))
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            extra.append(sel)
        self.setExtraSelections(extra)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(C_BG_ALT))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current_block = self.textCursor().blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_block:
                    painter.setPen(QColor(C_ACCENT))
                else:
                    painter.setPen(QColor(C_TEXT_DIM))
                painter.drawText(
                    0, top, self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    # Поиск/замена
    def find(self, text):
        if not text:
            return False
        c = self.textCursor()
        doc = self.document()
        cursor = doc.find(text, c)
        if cursor.isNull():
            # с начала
            c.movePosition(QTextCursor.Start)
            cursor = doc.find(text, c)
        if not cursor.isNull():
            self.setTextCursor(cursor)
            return True
        return False

    def replace(self, ftext, rtext):
        c = self.textCursor()
        if c.hasSelection() and c.selectedText() == ftext:
            c.insertText(rtext)
        self.find(ftext)

    def replace_all(self, ftext, rtext):
        c = self.textCursor()
        c.movePosition(QTextCursor.Start)
        self.setTextCursor(c)
        count = 0
        while True:
            cursor = self.document().find(ftext, self.textCursor())
            if cursor.isNull():
                break
            cursor.insertText(rtext)
            self.setTextCursor(cursor)
            count += 1
            if count > 100000:
                break
        self.status_msg(f"Заменено: {count}" if hasattr(self, "status_msg") else None)


# ---------- Подсветка ----------
class HighlighterBase(QSyntaxHighlighter):
    def make(self, color, bold=False, italic=False):
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    def add_rules(self, rules):
        self.rules = [(re.compile(p), fmt) for p, fmt in rules]

    def highlightBlock(self, text):
        for pat, fmt in self.rules:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
        self.setCurrentBlockState(0)


class PythonHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        kw = ('def|class|return|if|elif|else|for|while|break|continue|'
              'import|from|as|try|except|finally|with|lambda|yield|'
              'global|nonlocal|pass|assert|del|in|is|not|and|or|raise|'
              'async|await|match|case')
        builtins = ('print|len|range|str|int|float|list|dict|set|tuple|'
                    'bool|None|True|False|self|super|type|isinstance|'
                    'enumerate|zip|map|filter|open|input|sum|min|max|abs|'
                    'sorted|reversed|any|all|format|repr|chr|ord|hex|oct|bin')
        rules = [
            (r'#.*$',                                self.make(C_COMMENT, italic=True)),
            (r'"[^"\\]*(\\.[^"\\]*)*"',              self.make(C_STRING)),
            (r"'[^'\\]*(\\.[^'\\]*)*'",              self.make(C_STRING)),
            (r'\b[fbruFBRU]{1,2}"[^"\\]*(\\.[^"\\]*)*"', self.make(C_STRING)),
            (r'\b(' + kw + r')\b',                   self.make(C_KEYWORD, bold=True)),
            (r'\b(' + builtins + r')\b',             self.make(C_BUILTIN)),
            (r'\b[A-Z_][A-Z0-9_]+\b',                self.make(C_CLASS)),
            (r'\b\d+\.?\d*([eE][+-]?\d+)?\b',        self.make(C_NUMBER)),
            (r'@[A-Za-z_][\w.]*',                    self.make(C_DECORATOR)),
            (r'\bdef\s+(\w+)',                       self.make(C_FUNC)),
            (r'\bclass\s+(\w+)',                     self.make(C_CLASS)),
            (r'[+\-*/%=<>!&|^~]+',                   self.make(C_OPERATOR)),
        ]
        self.add_rules(rules)


class JsHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        kw = ('var|let|const|function|return|if|else|for|while|do|break|'
              'continue|switch|case|default|try|catch|finally|throw|new|'
              'this|typeof|instanceof|in|of|class|extends|super|import|'
              'from|export|async|await|yield|void|delete')
        builtins = ('console|document|window|Math|JSON|Object|Array|String|'
                    'Number|Boolean|Promise|Map|Set|Symbol|true|false|null|'
                    'undefined|NaN|Infinity')
        rules = [
            (r'//.*$',                                self.make(C_COMMENT, italic=True)),
            (r'/\*[\s\S]*?\*/',                       self.make(C_COMMENT, italic=True)),
            (r'"[^"\\]*(\\.[^"\\]*)*"',               self.make(C_STRING)),
            (r"'[^'\\]*(\\.[^'\\]*)*'",               self.make(C_STRING)),
            (r'`[^`]*`',                              self.make(C_STRING)),
            (r'\b(' + kw + r')\b',                    self.make(C_KEYWORD, bold=True)),
            (r'\b(' + builtins + r')\b',              self.make(C_BUILTIN)),
            (r'\b\d+\.?\d*([eE][+-]?\d+)?\b',         self.make(C_NUMBER)),
            (r'\bfunction\s+(\w+)',                   self.make(C_FUNC)),
            (r'\bclass\s+(\w+)',                      self.make(C_CLASS)),
            (r'[+\-*/%=<>!&|^~?]+',                   self.make(C_OPERATOR)),
        ]
        self.add_rules(rules)


class HtmlHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        rules = [
            (r'<!--[\s\S]*?-->',                self.make(C_COMMENT, italic=True)),
            (r'"[^"]*"',                         self.make(C_STRING)),
            (r"'[^']*'",                         self.make(C_STRING)),
            (r'<\/?[A-Za-z][\w-]*',              self.make(C_KEYWORD, bold=True)),
            (r'[A-Za-z-]+(?=\=)',                self.make(C_BUILTIN)),
            (r'[<>\/=]',                         self.make(C_OPERATOR)),
        ]
        self.add_rules(rules)


class CssHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        rules = [
            (r'/\*[\s\S]*?\*/',                  self.make(C_COMMENT, italic=True)),
            (r'[#.][\w-]+',                      self.make(C_CLASS)),
            (r'\b[A-Za-z-]+(?=\s*:)',            self.make(C_KEYWORD)),
            (r':\s*([^;{}]+)',                   self.make(C_STRING)),
            (r'[{};:,]',                         self.make(C_OPERATOR)),
            (r'\b\d+\.?\d*(px|em|rem|%|vh|vw|s|ms)?\b', self.make(C_NUMBER)),
        ]
        self.add_rules(rules)


class JsonHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        rules = [
            (r'"[^"\\]*(\\.[^"\\]*)*"(?=\s*:)',  self.make(C_KEYWORD, bold=True)),
            (r'"[^"\\]*(\\.[^"\\]*)*"',          self.make(C_STRING)),
            (r'\b(true|false|null)\b',           self.make(C_BUILTIN)),
            (r'\b-?\d+\.?\d*([eE][+-]?\d+)?\b',  self.make(C_NUMBER)),
            (r'[{}\[\]:,]',                      self.make(C_OPERATOR)),
        ]
        self.add_rules(rules)


class CppHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        kw = ('int|float|double|char|void|bool|long|short|unsigned|signed|'
              'const|static|struct|class|public|private|protected|namespace|'
              'using|return|if|else|for|while|do|break|continue|switch|case|'
              'default|try|catch|throw|new|delete|this|template|typename|'
              'virtual|override|final|auto|nullptr|true|false|include|define')
        rules = [
            (r'//.*$',                            self.make(C_COMMENT, italic=True)),
            (r'/\*[\s\S]*?\*/',                   self.make(C_COMMENT, italic=True)),
            (r'"[^"\\]*(\\.[^"\\]*)*"',           self.make(C_STRING)),
            (r"'[^'\\]*(\\.[^'\\]*)*'",           self.make(C_STRING)),
            (r'#\s*\w+',                          self.make(C_DECORATOR)),
            (r'\b(' + kw + r')\b',                self.make(C_KEYWORD, bold=True)),
            (r'\b\d+\.?\d*[fFuUlL]*\b',           self.make(C_NUMBER)),
            (r'\b[A-Z_][A-Z0-9_]+\b',             self.make(C_CLASS)),
            (r'[+\-*/%=<>!&|^~?]+',               self.make(C_OPERATOR)),
        ]
        self.add_rules(rules)


class ShHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        kw = ('if|then|else|elif|fi|for|in|do|done|while|case|esac|function|'
              'return|local|export|unset|echo|read|set|exit|cd|pwd|source')
        rules = [
            (r'#.*$',                              self.make(C_COMMENT, italic=True)),
            (r'"[^"\\]*(\\.[^"\\]*)*"',            self.make(C_STRING)),
            (r"'[^']*'",                           self.make(C_STRING)),
            (r'\b(' + kw + r')\b',                 self.make(C_KEYWORD, bold=True)),
            (r'\$\w+',                             self.make(C_BUILTIN)),
            (r'\b\d+\b',                           self.make(C_NUMBER)),
            (r'[|&;<>()]',                         self.make(C_OPERATOR)),
        ]
        self.add_rules(rules)


class MarkdownHighlighter(HighlighterBase):
    def __init__(self, doc):
        super().__init__(doc)
        rules = [
            (r'^#{1,6}\s+.*$',                     self.make(C_KEYWORD, bold=True)),
            (r'\*\*[^*]+\*\*',                     self.make(C_CLASS, bold=True)),
            (r'__[^_]+__',                         self.make(C_CLASS, bold=True)),
            (r'`[^`]+`',                           self.make(C_STRING)),
            (r'^>\s+.*$',                          self.make(C_COMMENT, italic=True)),
            (r'^[-*+]\s+',                         self.make(C_ACCENT)),
            (r'\[([^\]]+)\]\([^)]+\)',             self.make(C_ACCENT)),
        ]
        self.add_rules(rules)


# ---------- Панель поиска/замены ----------
class FindReplaceBar(QWidget):
    def __init__(self, editor_holder, parent=None):
        super().__init__(parent)
        self.editor_holder = editor_holder
        self.setFixedHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Найти…")
        self.find_edit.setFixedHeight(28)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Заменить на…")
        self.replace_edit.setFixedHeight(28)

        self.btn_find = QPushButton("Найти")
        self.btn_find.setFixedHeight(28)
        self.btn_find.setCursor(Qt.PointingHandCursor)
        self.btn_replace = QPushButton("Заменить")
        self.btn_replace.setFixedHeight(28)
        self.btn_replace.setCursor(Qt.PointingHandCursor)
        self.btn_replace_all = QPushButton("Все")
        self.btn_replace_all.setFixedHeight(28)
        self.btn_replace_all.setCursor(Qt.PointingHandCursor)
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setCursor(Qt.PointingHandCursor)

        lay.addWidget(QLabel("🔍"))
        lay.addWidget(self.find_edit, 3)
        lay.addWidget(self.btn_find)
        lay.addWidget(self.replace_edit, 3)
        lay.addWidget(self.btn_replace)
        lay.addWidget(self.btn_replace_all)
        lay.addStretch(1)
        lay.addWidget(self.btn_close)

        self.btn_find.clicked.connect(self.find)
        self.btn_replace.clicked.connect(self.replace)
        self.btn_replace_all.clicked.connect(self.replace_all)
        self.btn_close.clicked.connect(self.hide)
        self.find_edit.returnPressed.connect(self.find)

        self.setStyleSheet(f"""
            QWidget {{ background: {C_BG_ALT}; border-bottom: 1px solid {C_BORDER}; }}
            QLineEdit {{
                background: {C_BG}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
                padding: 2px 8px; selection-background-color: {C_ACCENT};
            }}
            QLineEdit:focus {{ border: 1px solid {C_ACCENT}; }}
            QPushButton {{
                background: {C_BG_HOVER}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 4px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{ background: {C_ACCENT}; color: {C_BG}; border: 1px solid {C_ACCENT}; }}
            QLabel {{ color: {C_TEXT_DIM}; }}
        """)

    def current_editor(self):
        return self.editor_holder.current_editor()

    def find(self):
        ed = self.current_editor()
        if ed: ed.find(self.find_edit.text())

    def replace(self):
        ed = self.current_editor()
        if not ed: return
        ed.replace(self.find_edit.text(), self.replace_edit.text())

    def replace_all(self):
        ed = self.current_editor()
        if not ed: return
        ed.replace_all(self.find_edit.text(), self.replace_edit.text())


# ---------- Дерево файлов ----------
class FileTreeView(QTreeView):
    def __init__(self, on_open, parent=None):
        super().__init__(parent)
        self.on_open = on_open
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setIndentation(14)
        self.setRootIsDecorated(True)
        self.setSelectionMode(QTreeView.SingleSelection)
        self.setUniformRowHeights(True)
        self.setFrameShape(QFrame.NoFrame)

        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self.setModel(self.model)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)
        for col in [1, 2, 3]:
            self.hideColumn(col)

        self.doubleClicked.connect(self.open_index)
        self.setStyleSheet(f"""
            QTreeView {{
                background: {C_BG_ALT}; color: {C_TEXT};
                border: none; outline: 0;
            }}
            QTreeView::item {{ padding: 4px 2px; }}
            QTreeView::item:hover {{ background: {C_BG_HOVER}; }}
            QTreeView::item:selected {{ background: {C_ACCENT}; color: {C_BG}; }}
            QTreeView::branch {{ background: {C_BG_ALT}; }}
        """)

    def set_root(self, path):
        if not path or not os.path.isdir(path):
            return
        idx = self.model.index(path)
        self.setRootIndex(idx)
        self.model.setRootPath(path)

    def open_index(self, idx):
        path = self.model.filePath(idx)
        if os.path.isfile(path):
            self.on_open(path)


# ---------- Вкладки ----------
class EditorHolder(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setDocumentMode(True)
        self.tabCloseRequested.connect(self.close_tab)
        self.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {C_BORDER}; top: -1px;
                background: {C_BG};
            }}
            QTabBar::tab {{
                background: {C_BG_ALT}; color: {C_TEXT_DIM};
                padding: 7px 16px; margin-right: 2px;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                border: 1px solid {C_BORDER}; border-bottom: none;
                min-width: 110px;
            }}
            QTabBar::tab:selected {{
                background: {C_BG}; color: {C_TEXT};
                border-bottom: 2px solid {C_ACCENT};
            }}
            QTabBar::tab:hover:!selected {{ background: {C_BG_HOVER}; color: {C_TEXT}; }}
            QTabBar::close-button {{
                image: none; subcontrol-position: right; padding: 2px;
                border-radius: 8px; background: transparent;
            }}
            QTabBar::close-button:hover {{ background: {C_ERROR}; }}
        """)

    def open_file(self, filepath):
        for i in range(self.count()):
            ed = self.widget(i)
            if isinstance(ed, CodeEditor) and ed.filepath and \
               os.path.abspath(ed.filepath) == os.path.abspath(filepath):
                self.setCurrentIndex(i)
                return ed
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(filepath, "r", encoding="cp1251", errors="replace") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл:\n{e}")
            return None
        ed = CodeEditor(filepath)
        ed.setPlainText(content)
        ed.document().setModified(False)
        title = os.path.basename(filepath)
        idx = self.addTab(ed, title)
        self.setTabToolTip(idx, filepath)
        self.setCurrentIndex(idx)
        self.update_tab_modified(idx, False)
        ed.modificationChanged.connect(
            lambda m, i=idx, e=ed: self.update_tab_modified(i, m)
        )
        return ed

    def update_tab_modified(self, idx, modified):
        ed = self.widget(idx)
        if not isinstance(ed, CodeEditor):
            return
        title = os.path.basename(ed.filepath) if ed.filepath else "Без имени"
        if modified:
            title = "● " + title
        self.setTabText(idx, title)

    def new_file(self):
        ed = CodeEditor(None)
        idx = self.addTab(ed, "● Без имени")
        self.setTabToolTip(idx, "Новый файл")
        self.setCurrentIndex(idx)
        ed.modificationChanged.connect(
            lambda m, i=idx, e=ed: self.update_tab_modified(i, m)
        )
        return ed

    def current_editor(self):
        w = self.currentWidget()
        return w if isinstance(w, CodeEditor) else None

    def close_tab(self, idx):
        ed = self.widget(idx)
        if not isinstance(ed, CodeEditor):
            return
        if ed.document().isModified():
            name = os.path.basename(ed.filepath) if ed.filepath else "Без имени"
            ret = QMessageBox.question(
                self, "Сохранить?",
                f"Файл «{name}» изменён. Сохранить перед закрытием?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if ret == QMessageBox.Cancel:
                return
            if ret == QMessageBox.Save:
                if not self.save_editor(ed):
                    return
        self.removeTab(idx)

    def save_editor(self, ed):
        if not ed.filepath:
            path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить файл", "", "Все файлы (*.*)"
            )
            if not path:
                return False
            ed.filepath = path
            ed.set_highlighter_for(path)
        try:
            with open(ed.filepath, "w", encoding="utf-8") as f:
                f.write(ed.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return False
        ed.document().setModified(False)
        idx = self.indexOf(ed)
        if idx >= 0:
            self.setTabText(idx, os.path.basename(ed.filepath))
            self.setTabToolTip(idx, ed.filepath)
        return True


# ---------- Главное окно ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova IDE")
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)
        self.apply_dark_theme()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.toolbar = self._build_toolbar()
        outer.addWidget(self.toolbar)

        self.splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(0)
        self.path_label = QLabel("  Папка не открыта")
        self.path_label.setStyleSheet(
            f"background:{C_BG_ALT}; color:{C_TEXT_DIM}; "
            f"padding:8px 10px; border-bottom:1px solid {C_BORDER}; "
            f"font-size:12px;"
        )
        llay.addWidget(self.path_label)
        self.file_tree = FileTreeView(self.open_file)
        llay.addWidget(self.file_tree, 1)
        self.splitter.addWidget(left)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setSizes([280, 1000])

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(0)
        self.editor_holder = EditorHolder()
        rlay.addWidget(self.editor_holder, 1)
        self.find_bar = FindReplaceBar(self.editor_holder)
        self.find_bar.hide()
        rlay.addWidget(self.find_bar)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)

        outer.addWidget(self.splitter, 1)

        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        self.status.setStyleSheet(
            f"QStatusBar {{ background:{C_BG_ALT}; color:{C_TEXT_DIM}; "
            f"border-top:1px solid {C_BORDER}; font-size:12px; }}"
            f"QStatusBar::item {{ border: none; }}"
        )
        self.lbl_lang = QLabel("Python")
        self.lbl_pos = QLabel("Стр 1, Кол 1")
        self.lbl_enc = QLabel("UTF-8")
        self.lbl_count = QLabel("0 файлов")
        for lbl in (self.lbl_lang, self.lbl_pos, self.lbl_enc, self.lbl_count):
            lbl.setStyleSheet(f"color:{C_TEXT_DIM}; padding:0 10px;")
        self.status.addWidget(self.lbl_lang)
        self.status.addWidget(self.lbl_enc)
        self.status.addPermanentWidget(self.lbl_count)
        self.status.addPermanentWidget(self.lbl_pos)
        self.setStatusBar(self.status)

        self.editor_holder.currentChanged.connect(self.on_tab_changed)
        self._build_menus()
        self._build_shortcuts()
        self.on_tab_changed(-1)
        self.editor_holder.new_file()

    def apply_dark_theme(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {C_BG}; }}
            QWidget {{ color: {C_TEXT}; }}
            QToolBar {{
                background: {C_BG_ALT}; border: none;
                border-bottom: 1px solid {C_BORDER};
                spacing: 4px; padding: 4px 6px;
            }}
            QToolBar QToolButton {{
                background: transparent; color: {C_TEXT};
                padding: 6px 10px; border-radius: 5px;
                border: 1px solid transparent;
            }}
            QToolBar QToolButton:hover {{
                background: {C_BG_HOVER}; border: 1px solid {C_BORDER};
            }}
            QToolBar QToolButton:pressed {{ background: {C_ACCENT}; color: {C_BG}; }}
            QSplitter::handle {{ background: {C_BORDER}; width: 2px; }}
            QSplitter::handle:hover {{ background: {C_ACCENT}; }}
            QMenuBar {{
                background: {C_BG_ALT}; color: {C_TEXT};
                border-bottom: 1px solid {C_BORDER}; padding: 2px;
            }}
            QMenuBar::item {{
                padding: 6px 12px; background: transparent; border-radius: 4px;
            }}
            QMenuBar::item:selected {{ background: {C_BG_HOVER}; }}
            QMenuBar::item:pressed {{ background: {C_ACCENT}; color: {C_BG}; }}
            QMenu {{
                background: {C_BG_ALT}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; padding: 4px;
            }}
            QMenu::item {{ padding: 6px 28px 6px 18px; border-radius: 4px; }}
            QMenu::item:selected {{ background: {C_BG_HOVER}; }}
            QMenu::separator {{ height: 1px; background: {C_BORDER}; margin: 4px 8px; }}
            QStatusBar QLabel {{ color: {C_TEXT_DIM}; }}
            QScrollBar:vertical {{
                background: {C_BG}; width: 12px; margin: 0; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C_BG_HOVER}; min-height: 30px; border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {C_TEXT_DIM}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {C_BG}; height: 12px; margin: 0; border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {C_BG_HOVER}; min-width: 30px; border-radius: 6px;
                margin: 2px;
            }}
        """)

    def _build_toolbar(self):
        tb = QToolBar("Главная")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        acts = [
            ("＋  Новый",     self.action_new,         "Создать файл (Ctrl+N)"),
            ("📂  Открыть",   self.action_open,        "Открыть файл (Ctrl+O)"),
            ("💾  Сохранить", self.action_save,        "Сохранить (Ctrl+S)"),
            ("📁  Папка",     self.action_open_folder, "Открыть папку проекта"),
            ("▶  Запустить",  self.action_run,         "Запустить (F5)"),
            ("🔍  Найти",     self.toggle_find,        "Найти/Заменить (Ctrl+F)"),
        ]
        for label, slot, tip in acts:
            a = QAction(label, self)
            a.setToolTip(tip)
            a.triggered.connect(slot)
            tb.addAction(a)
            tb.addSeparator()
        tb.layout().setSpacing(2)
        return tb

    def _build_menus(self):
        mb = self.menuBar()
        m_file = mb.addMenu("Файл")
        self._add_action(m_file, "Новый",          QKeySequence.New,            self.action_new)
        self._add_action(m_file, "Открыть…",       QKeySequence.Open,           self.action_open)
        self._add_action(m_file, "Сохранить",      QKeySequence.Save,           self.action_save)
        self._add_action(m_file, "Сохранить как…", QKeySequence("Ctrl+Shift+S"), self.action_save_as)
        m_file.addSeparator()
        self._add_action(m_file, "Открыть папку…", QKeySequence("Ctrl+Shift+O"), self.action_open_folder)
        m_file.addSeparator()
        self._add_action(m_file, "Выход",          QKeySequence.Quit,           self.close)

        m_edit = mb.addMenu("Правка")
        self._add_action(m_edit, "Отменить",  QKeySequence.Undo,  self.action_undo)
        self._add_action(m_edit, "Повторить", QKeySequence.Redo,  self.action_redo)
        m_edit.addSeparator()
        self._add_action(m_edit, "Вырезать",  QKeySequence.Cut,   self.action_cut)
        self._add_action(m_edit, "Копировать",QKeySequence.Copy,  self.action_copy)
        self._add_action(m_edit, "Вставить",  QKeySequence.Paste, self.action_paste)
        m_edit.addSeparator()
        self._add_action(m_edit, "Найти/Заменить…", QKeySequence.Find, self.toggle_find)

        m_run = mb.addMenu("Запуск")
        self._add_action(m_run, "Запустить (F5)", QKeySequence("F5"), self.action_run)

        m_view = mb.addMenu("Вид")
        self._add_action(m_view, "Увеличить шрифт", QKeySequence("Ctrl++"),
                         lambda: self.zoom_font(+1))
        self._add_action(m_view, "Уменьшить шрифт", QKeySequence("Ctrl+-"),
                         lambda: self.zoom_font(-1))

        m_help = mb.addMenu("Помощь")
        self._add_action(m_help, "О программе", QKeySequence("F1"), self.about)

    def _add_action(self, menu, text, shortcut, slot):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
        menu.addAction(a)

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+W"), self,
                  activated=lambda: self.editor_holder.close_tab(
                      self.editor_holder.currentIndex()))
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=self.next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, activated=self.prev_tab)

    def action_new(self):
        self.editor_holder.new_file()
        self.on_tab_changed(self.editor_holder.currentIndex())

    def action_open(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Открыть файл(ы)", "", "Все файлы (*.*)")
        for p in paths:
            self.open_file(p)

    def open_file(self, path):
        self.editor_holder.open_file(path)
        self.on_tab_changed(self.editor_holder.currentIndex())

    def action_save(self):
        ed = self.editor_holder.current_editor()
        if ed:
            self.editor_holder.save_editor(ed)

    def action_save_as(self):
        ed = self.editor_holder.current_editor()
        if not ed: return
        ed.filepath = None
        self.editor_holder.save_editor(ed)

    def action_open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Открыть папку")
        if path:
            self.file_tree.set_root(path)
            self.path_label.setText("  " + path)
            QApplication.processEvents()

    def action_undo(self):
        ed = self.editor_holder.current_editor()
        if ed: ed.undo()

    def action_redo(self):
        ed = self.editor_holder.current_editor()
        if ed: ed.redo()

    def action_cut(self):
        ed = self.editor_holder.current_editor()
        if ed: ed.cut()

    def action_copy(self):
        ed = self.editor_holder.current_editor()
        if ed: ed.copy()

    def action_paste(self):
        ed = self.editor_holder.current_editor()
        if ed: ed.paste()

    def toggle_find(self):
        self.find_bar.setVisible(not self.find_bar.isVisible())
        if self.find_bar.isVisible():
            self.find_bar.find_edit.setFocus()
            self.find_bar.find_edit.selectAll()

    def zoom_font(self, delta):
        ed = self.editor_holder.current_editor()
        if not ed: return
        f = ed.font()
        sz = max(6, min(36, f.pointSize() + delta))
        f.setPointSize(sz)
        ed.setFont(f)
        ed.update_line_number_area_width(0)

    def next_tab(self):
        n = self.editor_holder.count()
        if n > 1:
            self.editor_holder.setCurrentIndex(
                (self.editor_holder.currentIndex() + 1) % n
            )

    def prev_tab(self):
        n = self.editor_holder.count()
        if n > 1:
            self.editor_holder.setCurrentIndex(
                (self.editor_holder.currentIndex() - 1) % n
            )

    def action_run(self):
        ed = self.editor_holder.current_editor()
        if not ed: return
        if ed.document().isModified() or not ed.filepath:
            if not self.editor_holder.save_editor(ed):
                return
        if not ed.filepath: return
        ext = os.path.splitext(ed.filepath)[1].lower()
        if ext == ".py":
            self._run_cmd([sys.executable, ed.filepath])
        elif ext in (".js", ".mjs"):
            self._run_cmd(["node", ed.filepath])
        elif ext == ".sh":
            self._run_cmd(["bash", ed.filepath])
        else:
            self.status.showMessage(f"Запуск для «{ext}» не поддерживается", 2500)

    def _run_cmd(self, cmd):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            out = res.stdout or ""
            err = res.stderr or ""
            text = (out + ("\n--- STDERR ---\n" + err if err else "")).strip()
            if not text:
                text = "(нет вывода)"
        except FileNotFoundError:
            text = f"Интерпретатор не найден: {cmd[0]}"
        except subprocess.TimeoutExpired:
            text = "Превышено время выполнения (30 с)"
        except Exception as e:
            text = f"Ошибка запуска: {e}"
        idx = self.editor_holder.addTab(CodeEditor(None), "▶ Вывод")
        out_ed = self.editor_holder.widget(idx)
        out_ed.setPlainText(text)
        out_ed.setReadOnly(True)
        self.editor_holder.setCurrentIndex(idx)
        self.status.showMessage(f"Запущено: {' '.join(cmd)}", 2500)

    def on_tab_changed(self, _):
        ed = self.editor_holder.current_editor()
        if not ed:
            self.lbl_lang.setText("—")
            self.lbl_pos.setText("Стр 1, Кол 1")
            return
        ext = os.path.splitext(ed.filepath or "")[1].lower() or "txt"
        lang_map = {
            ".py":"Python", ".js":"JavaScript", ".ts":"TypeScript",
            ".html":"HTML", ".css":"CSS", ".json":"JSON",
            ".c":"C", ".cpp":"C++", ".h":"C/C++", ".hpp":"C++",
            ".sh":"Shell", ".md":"Markdown",
        }
        self.lbl_lang.setText(lang_map.get(ext, "Текст"))
        if getattr(ed, "_pos_connected", False):
            try:
                ed.cursorPositionChanged.disconnect(self.update_pos)
            except (TypeError, RuntimeError):
                pass
        ed.cursorPositionChanged.connect(self.update_pos)
        ed._pos_connected = True
        self.update_pos()
        self.lbl_count.setText(f"{self.editor_holder.count()} файлов")

    def update_pos(self):
        ed = self.editor_holder.current_editor()
        if not ed: return
        c = ed.textCursor()
        self.lbl_pos.setText(f"Стр {c.blockNumber() + 1}, Кол {c.columnNumber() + 1}")

    def about(self):
        QMessageBox.about(
            self, "О программе — Nova IDE",
            "<h3 style='color:#58a6ff'>Nova IDE</h3>"
            "<p>Лёгкая красивая IDE на PySide6.</p>"
            "<p>Подсветка: Python, JS, HTML, CSS, JSON, C/C++, Shell, Markdown.<br>"
            "Запуск: Python, Node.js, Bash.<br>"
            "Горячие клавиши: Ctrl+N/O/S/F, F5, Ctrl+Tab.</p>"
            "<p style='color:#8b949e'>Платформа: " + platform.system() + "</p>"
        )

    def closeEvent(self, e):
        while self.editor_holder.count() > 0:
            before = self.editor_holder.count()
            self.editor_holder.close_tab(0)
            if self.editor_holder.count() == before:
                e.ignore()
                return
            if self.editor_holder.count() == 0:
                break
        e.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Nova IDE")
    app.setStyle("Fusion")
    p = app.palette()
    p.setColor(QPalette.Window, QColor(C_BG))
    p.setColor(QPalette.WindowText, QColor(C_TEXT))
    p.setColor(QPalette.Base, QColor(C_BG))
    p.setColor(QPalette.AlternateBase, QColor(C_BG_ALT))
    p.setColor(QPalette.Text, QColor(C_TEXT))
    p.setColor(QPalette.Button, QColor(C_BG_ALT))
    p.setColor(QPalette.ButtonText, QColor(C_TEXT))
    p.setColor(QPalette.Highlight, QColor(C_ACCENT))
    p.setColor(QPalette.HighlightedText, QColor(C_BG))
    p.setColor(QPalette.ToolTipBase, QColor(C_BG_ALT))
    p.setColor(QPalette.ToolTipText, QColor(C_TEXT))
    app.setPalette(p)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
