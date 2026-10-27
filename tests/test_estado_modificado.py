"""O Sauim só pode perguntar "salvar alterações?" se o documento foi mesmo
modificado (regressão: o documento já nascia marcado como modificado)."""
from PySide6.QtWidgets import QFileDialog, QMessageBox


def _responder(monkeypatch, resposta):
    """Troca o guarda de diálogos: QMessageBox.question passa a devolver
    `resposta`. Devolve a lista onde cada pergunta feita é registrada."""
    perguntas = []

    def _question(*args, **kwargs):
        perguntas.append(args)
        return resposta

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_question))
    return perguntas


def test_documento_recem_aberto_nao_esta_modificado(janela):
    assert not janela.text_edit.document().isModified()


def test_digitar_marca_como_modificado(janela, qtbot):
    qtbot.keyClicks(janela.text_edit, "a")
    assert janela.text_edit.document().isModified()


def test_abrir_sem_alterar_nao_pergunta_nada(janela, criar_saui, monkeypatch):
    """Regressão: Abrir logo depois de iniciar perguntava se queria salvar."""
    arquivo = criar_saui()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(arquivo), "")),
    )
    janela.abrir_arquivo()   # se perguntar algo, o guarda de diálogos falha o teste
    assert janela.current_path == str(arquivo)


def test_novo_sem_alterar_nao_pergunta_nada(janela):
    janela.novo_arquivo()
    assert not janela.text_edit.document().isModified()


def test_novo_depois_de_digitar_pergunta_e_descarta(janela, qtbot, monkeypatch):
    perguntas = _responder(monkeypatch, QMessageBox.Discard)
    qtbot.keyClicks(janela.text_edit, "abc")
    janela.novo_arquivo()
    assert len(perguntas) == 1
    assert janela.text_edit.toPlainText() == ""
    assert not janela.text_edit.document().isModified()


def test_cancelar_a_pergunta_mantem_o_documento(janela, qtbot, monkeypatch):
    _responder(monkeypatch, QMessageBox.Cancel)
    qtbot.keyClicks(janela.text_edit, "abc")
    janela.novo_arquivo()
    assert janela.text_edit.toPlainText() == "abc"


def test_fechar_com_alteracoes_pergunta(janela, qtbot, monkeypatch):
    perguntas = _responder(monkeypatch, QMessageBox.Cancel)
    qtbot.keyClicks(janela.text_edit, "abc")
    assert janela.close() is False      # o usuário cancelou: a janela fica
    assert len(perguntas) == 1
    assert janela.isVisible()


def test_fechar_sem_alteracoes_nao_pergunta(janela):
    assert janela.close() is True


def test_salvar_deixa_o_documento_limpo(janela, qtbot, tmp_path):
    qtbot.keyClicks(janela.text_edit, "abc")
    janela._salvar_em(str(tmp_path / "a.saui"))
    assert not janela.text_edit.document().isModified()


def test_arquivo_com_listas_numeradas_abre_sem_ficar_modificado(
        janela, criar_saui, qtbot):
    """A renumeração de listas altera o documento depois de aberto; isso não
    pode contar como modificação do usuário."""
    html = ("<ol><li>Alfa<ol><li>Sub um</li><li>Sub dois</li></ol></li>"
            "<li>Beta</li></ol>")
    janela.abrir_caminho(str(criar_saui(html=html)))
    qtbot.wait(150)   # tempo para a renumeração (agendada) rodar
    assert not janela.text_edit.document().isModified()
