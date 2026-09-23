"""
Editor de Texto Simples - v1
Requisitos: pip install PySide6
Execução: python editor.py
"""
import sys
from PySide6.QtCore import Qt, QSizeF, QMarginsF
from PySide6.QtGui import (
    QTextCharFormat, QFont, QTextCursor, QPainter, QPen, QColor,
    QAction, QKeySequence, QPageLayout, QPageSize
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QFileDialog,
    QMessageBox, QStatusBar, QWidget, QVBoxLayout
)

# ---------- Configurações de página (em milímetros) ----------
MM_TO_PX = 96 / 25.4  # 96 DPI (padrão de tela)

PAGE_WIDTH_MM = 210     # A4
PAGE_HEIGHT_MM = 297
MARGIN_MM = 25          # margem uniforme (2,5 cm) - simples por enquanto

PAGE_WIDTH_PX = PAGE_WIDTH_MM * MM_TO_PX
PAGE_HEIGHT_PX = PAGE_HEIGHT_MM * MM_TO_PX
MARGIN_PX = MARGIN_MM * MM_TO_PX


class PagedTextEdit(QTextEdit):
    """QTextEdit que simula páginas: a largura do texto é limitada à largura
    da página (com margens) e linhas tracejadas indicam onde cada página
    termina, conforme o usuário rola o documento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QTextEdit.FixedPixelWidth)
        self.setLineWrapColumnOrWidth(int(PAGE_WIDTH_PX))
        self.document().setDocumentMargin(MARGIN_PX)
        self.setFixedWidth(int(PAGE_WIDTH_PX) + 4)
        self.document().setPageSize(QSizeF(PAGE_WIDTH_PX, PAGE_HEIGHT_PX))

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor(180, 180, 180), 1, Qt.DashLine))

        page_height = PAGE_HEIGHT_PX
        offset = self.verticalScrollBar().value()
        y = page_height - (offset % page_height)
        while y < self.viewport().height():
            painter.drawLine(0, int(y), self.viewport().width(), int(y))
            y += page_height
        painter.end()

    def page_count(self):
        return max(1, self.document().pageCount())


class Editor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Editor de Texto — Sem título")
        self.resize(1000, 800)

        self.current_path = None

        self.text_edit = PagedTextEdit()
        self.text_edit.setFont(QFont("Arial", 11))

        # centraliza a "página" na janela
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignHCenter)
        layout.addWidget(self.text_edit)
        self.setCentralWidget(container)

        self._criar_menus_e_barra()

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.text_edit.textChanged.connect(self._atualizar_status)
        self.text_edit.cursorPositionChanged.connect(self._sincronizar_botoes)
        self._atualizar_status()

    # ---------------- Menu / Toolbar ----------------
    def _criar_menus_e_barra(self):
        menu_arquivo = self.menuBar().addMenu("&Arquivo")

        acao_novo = QAction("Novo", self)
        acao_novo.setShortcut(QKeySequence.New)
        acao_novo.triggered.connect(self.novo_arquivo)
        menu_arquivo.addAction(acao_novo)

        acao_abrir = QAction("Abrir...", self)
        acao_abrir.setShortcut(QKeySequence.Open)
        acao_abrir.triggered.connect(self.abrir_arquivo)
        menu_arquivo.addAction(acao_abrir)

        acao_salvar = QAction("Salvar", self)
        acao_salvar.setShortcut(QKeySequence.Save)
        acao_salvar.triggered.connect(self.salvar_arquivo)
        menu_arquivo.addAction(acao_salvar)

        acao_salvar_como = QAction("Salvar como...", self)
        acao_salvar_como.setShortcut(QKeySequence.SaveAs)
        acao_salvar_como.triggered.connect(self.salvar_como)
        menu_arquivo.addAction(acao_salvar_como)

        menu_arquivo.addSeparator()

        acao_imprimir = QAction("Imprimir...", self)
        acao_imprimir.setShortcut(QKeySequence.Print)
        acao_imprimir.triggered.connect(self.imprimir)
        menu_arquivo.addAction(acao_imprimir)

        acao_visualizar = QAction("Visualizar impressão...", self)
        acao_visualizar.triggered.connect(self.visualizar_impressao)
        menu_arquivo.addAction(acao_visualizar)

        menu_arquivo.addSeparator()
        acao_sair = QAction("Sair", self)
        acao_sair.triggered.connect(self.close)
        menu_arquivo.addAction(acao_sair)

        # ---- Formatação ----
        toolbar = QToolBar("Formatação")
        self.addToolBar(toolbar)

        self.acao_negrito = QAction("N", self)
        self.acao_negrito.setCheckable(True)
        self.acao_negrito.setShortcut(QKeySequence.Bold)
        f = self.acao_negrito.font()
        f.setBold(True)
        self.acao_negrito.setFont(f)
        self.acao_negrito.triggered.connect(self.alternar_negrito)
        toolbar.addAction(self.acao_negrito)

        self.acao_italico = QAction("I", self)
        self.acao_italico.setCheckable(True)
        self.acao_italico.setShortcut(QKeySequence.Italic)
        f = self.acao_italico.font()
        f.setItalic(True)
        self.acao_italico.setFont(f)
        self.acao_italico.triggered.connect(self.alternar_italico)
        toolbar.addAction(self.acao_italico)

        self.acao_sublinhado = QAction("S", self)
        self.acao_sublinhado.setCheckable(True)
        self.acao_sublinhado.setShortcut(QKeySequence.Underline)
        f = self.acao_sublinhado.font()
        f.setUnderline(True)
        self.acao_sublinhado.setFont(f)
        self.acao_sublinhado.triggered.connect(self.alternar_sublinhado)
        toolbar.addAction(self.acao_sublinhado)

        self.acao_tachado = QAction("T", self)
        self.acao_tachado.setCheckable(True)
        self.acao_tachado.setShortcut(QKeySequence("Ctrl+Shift+X"))
        f = self.acao_tachado.font()
        f.setStrikeOut(True)
        self.acao_tachado.setFont(f)
        self.acao_tachado.triggered.connect(self.alternar_tachado)
        toolbar.addAction(self.acao_tachado)

    # ---------------- Ações de arquivo ----------------
    def novo_arquivo(self):
        if self._confirmar_descarte():
            self.text_edit.clear()
            self.current_path = None
            self.setWindowTitle("Editor de Texto — Sem título")

    def abrir_arquivo(self):
        if not self._confirmar_descarte():
            return
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir arquivo", "", "Documentos HTML (*.html);;Texto simples (*.txt)"
        )
        if not caminho:
            return
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = f.read()
        if caminho.lower().endswith(".html"):
            self.text_edit.setHtml(conteudo)
        else:
            self.text_edit.setPlainText(conteudo)
        self.current_path = caminho
        self.setWindowTitle(f"Editor de Texto — {caminho}")

    def salvar_arquivo(self):
        if self.current_path:
            self._salvar_em(self.current_path)
        else:
            self.salvar_como()

    def salvar_como(self):
        caminho, filtro = QFileDialog.getSaveFileName(
            self, "Salvar como", "", "Documento HTML (*.html);;Texto simples (*.txt)"
        )
        if not caminho:
            return
        if "html" in filtro.lower() and not caminho.lower().endswith(".html"):
            caminho += ".html"
        if "txt" in filtro.lower() and not caminho.lower().endswith(".txt"):
            caminho += ".txt"
        self._salvar_em(caminho)

    def _salvar_em(self, caminho):
        try:
            if caminho.lower().endswith(".html"):
                conteudo = self.text_edit.toHtml()
            else:
                conteudo = self.text_edit.toPlainText()
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo)
            self.current_path = caminho
            self.text_edit.document().setModified(False)
            self.setWindowTitle(f"Editor de Texto — {caminho}")
            self.status.showMessage("Arquivo salvo.", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao salvar", str(e))

    def _confirmar_descarte(self):
        if not self.text_edit.document().isModified():
            return True
        resposta = QMessageBox.question(
            self, "Alterações não salvas",
            "Deseja salvar as alterações antes de continuar?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
        )
        if resposta == QMessageBox.Save:
            self.salvar_arquivo()
            return True
        return resposta == QMessageBox.Discard

    # ---------------- Impressão ----------------
    def _preparar_impressora(self):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(
            QMarginsF(MARGIN_MM, MARGIN_MM, MARGIN_MM, MARGIN_MM),
            QPageLayout.Millimeter
        )
        return printer

    def imprimir(self):
        printer = self._preparar_impressora()
        dialogo = QPrintDialog(printer, self)
        if dialogo.exec() == QPrintDialog.Accepted:
            self.text_edit.document().print_(printer)

    def visualizar_impressao(self):
        printer = self._preparar_impressora()
        preview = QPrintPreviewDialog(printer, self)
        preview.paintRequested.connect(lambda p: self.text_edit.document().print_(p))
        preview.exec()

    # ---------------- Formatação ----------------
    def alternar_negrito(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if self.acao_negrito.isChecked() else QFont.Normal)
        self._aplicar_formato(fmt)

    def alternar_italico(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.acao_italico.isChecked())
        self._aplicar_formato(fmt)

    def alternar_sublinhado(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.acao_sublinhado.isChecked())
        self._aplicar_formato(fmt)

    def alternar_tachado(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(self.acao_tachado.isChecked())
        self._aplicar_formato(fmt)

    def _aplicar_formato(self, fmt):
        # Se houver seleção, aplica nela; se não, define o formato
        # para o que for digitado a partir do cursor.
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.text_edit.setFocus()

    def _sincronizar_botoes(self):
        fmt = self.text_edit.currentCharFormat()
        for acao in (self.acao_negrito, self.acao_italico,
                     self.acao_sublinhado, self.acao_tachado):
            acao.blockSignals(True)

        self.acao_negrito.setChecked(fmt.fontWeight() == QFont.Bold)
        self.acao_italico.setChecked(fmt.fontItalic())
        self.acao_sublinhado.setChecked(fmt.fontUnderline())
        self.acao_tachado.setChecked(fmt.fontStrikeOut())

        for acao in (self.acao_negrito, self.acao_italico,
                     self.acao_sublinhado, self.acao_tachado):
            acao.blockSignals(False)

    # ---------------- Status ----------------
    def _atualizar_status(self):
        paginas = self.text_edit.page_count()
        self.status.showMessage(f"Páginas: {paginas}")


def main():
    app = QApplication(sys.argv)
    janela = Editor()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
