"""Impressão (gerando PDF, sem impressora de verdade).

Regressões: número de página aparecendo sozinho no rodapé, e a divisão das
páginas na impressão não bater com a da tela.
"""
import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrinter

from ajudas import pagina_valida

pypdf = pytest.importorskip("pypdf")
QtPdf = pytest.importorskip("PySide6.QtPdf")    # desenha a página do PDF em pixels


def _renderizar_pagina(caminho, pagina=0):
    """Desenha uma página do PDF numa imagem de fundo branco (72 dpi)."""
    documento = QtPdf.QPdfDocument()
    documento.load(str(caminho))
    assert documento.pageCount() > pagina, "o QtPdf não conseguiu abrir o PDF"
    tamanho = documento.pagePointSize(pagina)
    desenhada = documento.render(pagina, QSize(int(tamanho.width()), int(tamanho.height())))
    imagem = QImage(desenhada.size(), QImage.Format_RGB32)
    imagem.fill(Qt.white)                       # o render pode vir com fundo transparente
    pintor = QPainter(imagem)
    pintor.drawImage(0, 0, desenhada)
    pintor.end()
    return imagem


def _tem_tinta(imagem, x0, y0, x1, y1, limite=200):
    """True se existe algum pixel escuro na região (x0, y0) - (x1, y1)."""
    for y in range(max(0, y0), min(imagem.height(), y1)):
        for x in range(max(0, x0), min(imagem.width(), x1)):
            if (imagem.pixel(x, y) & 0xFF) < limite:
                return True
    return False


def _imprimir_em_pdf(janela, qtbot, caminho):
    janela.grab()
    qtbot.waitUntil(lambda: pagina_valida(janela.text_edit), timeout=2000)
    impressora = janela._preparar_impressora()
    impressora.setOutputFormat(QPrinter.PdfFormat)
    impressora.setOutputFileName(str(caminho))
    janela.text_edit.document().print_(impressora)
    return pypdf.PdfReader(str(caminho))


def test_pdf_nao_tem_numero_de_pagina(janela, qtbot, tmp_path):
    """Regressão: o Qt desenhava um número de página sozinho no rodapé.

    Olhamos os pixels da página em vez de extrair o texto do PDF: assim o teste
    não depende de como as fontes foram embutidas, e também pega um PDF em
    branco (que passaria "no vazio" numa checagem só de texto)."""
    janela.text_edit.setPlainText("Texto de teste")
    caminho = tmp_path / "a.pdf"
    _imprimir_em_pdf(janela, qtbot, caminho)

    pagina = _renderizar_pagina(caminho)
    largura, altura = pagina.width(), pagina.height()
    assert _tem_tinta(pagina, 0, 0, largura, int(altura * 0.3)), \
        "PDF em branco: o texto não foi desenhado"
    assert not _tem_tinta(pagina, 0, int(altura * 0.8), largura, altura), \
        "apareceu algo no rodapé da página (número de página?)"


def test_pdf_tem_as_mesmas_paginas_que_a_tela_mostra(janela, qtbot, tmp_path):
    ed = janela.text_edit
    ed.setPlainText("linha\n" * 150)
    leitor = _imprimir_em_pdf(janela, qtbot, tmp_path / "b.pdf")
    assert ed.document().pageCount() >= 2
    assert len(leitor.pages) == ed.document().pageCount()


@pytest.mark.parametrize("largura_mm, altura_mm, largura_pt, altura_pt", [
    (210.0, 297.0, 595.3, 841.9),      # A4
    (215.9, 279.4, 612.0, 792.0),      # Carta
])
def test_pdf_usa_o_papel_configurado(janela, qtbot, tmp_path,
                                     largura_mm, altura_mm, largura_pt, altura_pt):
    janela.text_edit.configurar_pagina(largura_mm, altura_mm, 25)
    leitor = _imprimir_em_pdf(janela, qtbot, tmp_path / "c.pdf")
    caixa = leitor.pages[0].mediabox
    assert float(caixa.width) == pytest.approx(largura_pt, abs=2)
    assert float(caixa.height) == pytest.approx(altura_pt, abs=2)


def test_imprimir_nao_marca_o_documento_como_modificado(janela, qtbot, tmp_path):
    janela.text_edit.setPlainText("Texto de teste")
    janela.text_edit.document().setModified(False)
    _imprimir_em_pdf(janela, qtbot, tmp_path / "d.pdf")
    assert not janela.text_edit.document().isModified()
