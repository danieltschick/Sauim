"""Listas (Tab / Shift+Tab, numeração hierárquica) e Desfazer / Refazer."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextListFormat

from ajudas import (formato_do_caractere, indent_da_lista, lista_do_bloco,
                    selecionar_tudo)


def _criar_lista_numerada(janela, qtbot, itens=("Alfa", "Beta", "Gama")):
    ed = janela.text_edit
    ed.setPlainText("\n".join(itens))
    selecionar_tudo(ed)
    janela.alternar_lista(QTextListFormat.ListDecimal)
    qtbot.wait(60)          # a renumeração roda no ciclo de eventos seguinte


def _cursor_no_item(ed, numero, deslocamento=2):
    """Põe o cursor no meio do item `numero` e devolve a posição."""
    bloco = ed.document().findBlockByNumber(numero)
    cursor = ed.textCursor()
    cursor.setPosition(bloco.position() + deslocamento)
    ed.setTextCursor(cursor)
    return cursor.position()


def _ctrl_z(qtbot, ed):
    qtbot.keyClick(ed, Qt.Key_Z, Qt.ControlModifier)
    qtbot.wait(60)


def _ctrl_y(qtbot, ed):
    qtbot.keyClick(ed, Qt.Key_Y, Qt.ControlModifier)
    qtbot.wait(60)


# ---------- Tab / Shift+Tab ----------

def test_tab_aumenta_o_nivel_e_cria_o_prefixo(janela, qtbot):
    _criar_lista_numerada(janela, qtbot)
    ed = janela.text_edit
    assert [indent_da_lista(ed, n) for n in range(3)] == [1, 1, 1]

    _cursor_no_item(ed, 1)
    qtbot.keyClick(ed, Qt.Key_Tab)
    qtbot.wait(60)

    lista = lista_do_bloco(ed, 1)
    assert lista.format().indent() == 2
    assert lista.format().numberPrefix() == "1."      # Beta vira "1.1"
    assert indent_da_lista(ed, 0) == 1
    assert indent_da_lista(ed, 2) == 1


def test_numeracao_do_nivel_principal_continua_depois_de_aninhar(janela, qtbot):
    """Alfa = 1, Beta (aninhado) = 1.1, Gama continua o nível principal = 2."""
    _criar_lista_numerada(janela, qtbot)
    ed = janela.text_edit
    _cursor_no_item(ed, 1)
    qtbot.keyClick(ed, Qt.Key_Tab)
    qtbot.wait(60)

    bloco_gama = ed.document().findBlockByNumber(2)
    assert bloco_gama.textList().itemNumber(bloco_gama) == 1    # 0-based: "2."


def test_shift_tab_volta_um_nivel(janela, qtbot):
    _criar_lista_numerada(janela, qtbot)
    ed = janela.text_edit
    _cursor_no_item(ed, 1)
    qtbot.keyClick(ed, Qt.Key_Tab)
    qtbot.wait(60)
    qtbot.keyClick(ed, Qt.Key_Backtab)
    qtbot.wait(60)

    lista = lista_do_bloco(ed, 1)
    assert lista.format().indent() == 1
    assert lista.format().numberPrefix() == ""
    assert lista.format().numberSuffix() == "."


def test_shift_tab_no_primeiro_nivel_tira_o_item_da_lista(janela, qtbot):
    _criar_lista_numerada(janela, qtbot)
    ed = janela.text_edit
    _cursor_no_item(ed, 1)
    qtbot.keyClick(ed, Qt.Key_Backtab)
    qtbot.wait(60)

    assert lista_do_bloco(ed, 1) is None
    assert lista_do_bloco(ed, 0) is not None
    assert lista_do_bloco(ed, 2) is not None


def test_tab_fora_de_lista_insere_tabulacao(janela, qtbot):
    ed = janela.text_edit
    ed.setPlainText("abc")
    cursor = ed.textCursor()
    cursor.movePosition(QTextCursor.End)
    ed.setTextCursor(cursor)
    qtbot.keyClick(ed, Qt.Key_Tab)
    assert "\t" in ed.toPlainText()


# ---------- Desfazer / Refazer ----------

def test_desfazer_depois_do_tab_volta_nivel_e_numeracao_juntos(janela, qtbot):
    """Regressão: a renumeração é incorporada ao passo do Tab, então um único
    Ctrl+Z desfaz os dois (e a numeração não fica inconsistente)."""
    _criar_lista_numerada(janela, qtbot)
    ed = janela.text_edit
    _cursor_no_item(ed, 1)
    qtbot.keyClick(ed, Qt.Key_Tab)
    qtbot.wait(60)

    _ctrl_z(qtbot, ed)

    lista = lista_do_bloco(ed, 1)
    assert lista.format().indent() == 1
    assert lista.format().numberPrefix() == ""
    assert lista.format().numberSuffix() == "."


def test_desfazer_depois_do_tab_mantem_o_cursor(janela, qtbot):
    """Regressão: depois de Tab + Ctrl+Z o cursor ia para o início do texto."""
    _criar_lista_numerada(janela, qtbot)
    ed = janela.text_edit
    posicao = _cursor_no_item(ed, 1)
    qtbot.keyClick(ed, Qt.Key_Tab)
    qtbot.wait(60)

    _ctrl_z(qtbot, ed)

    assert ed.textCursor().position() == posicao
    assert not ed.textCursor().hasSelection()


def test_desfazer_e_refazer_o_tab(janela, qtbot):
    _criar_lista_numerada(janela, qtbot)
    ed = janela.text_edit
    posicao = _cursor_no_item(ed, 1)
    qtbot.keyClick(ed, Qt.Key_Tab)
    qtbot.wait(60)

    _ctrl_z(qtbot, ed)
    assert indent_da_lista(ed, 1) == 1
    _ctrl_y(qtbot, ed)
    assert indent_da_lista(ed, 1) == 2
    assert ed.textCursor().position() == posicao


def test_desfazer_formatacao_mantem_a_selecao(janela, qtbot):
    """Desfazer uma mudança só de formatação não move a seleção."""
    ed = janela.text_edit
    ed.setPlainText("Hello world")
    cursor = ed.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.KeepAnchor)
    ed.setTextCursor(cursor)

    janela.acao_negrito.trigger()
    assert formato_do_caractere(ed, 6).font().bold()

    _ctrl_z(qtbot, ed)

    assert not formato_do_caractere(ed, 6).font().bold()
    assert (ed.textCursor().selectionStart(), ed.textCursor().selectionEnd()) == (6, 11)


def test_desfazer_e_refazer_texto_digitado(janela, qtbot):
    ed = janela.text_edit
    qtbot.keyClicks(ed, "abc")
    com_texto = ed.toPlainText()

    _ctrl_z(qtbot, ed)
    assert ed.toPlainText() != com_texto

    _ctrl_y(qtbot, ed)
    assert ed.toPlainText() == com_texto
