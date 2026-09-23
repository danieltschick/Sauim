"""
Sauim - Editor de Texto v1
Requisitos: pip install PySide6
Execução: python editor.py

Formato nativo: .saui (JSON contendo o HTML do documento + metadados de
página). HTML e TXT continuam disponíveis como formatos de exportação.
"""
import sys
import json
from PySide6.QtCore import Qt, QSizeF, QMarginsF
from PySide6.QtGui import (
    QTextCharFormat, QFont, QTextCursor, QPainter, QPen, QColor,
    QAction, QKeySequence, QPageLayout, QPageSize
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QFileDialog,
    QMessageBox, QStatusBar, QWidget, QVBoxLayout, QFontComboBox, QComboBox
)
from PySide6.QtGui import QActionGroup, QIntValidator

# ---------- Configurações de página (em milímetros) ----------
MM_TO_PX = 96 / 25.4  # 96 DPI (padrão de tela)

PAGE_WIDTH_MM = 210     # A4
PAGE_HEIGHT_MM = 297
MARGIN_MM = 25          # margem uniforme (2,5 cm) - simples por enquanto

PAGE_WIDTH_PX = PAGE_WIDTH_MM * MM_TO_PX
PAGE_HEIGHT_PX = PAGE_HEIGHT_MM * MM_TO_PX
MARGIN_PX = MARGIN_MM * MM_TO_PX

