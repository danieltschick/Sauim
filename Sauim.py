"""
Sauim - Editor de Texto v1
Requisitos: pip install PySide6
Execução: python editor.py

Formato nativo: .saui (JSON contendo o HTML do documento + metadados de
página). HTML e TXT continuam disponíveis como formatos de exportação.
"""
import sys
import os
import json
import base64
from PySide6.QtCore import Qt, QSizeF, QTimer, QBuffer, QIODevice, QRect
from PySide6.QtGui import (
    QTextCharFormat, QFont, QTextCursor, QPainter, QPen,
    QColor, QAction, QKeySequence, QPageSize, QImage,
    QTextImageFormat, QIcon
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QFileDialog,
    QMessageBox, QStatusBar, QWidget, QVBoxLayout, QFontComboBox, QComboBox,
    QColorDialog, QLabel, QDialog, QDialogButtonBox, QFormLayout, QDoubleSpinBox
)
from PySide6.QtGui import QActionGroup, QIntValidator, QIcon, QPixmap, QTextListFormat

# ---------- Configurações de página (em milímetros) ----------
MM_TO_PX = 96 / 25.4  # 96 DPI (padrão de tela)

PAGE_WIDTH_MM_PADRAO = 210     # A4 — usado só como valor inicial;
PAGE_HEIGHT_MM_PADRAO = 297    # o tamanho de página real agora é
MARGIN_MM_PADRAO = 25          # configurável por documento (veja
                                # PagedTextEdit.configurar_pagina).

# Papéis predefinidos: nome -> (largura_mm, altura_mm)
PAPEIS_PREDEFINIDOS = {
    "A4 (210 × 297 mm)": (210.0, 297.0),
    "Carta / Letter (215,9 × 279,4 mm)": (215.9, 279.4),
    "Ofício / Legal (215,9 × 355,6 mm)": (215.9, 355.6),
}

# ---------- Formato nativo do Sauim ----------
NOME_APP = "Sauim"
EXTENSAO_NATIVA = ".saui"
VERSAO_FORMATO = 1

TAMANHO_ALCA_PX = 8  # tamanho do quadradinho de redimensionar imagem


