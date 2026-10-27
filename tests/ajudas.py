"""Funções auxiliares usadas por vários testes (não são testes)."""
from PySide6.QtGui import QTextCursor


def pagina_valida(ed):
    """True se o documento tem o tamanho de página configurado (altura válida).

    Sem altura válida o Qt trata o documento como "sem paginação": nem a tela
    mostra as quebras no lugar certo, nem a impressão respeita o papel.
    """
    tamanho = ed.document().pageSize()
    return (abs(tamanho.width() - ed.largura_px) < 0.5
            and abs(tamanho.height() - ed.altura_px) < 0.5)


def formato_do_caractere(ed, posicao):
    """Formato de caractere do caractere que começa em `posicao`."""
    c = QTextCursor(ed.document())
    c.setPosition(posicao)
    c.setPosition(posicao + 1, QTextCursor.KeepAnchor)
    return c.charFormat()


def posicoes_de_letras(ed):
    """Posições (no documento) dos caracteres que são letras ou números."""
    return [i for i, ch in enumerate(ed.toPlainText()) if ch.isalnum()]


def selecionar_tudo(ed):
    c = ed.textCursor()
    c.select(QTextCursor.Document)
    ed.setTextCursor(c)


def indent_da_lista(ed, numero_do_bloco):
    """Nível (indent) da lista a que o bloco pertence; 0 se não estiver em lista."""
    lista = ed.document().findBlockByNumber(numero_do_bloco).textList()
    return lista.format().indent() if lista else 0


def lista_do_bloco(ed, numero_do_bloco):
    return ed.document().findBlockByNumber(numero_do_bloco).textList()