# ---------- Formato nativo do Sauim ----------
NOME_APP = "Sauim"
EXTENSAO_NATIVA = ".saui"
VERSAO_FORMATO = 1


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
        self.setWindowTitle(f"{NOME_APP} — Sem título")
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

        # Família da fonte
        self.combo_fonte = QFontComboBox()
        self.combo_fonte.setCurrentFont(QFont("Arial"))
        self.combo_fonte.setToolTip("Fonte")
        self.combo_fonte.setMaximumWidth(180)
        self.combo_fonte.currentFontChanged.connect(self.alterar_familia_fonte)
        toolbar.addWidget(self.combo_fonte)

        # Tamanho da fonte
        tamanhos_comuns = ["8", "9", "10", "11", "12", "14", "16", "18",
                            "20", "24", "28", "32", "36", "48", "72"]
        self.combo_tamanho = QComboBox()
        self.combo_tamanho.setEditable(True)
        self.combo_tamanho.addItems(tamanhos_comuns)
        self.combo_tamanho.setCurrentText("11")
        self.combo_tamanho.setToolTip("Tamanho da fonte")
        self.combo_tamanho.setMaximumWidth(60)
        self.combo_tamanho.lineEdit().setValidator(QIntValidator(1, 400, self))
        self.combo_tamanho.activated.connect(
            lambda: self.alterar_tamanho_fonte(self.combo_tamanho.currentText())
        )
        self.combo_tamanho.lineEdit().returnPressed.connect(
            lambda: self.alterar_tamanho_fonte(self.combo_tamanho.currentText())
        )
        toolbar.addWidget(self.combo_tamanho)

        toolbar.addSeparator()

        self.acao_negrito = QAction("N", self)
        self.acao_negrito.setCheckable(True)
        self.acao_negrito.setShortcut(QKeySequence.Bold)
        self.acao_negrito.setToolTip("Negrito (Ctrl+B)")
        f = self.acao_negrito.font()
        f.setBold(True)
        self.acao_negrito.setFont(f)
        self.acao_negrito.triggered.connect(self.alternar_negrito)
        toolbar.addAction(self.acao_negrito)

        self.acao_italico = QAction("I", self)
        self.acao_italico.setCheckable(True)
        self.acao_italico.setShortcut(QKeySequence.Italic)
        self.acao_italico.setToolTip("Itálico (Ctrl+I)")
        f = self.acao_italico.font()
        f.setItalic(True)
        self.acao_italico.setFont(f)
        self.acao_italico.triggered.connect(self.alternar_italico)
        toolbar.addAction(self.acao_italico)

        self.acao_sublinhado = QAction("S", self)
        self.acao_sublinhado.setCheckable(True)
        self.acao_sublinhado.setShortcut(QKeySequence.Underline)
        self.acao_sublinhado.setToolTip("Sublinhado (Ctrl+U)")
        f = self.acao_sublinhado.font()
        f.setUnderline(True)
        self.acao_sublinhado.setFont(f)
        self.acao_sublinhado.triggered.connect(self.alternar_sublinhado)
        toolbar.addAction(self.acao_sublinhado)

        self.acao_tachado = QAction("T", self)
        self.acao_tachado.setCheckable(True)
        self.acao_tachado.setShortcut(QKeySequence("Ctrl+Shift+X"))
        self.acao_tachado.setToolTip("Tachado (Ctrl+Shift+X)")
        f = self.acao_tachado.font()
        f.setStrikeOut(True)
        self.acao_tachado.setFont(f)
        self.acao_tachado.triggered.connect(self.alternar_tachado)
        toolbar.addAction(self.acao_tachado)

        toolbar.addSeparator()

        # ---- Alinhamento (mutuamente exclusivo) ----
        grupo_alinhamento = QActionGroup(self)
        grupo_alinhamento.setExclusive(True)

        self.acao_alinhar_esquerda = QAction("Esq", self)
        self.acao_alinhar_esquerda.setCheckable(True)
        self.acao_alinhar_esquerda.setChecked(True)  # padrão ao abrir
        self.acao_alinhar_esquerda.setToolTip("Alinhar à esquerda (Ctrl+L)")
        self.acao_alinhar_esquerda.setShortcut(QKeySequence("Ctrl+L"))
        self.acao_alinhar_esquerda.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignLeft)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_esquerda)
        toolbar.addAction(self.acao_alinhar_esquerda)

        self.acao_alinhar_centro = QAction("Ctr", self)
        self.acao_alinhar_centro.setCheckable(True)
        self.acao_alinhar_centro.setToolTip("Centralizar (Ctrl+E)")
        self.acao_alinhar_centro.setShortcut(QKeySequence("Ctrl+E"))
        self.acao_alinhar_centro.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignCenter)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_centro)
        toolbar.addAction(self.acao_alinhar_centro)

        self.acao_alinhar_direita = QAction("Dir", self)
        self.acao_alinhar_direita.setCheckable(True)
        self.acao_alinhar_direita.setToolTip("Alinhar à direita (Ctrl+R)")
        self.acao_alinhar_direita.setShortcut(QKeySequence("Ctrl+R"))
        self.acao_alinhar_direita.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignRight)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_direita)
        toolbar.addAction(self.acao_alinhar_direita)

        self.acao_alinhar_justificado = QAction("Jus", self)
        self.acao_alinhar_justificado.setCheckable(True)
        self.acao_alinhar_justificado.setToolTip("Justificar (Ctrl+J)")
        self.acao_alinhar_justificado.setShortcut(QKeySequence("Ctrl+J"))
        self.acao_alinhar_justificado.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignJustify)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_justificado)
        toolbar.addAction(self.acao_alinhar_justificado)

        # guarda numa lista pra facilitar a sincronização com o cursor
        self._acoes_alinhamento = {
            Qt.AlignLeft: self.acao_alinhar_esquerda,
            Qt.AlignCenter: self.acao_alinhar_centro,
            Qt.AlignRight: self.acao_alinhar_direita,
            Qt.AlignJustify: self.acao_alinhar_justificado,
        }

    # ---------------- Ações de arquivo ----------------
    def novo_arquivo(self):
        if self._confirmar_descarte():
            self.text_edit.clear()
            self.current_path = None
            self.setWindowTitle(f"{NOME_APP} — Sem título")

    def abrir_arquivo(self):
        if not self._confirmar_descarte():
            return
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir arquivo", "",
            f"Documento {NOME_APP} (*{EXTENSAO_NATIVA});;"
            "Documento HTML (*.html);;Texto simples (*.txt)"
        )
        if not caminho:
            return
        try:
            if caminho.lower().endswith(EXTENSAO_NATIVA):
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                self.text_edit.setHtml(dados.get("conteudo_html", ""))
                # Metadados de página (largura/altura/margem) ficam salvos
                # no arquivo para uso futuro; a v1 ainda usa os valores
                # fixos definidos no topo do arquivo.
            elif caminho.lower().endswith(".html"):
                with open(caminho, "r", encoding="utf-8") as f:
                    self.text_edit.setHtml(f.read())
            else:
                with open(caminho, "r", encoding="utf-8") as f:
                    self.text_edit.setPlainText(f.read())
        except Exception as e:
            QMessageBox.critical(self, "Erro ao abrir", str(e))
            return
        self.current_path = caminho
        self.text_edit.document().setModified(False)
        self.setWindowTitle(f"{NOME_APP} — {caminho}")

    def salvar_arquivo(self):
        if self.current_path:
            self._salvar_em(self.current_path)
        else:
            self.salvar_como()

    def salvar_como(self):
        caminho, filtro = QFileDialog.getSaveFileName(
            self, "Salvar como", "",
            f"Documento {NOME_APP} (*{EXTENSAO_NATIVA});;"
            "Documento HTML (*.html);;Texto simples (*.txt)"
        )
        if not caminho:
            return
        if EXTENSAO_NATIVA.strip(".") in filtro.lower() and not caminho.lower().endswith(EXTENSAO_NATIVA):
            caminho += EXTENSAO_NATIVA
        elif "html" in filtro.lower() and not caminho.lower().endswith(".html"):
            caminho += ".html"
        elif "txt" in filtro.lower() and not caminho.lower().endswith(".txt"):
            caminho += ".txt"
        self._salvar_em(caminho)

    def _salvar_em(self, caminho):
        try:
            if caminho.lower().endswith(EXTENSAO_NATIVA):
                dados = {
                    "formato": "sauim",
                    "versao": VERSAO_FORMATO,
                    "conteudo_html": self.text_edit.toHtml(),
                    "pagina": {
                        "largura_mm": PAGE_WIDTH_MM,
                        "altura_mm": PAGE_HEIGHT_MM,
                        "margem_mm": MARGIN_MM,
                    },
                }
                with open(caminho, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
            elif caminho.lower().endswith(".html"):
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(self.text_edit.toHtml())
            else:
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(self.text_edit.toPlainText())
            self.current_path = caminho
            self.text_edit.document().setModified(False)
            self.setWindowTitle(f"{NOME_APP} — {caminho}")
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

    def alterar_familia_fonte(self, fonte):
        fmt = QTextCharFormat()
        fmt.setFontFamilies([fonte.family()])
        self._aplicar_formato(fmt)

    def alterar_tamanho_fonte(self, texto):
        try:
            tamanho = int(texto)
        except ValueError:
            return
        if tamanho <= 0:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(tamanho)
        self._aplicar_formato(fmt)

    def definir_alinhamento(self, alinhamento):
        # setAlignment age sobre o(s) parágrafo(s) do cursor/seleção atual.
        self.text_edit.setAlignment(alinhamento)
        self.text_edit.setFocus()

    def _sincronizar_botoes(self):
        fmt = self.text_edit.currentCharFormat()

        self.combo_fonte.blockSignals(True)
        self.combo_fonte.setCurrentFont(QFont(fmt.font().family()))
        self.combo_fonte.blockSignals(False)

        tamanho = fmt.fontPointSize()
        if tamanho <= 0:
            tamanho = self.text_edit.font().pointSize()
        self.combo_tamanho.blockSignals(True)
        self.combo_tamanho.setCurrentText(str(int(tamanho)))
        self.combo_tamanho.blockSignals(False)

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

        # alinhamento do parágrafo onde o cursor está
        alinhamento_atual = self.text_edit.alignment() & Qt.AlignHorizontal_Mask
        acao_correspondente = self._acoes_alinhamento.get(alinhamento_atual)
        if acao_correspondente is not None:
            acao_correspondente.blockSignals(True)
            acao_correspondente.setChecked(True)
            acao_correspondente.blockSignals(False)

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