def caminho_recurso(nome_arquivo):
    """Encontra um arquivo ao lado do script — e também funciona depois de
    empacotado com o PyInstaller (que extrai os arquivos embutidos numa
    pasta temporária indicada por sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome_arquivo)


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
        self._reaplicacao_agendada = False
        self.setLineWrapMode(QTextEdit.FixedPixelWidth)
        self.configurar_pagina(
            PAGE_WIDTH_MM_PADRAO, PAGE_HEIGHT_MM_PADRAO, MARGIN_MM_PADRAO
        )

        # Renumeração hierárquica de listas numeradas (1 / 1.1 / 1.1.1)
        self._renumerando = False
        self._renumeracao_agendada = False
        self.document().contentsChanged.connect(self._agendar_renumeracao)

        # Redimensionamento de imagem por arraste
        self._imagem_selecionada_pos = None
        self._redimensionando = False
        self._alca_ativa = None
        self._ponto_inicio_arraste = None
        self._retangulo_inicio = None
        self.setMouseTracking(True)

    def configurar_pagina(self, largura_mm, altura_mm, margem_mm):
        """Define o tamanho da página (e a margem uniforme) em milímetros e
        aplica tudo que depende disso: largura de quebra de linha do texto,
        margem interna do documento e tamanho de página usado na contagem
        de páginas. Pode ser chamado a qualquer momento (por exemplo, ao
        abrir um arquivo ou pelo diálogo "Configurar página")."""
        self.largura_mm = float(largura_mm)
        self.altura_mm = float(altura_mm)
        self.margem_mm = float(margem_mm)

        self.largura_px = self.largura_mm * MM_TO_PX
        self.altura_px = self.altura_mm * MM_TO_PX
        self.margem_px = self.margem_mm * MM_TO_PX

        self.setLineWrapColumnOrWidth(int(self.largura_px))
        self.setFixedWidth(int(self.largura_px) + 4)
        self.document().setDocumentMargin(self.margem_px)
        self.document().setPageSize(QSizeF(self.largura_px, self.altura_px))
        self.viewport().update()

    def _conferir_tamanho_pagina(self):
        """Autocorreção: se, por qualquer motivo, o Qt tiver alterado o
        tamanho de página do documento (ele redefine esse valor em alguns
        momentos por conta própria), agenda a reaplicação. É chamado a cada
        repintura; quando está tudo certo, custa só uma comparação. A
        correção é adiada para o próximo ciclo de eventos, pra não mexer
        no documento no meio de um desenho."""
        esperado = QSizeF(self.largura_px, self.altura_px)
        if self.document().pageSize() != esperado and not self._reaplicacao_agendada:
            self._reaplicacao_agendada = True
            QTimer.singleShot(0, self._executar_reaplicacao)

    def _executar_reaplicacao(self):
        self._reaplicacao_agendada = False
        self.reaplicar_tamanho_pagina()

    def reaplicar_tamanho_pagina(self):
        """Reaplica o tamanho de página ao documento, sempre (sem comparar
        antes), o que também obriga o layout a ser refeito com a paginação
        correta. Deve ser chamado depois de carregar um texto novo
        (abrir arquivo, novo documento), que é quando a paginação na tela
        aparece errada."""
        self.document().setPageSize(QSizeF(self.largura_px, self.altura_px))
        self.viewport().update()

    def canInsertFromMimeData(self, source):
        if source.hasImage():
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage():
            imagem = QImage(source.imageData())
            if not imagem.isNull():
                self._inserir_imagem(imagem)
                return
        super().insertFromMimeData(source)

    def _inserir_imagem(self, imagem):
        # Limita a largura da imagem à área útil da página (largura menos
        # as margens), pra não sair maior que a folha.
        largura_maxima = int(self.largura_px - 2 * self.margem_px)
        if imagem.width() > largura_maxima:
            imagem = imagem.scaledToWidth(largura_maxima, Qt.SmoothTransformation)

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        imagem.save(buffer, "PNG")
        dados_base64 = base64.b64encode(buffer.data().data()).decode("ascii")
        buffer.close()

        # Usar a própria data URI como "nome" do recurso faz o Qt escrever
        # a imagem embutida direto no HTML exportado (toHtml()/.saui),
        # em vez de uma referência externa que se perderia ao reabrir o
        # arquivo em outro computador.
        uri = f"data:image/png;base64,{dados_base64}"
        cursor = self.textCursor()
        cursor.insertImage(imagem, uri)

    # ---------------- Seleção e redimensionamento de imagem ----------------
    def _posicao_imagem_no_ponto(self, ponto):
        """Retorna a posição (índice do caractere) da imagem sob o ponto
        dado no viewport, ou None se não houver imagem ali."""
        cursor_aprox = self.cursorForPosition(ponto)
        for pos in (cursor_aprox.position(), cursor_aprox.position() - 1):
            if 0 <= pos < self.document().characterCount() - 1:
                c = QTextCursor(self.document())
                c.setPosition(pos)
                c.setPosition(pos + 1, QTextCursor.KeepAnchor)
                if c.charFormat().isImageFormat():
                    rect = self._retangulo_imagem(pos)
                    if rect.adjusted(-2, -2, 2, 2).contains(ponto):
                        return pos
        return None

    def _retangulo_imagem(self, pos):
        """Estima o retângulo (no viewport) ocupado pela imagem que está
        na posição pos, usando o cursor antes/depois dela como referência."""
        cursor_antes = QTextCursor(self.document())
        cursor_antes.setPosition(pos)
        rect_antes = self.cursorRect(cursor_antes)

        cursor_depois = QTextCursor(self.document())
        cursor_depois.setPosition(pos + 1)
        rect_depois = self.cursorRect(cursor_depois)

        largura = rect_depois.left() - rect_antes.left()
        return QRect(rect_antes.left(), rect_antes.top(), largura, rect_antes.height())

    def _alca_sob_ponto(self, ponto):
        if self._imagem_selecionada_pos is None:
            return None
        rect = self._retangulo_imagem(self._imagem_selecionada_pos)
        metade = TAMANHO_ALCA_PX // 2
        alcas = {
            "tl": rect.topLeft(),
            "tr": rect.topRight(),
            "bl": rect.bottomLeft(),
            "br": rect.bottomRight(),
        }
        for nome, centro in alcas.items():
            alvo = QRect(centro.x() - metade, centro.y() - metade, TAMANHO_ALCA_PX, TAMANHO_ALCA_PX)
            if alvo.contains(ponto):
                return nome
        return None

    def mousePressEvent(self, event):
        alca = self._alca_sob_ponto(event.pos())
        if alca:
            self._redimensionando = True
            self._alca_ativa = alca
            self._ponto_inicio_arraste = event.pos()
            self._retangulo_inicio = self._retangulo_imagem(self._imagem_selecionada_pos)
            return

        nova_selecao = self._posicao_imagem_no_ponto(event.pos())
        self._imagem_selecionada_pos = nova_selecao
        self.viewport().update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._redimensionando:
            self._atualizar_redimensionamento(event.pos(), event.modifiers())
            return

        if self._alca_sob_ponto(event.pos()):
            self.viewport().setCursor(Qt.SizeFDiagCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._redimensionando:
            self._redimensionando = False
            self._alca_ativa = None
            return
        super().mouseReleaseEvent(event)

    def _atualizar_redimensionamento(self, ponto, modificadores=Qt.NoModifier):
        dx = ponto.x() - self._ponto_inicio_arraste.x()
        dy = ponto.y() - self._ponto_inicio_arraste.y()
        r = self._retangulo_inicio

        largura, altura = r.width(), r.height()
        if self._alca_ativa == "br":
            largura, altura = r.width() + dx, r.height() + dy
        elif self._alca_ativa == "bl":
            largura, altura = r.width() - dx, r.height() + dy
        elif self._alca_ativa == "tr":
            largura, altura = r.width() + dx, r.height() - dy
        elif self._alca_ativa == "tl":
            largura, altura = r.width() - dx, r.height() - dy

        # Shift pressionado: trava a proporção original da imagem, usando
        # a maior variação (largura ou altura) como referência.
        if bool(modificadores & Qt.ShiftModifier) and r.width() > 0 and r.height() > 0:
            proporcao = r.width() / r.height()
            if abs(largura - r.width()) >= abs(altura - r.height()):
                altura = largura / proporcao
            else:
                largura = altura * proporcao

        largura = max(20, int(largura))
        altura = max(20, int(altura))

        cursor = QTextCursor(self.document())
        cursor.setPosition(self._imagem_selecionada_pos)
        cursor.setPosition(self._imagem_selecionada_pos + 1, QTextCursor.KeepAnchor)
        fmt = cursor.charFormat().toImageFormat()
        fmt.setWidth(largura)
        fmt.setHeight(altura)
        cursor.setCharFormat(fmt)

        self.viewport().update()

    def paintEvent(self, event):
        self._conferir_tamanho_pagina()
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor(180, 180, 180), 1, Qt.DashLine))

        page_height = self.altura_px
        offset = self.verticalScrollBar().value()
        y = page_height - (offset % page_height)
        while y < self.viewport().height():
            painter.drawLine(0, int(y), self.viewport().width(), int(y))
            y += page_height

        if self._imagem_selecionada_pos is not None:
            rect = self._retangulo_imagem(self._imagem_selecionada_pos)
            painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.SolidLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            painter.setBrush(QColor(0, 120, 215))
            metade = TAMANHO_ALCA_PX // 2
            for ponto in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
                painter.drawRect(ponto.x() - metade, ponto.y() - metade,
                                  TAMANHO_ALCA_PX, TAMANHO_ALCA_PX)

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
            if cursor.currentList():
                doc = self.document()
                inicio = min(cursor.anchor(), cursor.position())
                fim = max(cursor.anchor(), cursor.position())
                bloco = doc.findBlock(inicio)
                ultimo = doc.findBlock(fim)
                blocos = []
                while bloco.isValid():
                    blocos.append(bloco)
                    if bloco.position() >= ultimo.position():
                        break
                    bloco = bloco.next()

                edicao = QTextCursor(doc)
                edicao.beginEditBlock()
                for b in blocos:
                    lista = b.textList()
                    if lista is None:
                        continue
                    nivel = lista.format().indent()
                    novo_nivel = nivel - 1 if e_shift_tab else nivel + 1
                    if novo_nivel < 1:
                        lista.remove(b)
                    elif novo_nivel <= 9:
                        fmt = QTextListFormat()
                        fmt.setStyle(lista.format().style())
                        fmt.setIndent(novo_nivel)
                        QTextCursor(b).createList(fmt)
                edicao.endEditBlock()
                # A numeração composta (1.1, 2.1.3...) é ajustada logo em
                # seguida pelo renumerador, que reage a qualquer mudança.
                return  # não repassa o Tab pro comportamento padrão

        super().keyPressEvent(event)

    # ---------------- Numeração hierárquica (1 / 1.1 / 1.1.1) ----------------
    def _agendar_renumeracao(self):
        # Não mexemos no documento dentro do próprio sinal de mudança;
        # deixamos para o próximo ciclo do laço de eventos.
        if self._renumerando or self._renumeracao_agendada:
            return
        self._renumeracao_agendada = True
        QTimer.singleShot(0, self._executar_renumeracao)

    def _executar_renumeracao(self):
        self._renumeracao_agendada = False
        self.renumerar_listas()

    def renumerar_listas(self):
        """Distribui os itens de listas numeradas em listas do Qt com o
        prefixo certo: nível 1 -> "1." ; nível 2 -> "1.1" ; nível 3 ->
        "1.1.1"... O Qt não tem numeração composta nativa, então cada grupo
        de filhos do mesmo pai vira uma lista com o prefixo do pai. Só
        altera o documento se algo estiver fora do lugar."""
        doc = self.document()
        modificado_antes = doc.isModified()
        self._renumerando = True
        edicao = QTextCursor(doc)
        edicao_aberta = False
        try:
            contadores = []
            listas = {}            # (nivel, caminho) -> (lista, indice)
            reivindicados = set()  # índices de listas já em uso

            bloco = doc.begin()
            while bloco.isValid():
                lista = bloco.textList()
                if lista is None or lista.format().style() != QTextListFormat.ListDecimal:
                    contadores = []
                    listas = {}
                    bloco = bloco.next()
                    continue

                nivel = max(1, lista.format().indent())
                del contadores[nivel:]
                while len(contadores) < nivel:
                    contadores.append(1 if len(contadores) < nivel - 1 else 0)
                contadores[nivel - 1] += 1

                caminho = tuple(contadores[:nivel - 1])
                chave = (nivel, caminho)
                prefixo = ".".join(str(n) for n in caminho) + "." if caminho else ""
                sufixo = "." if nivel == 1 else ""
                indice_atual = bloco.blockFormat().objectIndex()

                destino = listas.get(chave)
                if destino is None:
                    fmt_atual = lista.format()
                    reaproveitavel = (
                        indice_atual not in reivindicados
                        and fmt_atual.indent() == nivel
                        and fmt_atual.numberPrefix() == prefixo
                        and fmt_atual.numberSuffix() == sufixo
                    )
                    if reaproveitavel:
                        destino = (lista, indice_atual)
                    else:
                        if not edicao_aberta:
                            edicao.joinPreviousEditBlock()
                            edicao_aberta = True
                        fmt = QTextListFormat()
                        fmt.setStyle(QTextListFormat.ListDecimal)
                        fmt.setIndent(nivel)
                        fmt.setNumberPrefix(prefixo)
                        fmt.setNumberSuffix(sufixo)
                        nova_lista = QTextCursor(bloco).createList(fmt)
                        destino = (nova_lista, bloco.blockFormat().objectIndex())
                    reivindicados.add(destino[1])
                    listas[chave] = destino
                elif indice_atual != destino[1]:
                    if not edicao_aberta:
                        edicao.joinPreviousEditBlock()
                        edicao_aberta = True
                    destino[0].add(bloco)

                bloco = bloco.next()
        finally:
            if edicao_aberta:
                edicao.endEditBlock()
            self._renumerando = False
            if not modificado_antes:
                doc.setModified(False)


class ConfigurarPaginaDialog(QDialog):
    """Diálogo para escolher o tamanho do papel, a orientação e a margem."""

    PERSONALIZADO = "Personalizado"

    def __init__(self, largura_mm, altura_mm, margem_mm, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar página")

        self.combo_papel = QComboBox()
        self.combo_papel.addItems(list(PAPEIS_PREDEFINIDOS.keys()) + [self.PERSONALIZADO])

        self.combo_orientacao = QComboBox()
        self.combo_orientacao.addItems(["Retrato", "Paisagem"])

        self.spin_largura = QDoubleSpinBox()
        self.spin_altura = QDoubleSpinBox()
        for spin in (self.spin_largura, self.spin_altura):
            spin.setRange(50.0, 1000.0)
            spin.setDecimals(1)
            spin.setSuffix(" mm")

        self.spin_margem = QDoubleSpinBox()
        self.spin_margem.setRange(0.0, 100.0)
        self.spin_margem.setDecimals(1)
        self.spin_margem.setSuffix(" mm")
        self.spin_margem.setValue(margem_mm)

        formulario = QFormLayout()
        formulario.addRow("Papel:", self.combo_papel)
        formulario.addRow("Orientação:", self.combo_orientacao)
        formulario.addRow("Largura:", self.spin_largura)
        formulario.addRow("Altura:", self.spin_altura)
        formulario.addRow("Margem (todos os lados):", self.spin_margem)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self._validar_e_aceitar)
        botoes.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(formulario)
        layout.addWidget(botoes)

        self._selecionar_papel_atual(largura_mm, altura_mm)
        self.combo_papel.currentIndexChanged.connect(self._atualizar_campos)
        self.combo_orientacao.currentIndexChanged.connect(self._atualizar_campos)
        self._atualizar_campos()

    def _selecionar_papel_atual(self, largura_mm, altura_mm):
        """Pré-seleciona o papel/orientação que correspondem à página atual
        (ou 'Personalizado' se não bater com nenhum predefinido)."""
        for nome, (larg, alt) in PAPEIS_PREDEFINIDOS.items():
            if abs(largura_mm - larg) < 0.1 and abs(altura_mm - alt) < 0.1:
                self.combo_papel.setCurrentText(nome)
                self.combo_orientacao.setCurrentText("Retrato")
                return
            if abs(largura_mm - alt) < 0.1 and abs(altura_mm - larg) < 0.1:
                self.combo_papel.setCurrentText(nome)
                self.combo_orientacao.setCurrentText("Paisagem")
                return
        self.combo_papel.setCurrentText(self.PERSONALIZADO)
        self.spin_largura.setValue(largura_mm)
        self.spin_altura.setValue(altura_mm)

    def _atualizar_campos(self):
        papel = self.combo_papel.currentText()
        personalizado = papel == self.PERSONALIZADO

        # Largura/altura só são editáveis no modo personalizado;
        # orientação só faz sentido para papéis predefinidos.
        self.spin_largura.setEnabled(personalizado)
        self.spin_altura.setEnabled(personalizado)
        self.combo_orientacao.setEnabled(not personalizado)

        if not personalizado:
            larg, alt = PAPEIS_PREDEFINIDOS[papel]
            if self.combo_orientacao.currentText() == "Paisagem":
                larg, alt = alt, larg
            self.spin_largura.setValue(larg)
            self.spin_altura.setValue(alt)

    def _validar_e_aceitar(self):
        menor_lado = min(self.spin_largura.value(), self.spin_altura.value())
        if self.spin_margem.value() * 2 >= menor_lado:
            QMessageBox.warning(
                self, "Margem inválida",
                "A margem é grande demais para esse tamanho de papel — "
                "não sobraria espaço para o texto."
            )
            return
        self.accept()

    def valores(self):
        return (
            self.spin_largura.value(),
            self.spin_altura.value(),
            self.spin_margem.value(),
        )


class Editor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{NOME_APP} — Sem título")
        self.resize(1000, 800)

        icone = caminho_recurso("sauim.ico")
        if os.path.exists(icone):
            self.setWindowIcon(QIcon(icone))

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

        acao_config_pagina = QAction("Configurar página...", self)
        acao_config_pagina.triggered.connect(self.configurar_pagina_dialogo)
        menu_arquivo.addAction(acao_config_pagina)

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
        # self.addToolBarBreak()
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
        self.acao_alinhar_esquerda.setToolTip("Alinhar à esquerda (Ctrl+Q)")
        self.acao_alinhar_esquerda.setShortcut(QKeySequence("Ctrl+Q"))
        self.acao_alinhar_esquerda.triggered.connect(
            lambda: self.definir_alinhamento(Qt.AlignLeft)
        )
        grupo_alinhamento.addAction(self.acao_alinhar_esquerda)
        toolbar_paragrafo.addAction(self.acao_alinhar_esquerda)

        self.acao_alinhar_centro = QAction("Centr.", self)
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
        self.acao_alinhar_direita.setToolTip("Alinhar à direita (Ctrl+G)")
        self.acao_alinhar_direita.setShortcut(QKeySequence("Ctrl+G"))
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
            "Marcadores (com o cursor na lista: Tab avança um nível, "
            "Shift+Tab volta um nível)"
        )
        self.acao_marcadores.triggered.connect(
            lambda: self.alternar_lista(QTextListFormat.ListDisc)
        )
        toolbar_paragrafo.addAction(self.acao_marcadores)

        self.acao_numeracao = QAction("1. Lista", self)
        self.acao_numeracao.setToolTip(
            "Numeração (com o cursor na lista: Tab avança um nível, "
            "Shift+Tab volta um nível)"
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
            self.text_edit.reaplicar_tamanho_pagina()
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
                # Aplica primeiro o tamanho de página gravado no arquivo,
                # pra o texto já ser carregado com a largura certa.
                pagina = dados.get("pagina", {})
                self.text_edit.configurar_pagina(
                    pagina.get("largura_mm", PAGE_WIDTH_MM_PADRAO),
                    pagina.get("altura_mm", PAGE_HEIGHT_MM_PADRAO),
                    pagina.get("margem_mm", MARGIN_MM_PADRAO),
                )
                self.text_edit.setHtml(dados.get("conteudo_html", ""))
            elif caminho.lower().endswith(".html"):
                with open(caminho, "r", encoding="utf-8") as f:
                    self.text_edit.setHtml(f.read())
            else:
                with open(caminho, "r", encoding="utf-8") as f:
                    self.text_edit.setPlainText(f.read())
        except Exception as e:
            QMessageBox.critical(self, "Erro ao abrir", str(e))
            return
        self.text_edit.reaplicar_tamanho_pagina()
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
                        "largura_mm": self.text_edit.largura_mm,
                        "altura_mm": self.text_edit.altura_mm,
                        "margem_mm": self.text_edit.margem_mm,
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
    def configurar_pagina_dialogo(self):
        dialogo = ConfigurarPaginaDialog(
            self.text_edit.largura_mm,
            self.text_edit.altura_mm,
            self.text_edit.margem_mm,
            self,
        )
        if dialogo.exec() == QDialog.Accepted:
            largura, altura, margem = dialogo.valores()
            self.text_edit.configurar_pagina(largura, altura, margem)
            # o tamanho da página é salvo junto com o documento
            self.text_edit.document().setModified(True)
            self._atualizar_status()

    def _preparar_impressora(self):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(
            QPageSize(
                QSizeF(self.text_edit.largura_mm, self.text_edit.altura_mm),
                QPageSize.Millimeter,
            )
        )
        # fullPage(True) faz a impressora entregar a página inteira pro
        # documento, sem reservar espaço extra nas bordas — é isso que
        # impede o Qt de "ter onde" desenhar o número de página sozinho.
        # A margem visual continua vindo do document.setDocumentMargin(),
        # já usado pra exibição em tela, então não precisamos (nem
        # devemos) mexer no tamanho de página do documento pra imprimir —
        # isso foi o que causou o texto minúsculo na tentativa anterior.
        printer.setFullPage(True)
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
    icone = caminho_recurso("sauim.ico")
    if os.path.exists(icone):
        app.setWindowIcon(QIcon(icone))
    janela = Editor()
    janela.show()
    # Depois que a janela já apareceu e o primeiro ciclo de eventos rodou.
    QTimer.singleShot(0, janela.text_edit.reaplicar_tamanho_pagina)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
