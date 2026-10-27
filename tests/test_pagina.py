"""Tamanho de página, paginação e o diálogo "Configurar página"."""
import pytest
from PySide6.QtWidgets import QDialog, QMessageBox

import editor
from ajudas import pagina_valida


# ---------- o documento precisa manter uma altura de página válida ----------
# Regressão: o QTextEdit apagava a altura de página; a tela mostrava as quebras
# no lugar errado e a impressão saía com número de página automático.

def test_tamanho_de_pagina_valido_ao_iniciar(janela, qtbot):
    qtbot.waitUntil(lambda: pagina_valida(janela.text_edit), timeout=2000)


def test_tamanho_de_pagina_sobrevive_a_carregar_texto(janela, qtbot):
    janela.text_edit.setHtml("<p>x</p>")
    janela.grab()
    qtbot.waitUntil(lambda: pagina_valida(janela.text_edit), timeout=2000)


def test_tamanho_de_pagina_sobrevive_a_digitacao(janela, qtbot):
    qtbot.keyClicks(janela.text_edit, "texto " * 50)
    janela.grab()
    qtbot.waitUntil(lambda: pagina_valida(janela.text_edit), timeout=2000)


def test_texto_longo_gera_varias_paginas(janela, qtbot):
    ed = janela.text_edit
    ed.setPlainText("linha\n" * 300)
    janela.grab()
    qtbot.waitUntil(lambda: pagina_valida(ed), timeout=2000)
    assert ed.document().pageCount() >= 2


# ---------- configurar_pagina ----------

def test_configurar_pagina_atualiza_tudo(janela):
    ed = janela.text_edit
    ed.configurar_pagina(215.9, 279.4, 20)
    assert (ed.largura_mm, ed.altura_mm, ed.margem_mm) == (215.9, 279.4, 20.0)
    assert ed.largura_px == pytest.approx(215.9 * editor.MM_TO_PX)
    assert ed.altura_px == pytest.approx(279.4 * editor.MM_TO_PX)
    assert ed.document().documentMargin() == pytest.approx(20 * editor.MM_TO_PX)
    assert pagina_valida(ed)


def test_tamanho_de_pagina_vai_e_volta_no_arquivo(janela, tmp_path):
    ed = janela.text_edit
    ed.configurar_pagina(215.9, 279.4, 20)
    caminho = str(tmp_path / "p.saui")
    janela._salvar_em(caminho)

    ed.configurar_pagina(210, 297, 25)           # muda de volta
    janela.abrir_caminho(caminho)                # o arquivo deve restaurar
    assert (ed.largura_mm, ed.altura_mm, ed.margem_mm) == (215.9, 279.4, 20.0)


def test_mudar_a_pagina_pelo_dialogo_marca_modificado(janela, monkeypatch):
    """O tamanho da página é gravado no arquivo, então mudá-lo é uma alteração."""
    monkeypatch.setattr(editor.ConfigurarPaginaDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(editor.ConfigurarPaginaDialog, "valores",
                        lambda self: (215.9, 279.4, 20.0))
    janela.configurar_pagina_dialogo()
    assert janela.text_edit.largura_mm == 215.9
    assert janela.text_edit.document().isModified()


# ---------- diálogo "Configurar página" ----------

def _dialogo(qtbot, largura=210.0, altura=297.0, margem=25.0):
    d = editor.ConfigurarPaginaDialog(largura, altura, margem)
    qtbot.addWidget(d)
    return d


def test_dialogo_preseleciona_o_papel_atual(qtbot):
    d = _dialogo(qtbot)
    assert d.combo_papel.currentText() == list(editor.PAPEIS_PREDEFINIDOS)[0]   # A4
    assert d.combo_orientacao.currentText() == "Retrato"
    assert d.valores() == (pytest.approx(210.0), pytest.approx(297.0), pytest.approx(25.0))


def test_dialogo_reconhece_papel_em_paisagem(qtbot):
    d = _dialogo(qtbot, largura=297.0, altura=210.0)
    assert d.combo_papel.currentText() == list(editor.PAPEIS_PREDEFINIDOS)[0]
    assert d.combo_orientacao.currentText() == "Paisagem"


def test_dialogo_troca_de_papel_e_orientacao(qtbot):
    d = _dialogo(qtbot)
    d.combo_papel.setCurrentText(list(editor.PAPEIS_PREDEFINIDOS)[1])   # Carta
    assert d.valores()[:2] == (pytest.approx(215.9), pytest.approx(279.4))
    d.combo_orientacao.setCurrentText("Paisagem")
    assert d.valores()[:2] == (pytest.approx(279.4), pytest.approx(215.9))


def test_dialogo_personalizado_libera_largura_e_altura(qtbot):
    d = _dialogo(qtbot)
    assert not d.spin_largura.isEnabled()
    d.combo_papel.setCurrentText(d.PERSONALIZADO)
    assert d.spin_largura.isEnabled() and d.spin_altura.isEnabled()
    d.spin_largura.setValue(150.0)
    d.spin_altura.setValue(200.0)
    assert d.valores()[:2] == (pytest.approx(150.0), pytest.approx(200.0))


def test_dialogo_recusa_margem_grande_demais(qtbot, monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: avisos.append(a)))
    d = _dialogo(qtbot)
    d.combo_papel.setCurrentText(d.PERSONALIZADO)
    d.spin_largura.setValue(100.0)
    d.spin_altura.setValue(100.0)
    d.spin_margem.setValue(60.0)          # 2 x 60 >= 100: não sobra espaço
    d._validar_e_aceitar()
    assert len(avisos) == 1
    assert d.result() != QDialog.Accepted


def test_dialogo_aceita_margem_razoavel(qtbot):
    d = _dialogo(qtbot)
    d._validar_e_aceitar()
    assert d.result() == QDialog.Accepted
