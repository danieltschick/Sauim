"""Tamanho de fonte: digitado, colado de uma página web, e o que a barra mostra.

Regressão: texto colado de um navegador vem com o tamanho em pixels (e em
pontos, herdado). O Qt dá preferência ao pixel; então a barra mostrava sempre
11 e trocar o tamanho não surtia efeito no texto.

Para cobrir mais casos, basta soltar mais arquivos .html na pasta
tests/amostras/ (o HTML que o navegador põe na área de transferência): cada
amostra entra automaticamente nos testes parametrizados abaixo.
"""
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QTextCursor, QTextFormat

from ajudas import formato_do_caractere, posicoes_de_letras, selecionar_tudo

AMOSTRAS = sorted((Path(__file__).parent / "amostras").glob("*.html"))


def _colar(ed, html):
    mime = QMimeData()
    mime.setHtml(html)
    ed.insertFromMimeData(mime)


def _fonte_de(ed, posicao):
    return formato_do_caractere(ed, posicao).font()


def _tamanho_desenhado_em_pontos(ed, posicao):
    """O tamanho que o Qt desenha para o caractere, ou None se o trecho não
    tem tamanho explícito (vale então a fonte padrão do documento)."""
    formato = formato_do_caractere(ed, posicao)
    if not (formato.hasProperty(QTextFormat.FontPointSize)
            or formato.hasProperty(QTextFormat.FontPixelSize)):
        return None
    fonte = formato.font()
    dpi = ed.logicalDpiY() or 96
    if fonte.pixelSize() > 0:
        return fonte.pixelSize() * 72.0 / dpi
    if fonte.pointSizeF() > 0:
        return fonte.pointSizeF()
    return None


# ---------- texto digitado ----------

def test_trocar_tamanho_no_texto_digitado(janela, qtbot):
    ed = janela.text_edit
    qtbot.keyClicks(ed, "abcdef")
    selecionar_tudo(ed)
    janela.alterar_tamanho_fonte("20")
    for i in posicoes_de_letras(ed):
        assert _fonte_de(ed, i).pointSizeF() == 20


def test_texto_novo_mostra_arial_11_na_barra(janela):
    familia, pontos = janela._fonte_efetiva()
    assert familia == "Arial"
    assert pontos == pytest.approx(11.0)


# ---------- texto colado de uma página web ----------

@pytest.mark.parametrize("amostra", AMOSTRAS, ids=lambda p: p.name)
def test_barra_mostra_o_tamanho_que_o_qt_desenha(janela, amostra):
    ed = janela.text_edit
    _colar(ed, amostra.read_text(encoding="utf-8"))
    letras = posicoes_de_letras(ed)
    assert letras, "a amostra não colou nenhum texto"

    for i in letras[:: max(1, len(letras) // 12)]:
        esperado = _tamanho_desenhado_em_pontos(ed, i)
        if esperado is None:
            continue
        cursor = QTextCursor(ed.document())
        cursor.setPosition(i + 1)             # cursor logo depois da letra
        ed.setTextCursor(cursor)
        _familia, pontos = janela._fonte_efetiva()
        assert pontos == pytest.approx(esperado, abs=0.01), f"posição {i}"


@pytest.mark.parametrize("amostra", AMOSTRAS, ids=lambda p: p.name)
def test_novo_tamanho_vale_no_texto_colado(janela, amostra):
    ed = janela.text_edit
    _colar(ed, amostra.read_text(encoding="utf-8"))
    selecionar_tudo(ed)

    janela.alterar_tamanho_fonte("24")

    for i in posicoes_de_letras(ed):
        fonte = _fonte_de(ed, i)
        assert fonte.pointSizeF() == 24, f"posição {i}: ainda não está em 24 pt"
        assert fonte.pixelSize() == -1, f"posição {i}: sobrou tamanho em pixels"


@pytest.mark.parametrize("amostra", AMOSTRAS, ids=lambda p: p.name)
def test_trocar_tamanho_so_da_selecao_no_texto_colado(janela, amostra):
    ed = janela.text_edit
    _colar(ed, amostra.read_text(encoding="utf-8"))
    letras = posicoes_de_letras(ed)
    antes = {i: _tamanho_desenhado_em_pontos(ed, i) for i in letras}

    # seleciona só as 3 primeiras letras
    cursor = QTextCursor(ed.document())
    cursor.setPosition(letras[0])
    cursor.setPosition(letras[2] + 1, QTextCursor.KeepAnchor)
    ed.setTextCursor(cursor)
    janela.alterar_tamanho_fonte("30")

    for i in letras[:3]:
        assert _fonte_de(ed, i).pointSizeF() == 30
    for i in letras[3:]:
        assert _tamanho_desenhado_em_pontos(ed, i) == antes[i], f"posição {i} mudou sem querer"


@pytest.mark.parametrize("amostra", AMOSTRAS, ids=lambda p: p.name)
def test_tamanho_vale_no_que_for_digitado_depois_do_colado(janela, qtbot, amostra):
    ed = janela.text_edit
    _colar(ed, amostra.read_text(encoding="utf-8"))
    cursor = ed.textCursor()
    cursor.movePosition(QTextCursor.End)
    ed.setTextCursor(cursor)

    janela.alterar_tamanho_fonte("30")      # sem seleção: vale para o que vier
    inicio = len(ed.toPlainText())
    qtbot.keyClicks(ed, "xyz")

    for i in range(inicio, inicio + 3):
        fonte = _fonte_de(ed, i)
        assert fonte.pointSizeF() == 30 and fonte.pixelSize() == -1, f"posição {i}"


@pytest.mark.parametrize("amostra", AMOSTRAS, ids=lambda p: p.name)
def test_desfazer_a_troca_de_tamanho_volta_tudo_de_uma_vez(janela, qtbot, amostra):
    ed = janela.text_edit
    _colar(ed, amostra.read_text(encoding="utf-8"))
    letras = posicoes_de_letras(ed)
    antes = {i: _tamanho_desenhado_em_pontos(ed, i) for i in letras}
    selecionar_tudo(ed)

    janela.alterar_tamanho_fonte("24")
    qtbot.keyClick(ed, Qt.Key_Z, Qt.ControlModifier)
    qtbot.wait(60)

    for i in letras:
        assert _tamanho_desenhado_em_pontos(ed, i) == antes[i], f"posição {i}"
