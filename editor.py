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
    QTextCharFormat, QFont, QTextCursor, QPainter, QPen,
    QColor, QAction, QKeySequence, QPageLayout, QPageSize
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QFileDialog,
    QMessageBox, QStatusBar, QWidget, QVBoxLayout, QFontComboBox, QComboBox,
    QColorDialog, QLabel
)
from PySide6.QtGui import QActionGroup, QIntValidator, QIcon, QPixmap, QTextListFormat

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
    da página (com margens) e uma linha tracejada indica onde cada página
    termina, conforme o usuário rola o documento.

    Observação: isso é apenas uma indicação visual — o texto continua
    fluindo continuamente por trás da linha (sem um "vão" de verdade entre
    páginas). Tentamos, numa versão anterior, criar esse vão inserindo
    conteúdo real no documento, mas isso causava travamentos durante a
    digitação e fazia a paginação da tela não bater com a da impressão.
    """

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

    def keyPressEvent(self, event):
        # Tab/Shift+Tab só tem um comportamento especial quando o cursor
        # está dentro de uma lista (marcadores ou numeração); fora de uma
        # lista, o Tab funciona normalmente (insere uma tabulação).
        e_tab = event.key() == Qt.Key_Tab
        e_shift_tab = event.key() == Qt.Key_Backtab or (
            e_tab and bool(event.modifiers() & Qt.ShiftModifier)
        )

        if e_tab or e_shift_tab:
            cursor = self.textCursor()
            lista_atual = cursor.currentList()
            if lista_atual:
                estilo = lista_atual.format().style()
                nivel_atual = lista_atual.format().indent()
                novo_nivel = nivel_atual - 1 if e_shift_tab else nivel_atual + 1

                cursor.beginEditBlock()
                if novo_nivel < 1:
                    lista_atual.remove(cursor.block())
                else:
                    fmt = QTextListFormat()
                    fmt.setStyle(estilo)
                    fmt.setIndent(novo_nivel)
                    cursor.createList(fmt)
                cursor.endEditBlock()
                return  # não repassa o Tab pro comportamento padrão

        super().keyPressEvent(event)


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

        # ==================== Seção: Fonte ====================
        toolbar_fonte = QToolBar("Fonte")
        self.addToolBar(toolbar_fonte)

        rotulo_fonte = QLabel(" <b>Fonte</b> ")
        toolbar_fonte.addWidget(rotulo_fonte)

        # Família da fonte
        self.combo_fonte = QFontComboBox()
        self.combo_fonte.setCurrentFont(QFont("Arial"))
        self.combo_fonte.setToolTip("Fonte")
        self.combo_fonte.setMaximumWidth(180)
        self.combo_fonte.currentFontChanged.connect(self.alterar_familia_fonte)
        toolbar_fonte.addWidget(self.combo_fonte)

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
        toolbar_fonte.addWidget(self.combo_tamanho)

        toolbar_fonte.addSeparator()

        self.acao_negrito = QAction("N", self)
        self.acao_negrito.setCheckable(True)
        self.acao_negrito.setShortcut(QKeySequence.Bold)
        self.acao_negrito.setToolTip("Negrito (Ctrl+B)")
        f = self.acao_negrito.font()
        f.setBold(True)
        self.acao_negrito.setFont(f)
        self.acao_negrito.triggered.connect(self.alternar_negrito)
        toolbar_fonte.addAction(self.acao_negrito)

        self.acao_italico = QAction("I", self)
        self.acao_italico.setCheckable(True)
        self.acao_italico.setShortcut(QKeySequence.Italic)
        self.acao_italico.setToolTip("Itálico (Ctrl+I)")
        f = self.acao_italico.font()
        f.setItalic(True)
        self.acao_italico.setFont(f)
        self.acao_italico.triggered.connect(self.alternar_italico)
        toolbar_fonte.addAction(self.acao_italico)

        self.acao_sublinhado = QAction("S", self)
        self.acao_sublinhado.setCheckable(True)
        self.acao_sublinhado.setShortcut(QKeySequence.Underline)
        self.acao_sublinhado.setToolTip("Sublinhado (Ctrl+U)")
        f = self.acao_sublinhado.font()
        f.setUnderline(True)
        self.acao_sublinhado.setFont(f)
        self.acao_sublinhado.triggered.connect(self.alternar_sublinhado)
        toolbar_fonte.addAction(self.acao_sublinhado)

        self.acao_tachado = QAction("T", self)
        self.acao_tachado.setCheckable(True)
        self.acao_tachado.setShortcut(QKeySequence("Ctrl+Shift+X"))
        self.acao_tachado.setToolTip("Tachado (Ctrl+Shift+X)")
        f = self.acao_tachado.font()
        f.setStrikeOut(True)
        self.acao_tachado.setFont(f)
        self.acao_tachado.triggered.connect(self.alternar_tachado)
        toolbar_fonte.addAction(self.acao_tachado)

        toolbar_fonte.addSeparator()

        # ---- Cor da fonte / cor de realce ----
        self._cor_fonte_atual = QColor(Qt.black)
        self._cor_realce_atual = QColor(Qt.yellow)

        self.acao_cor_fonte = QAction(self._icone_cor(self._cor_fonte_atual), "Cor da fonte", self)
        self.acao_cor_fonte.setToolTip("Cor da fonte")
        self.acao_cor_fonte.triggered.connect(self.escolher_cor_fonte)
        toolbar_fonte.addAction(self.acao_cor_fonte)

        self.acao_cor_realce = QAction(self._icone_cor(self._cor_realce_atual), "Cor de realce", self)
        self.acao_cor_realce.setToolTip("Cor de realce (marca-texto)")
        self.acao_cor_realce.triggered.connect(self.escolher_cor_realce)
        toolbar_fonte.addAction(self.acao_cor_realce)

        self.acao_remover_realce = QAction("Sem realce", self)
        self.acao_remover_realce.setToolTip("Remover o realce do texto selecionado")
        self.acao_remover_realce.triggered.connect(self.remover_realce)
        toolbar_fonte.addAction(self.acao_remover_realce)

        # ==================== Seção: Parágrafo ====================
        self.addToolBarBreak()
        toolbar_paragrafo = QToolBar("Parágrafo")
        self.addToolBar(toolbar_paragrafo)

        rotulo_paragrafo = QLabel(" <b>Parágrafo</b> ")
        toolbar_paragrafo.addWidget(rotulo_paragrafo)

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
        toolbar_paragrafo.addAction(self.acao_alinhar_esquerda)

        self.acao_alinhar_centro = QAction("Centr", self)
        self.acao_alinhar_centro.setCheckable(True)
        self.acao_alinhar_centro.setToolTip("Centralizar (Ctrl+E)")
        self.acao_alinhar_centro.setShortcut(QKeySequence("Ctrl+E"))
        self.acao_alinhar_centro.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignCenter)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_centro)
        toolbar_paragrafo.addAction(self.acao_alinhar_centro)

        self.acao_alinhar_direita = QAction("Dir", self)
        self.acao_alinhar_direita.setCheckable(True)
        self.acao_alinhar_direita.setToolTip("Alinhar à direita (Ctrl+R)")
        self.acao_alinhar_direita.setShortcut(QKeySequence("Ctrl+R"))
        self.acao_alinhar_direita.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignRight)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_direita)
        toolbar_paragrafo.addAction(self.acao_alinhar_direita)

        self.acao_alinhar_justificado = QAction("Jus", self)
        self.acao_alinhar_justificado.setCheckable(True)
        self.acao_alinhar_justificado.setToolTip("Justificar (Ctrl+J)")
        self.acao_alinhar_justificado.setShortcut(QKeySequence("Ctrl+J"))
        self.acao_alinhar_justificado.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignJustify)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_justificado)
        toolbar_paragrafo.addAction(self.acao_alinhar_justificado)

        # guarda numa lista pra facilitar a sincronização com o cursor
        self._acoes_alinhamento = {
            Qt.AlignLeft: self.acao_alinhar_esquerda,
            Qt.AlignCenter: self.acao_alinhar_centro,
            Qt.AlignRight: self.acao_alinhar_direita,
            Qt.AlignJustify: self.acao_alinhar_justificado,
        }

        toolbar_paragrafo.addSeparator()

        # ---- Listas ----
        self.acao_marcadores = QAction("• Lista", self)
        self.acao_marcadores.setToolTip(
            "Marcadores com níveis"
        )
        self.acao_marcadores.triggered.connect(
            lambda: self.alternar_lista(QTextListFormat.ListDisc)
        )
        toolbar_paragrafo.addAction(self.acao_marcadores)

        self.acao_numeracao = QAction("1. Lista", self)
        self.acao_numeracao.setToolTip(
            "Marcadores numerados"
        )
        self.acao_numeracao.triggered.connect(
            lambda: self.alternar_lista(QTextListFormat.ListDecimal)
        )
        toolbar_paragrafo.addAction(self.acao_numeracao)

    @staticmethod
    def _icone_cor(cor):
        """Gera um ícone com a letra 'A' e uma barrinha colorida embaixo,
        para indicar visualmente qual cor está selecionada no botão."""
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setPen(Qt.black)
        fonte = painter.font()
        fonte.setBold(True)
        fonte.setPointSize(12)
        painter.setFont(fonte)
        painter.drawText(pixmap.rect().adjusted(0, 0, 0, -6), Qt.AlignCenter, "A")
        painter.fillRect(3, 19, 18, 4, cor)
        painter.end()
        return QIcon(pixmap)

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

    def escolher_cor_fonte(self):
        cor = QColorDialog.getColor(self._cor_fonte_atual, self, "Escolher cor da fonte")
        if not cor.isValid():
            return
        self._cor_fonte_atual = cor
        self.acao_cor_fonte.setIcon(self._icone_cor(cor))
        fmt = QTextCharFormat()
        fmt.setForeground(cor)
        self._aplicar_formato(fmt)

    def escolher_cor_realce(self):
        cor = QColorDialog.getColor(self._cor_realce_atual, self, "Escolher cor de realce")
        if not cor.isValid():
            return
        self._cor_realce_atual = cor
        self.acao_cor_realce.setIcon(self._icone_cor(cor))
        fmt = QTextCharFormat()
        fmt.setBackground(cor)
        self._aplicar_formato(fmt)

    def remover_realce(self):
        fmt = QTextCharFormat()
        fmt.setBackground(Qt.transparent)
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

    def alternar_lista(self, estilo):
        """Aplica marcadores ou numeração ao(s) parágrafo(s) atual(is).
        Clicar novamente no mesmo estilo remove a lista."""
        cursor = self.text_edit.textCursor()
        lista_atual = cursor.currentList()
        cursor.beginEditBlock()
        if lista_atual and lista_atual.format().style() == estilo:
            lista_atual.remove(cursor.block())
        else:
            fmt = QTextListFormat()
            fmt.setStyle(estilo)
            if lista_atual:
                fmt.setIndent(lista_atual.format().indent())
            cursor.createList(fmt)
        cursor.endEditBlock()
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

    def closeEvent(self, event):
        if self._confirmar_descarte():
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    janela = Editor()
    janela.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
