"""Zoom da vista: não pode alterar o documento nem o tamanho da página."""
import pytest

import Sauim as sauim
from ajudas import pagina_valida


def test_zoom_comeca_em_100(janela):
    assert janela.visao.zoom() == 1.0


def test_ampliar_e_reduzir_seguem_os_passos(janela):
    janela.ampliar_zoom()
    assert janela.visao.zoom() == pytest.approx(1.1)
    janela.reduzir_zoom()
    janela.reduzir_zoom()
    assert janela.visao.zoom() == pytest.approx(0.9)


def test_zoom_respeita_os_limites(janela):
    janela.visao.definir_zoom(999)
    assert janela.visao.zoom() == pytest.approx(sauim.ZOOM_MAX)
    janela.visao.definir_zoom(0.001)
    assert janela.visao.zoom() == pytest.approx(sauim.ZOOM_MIN)


def test_ampliar_no_maximo_nao_passa_do_limite(janela):
    janela.visao.definir_zoom(sauim.ZOOM_MAX)
    janela.ampliar_zoom()
    assert janela.visao.zoom() == pytest.approx(sauim.ZOOM_MAX)


def test_slider_e_rotulo_acompanham_o_zoom(janela):
    janela.visao.definir_zoom(1.5)
    assert janela.slider_zoom.value() == 150
    assert janela.botao_zoom_percentual.text() == "150%"


def test_slider_controla_o_zoom(janela):
    janela.slider_zoom.setValue(50)
    assert janela.visao.zoom() == pytest.approx(0.5)


def test_zoom_nao_modifica_o_documento(janela):
    janela.visao.definir_zoom(2.0)
    janela.ampliar_zoom()
    assert not janela.text_edit.document().isModified()


def test_zoom_nao_altera_o_tamanho_de_pagina(janela, qtbot):
    ed = janela.text_edit
    antes = ed.document().pageSize()
    janela.visao.definir_zoom(2.5)
    janela.grab()
    qtbot.wait(60)
    assert ed.document().pageSize() == antes
    assert pagina_valida(ed)


def test_ajustar_a_largura_faz_a_folha_caber_na_janela(janela):
    janela.visao.ajustar_a_largura()
    zoom = janela.visao.zoom()
    assert sauim.ZOOM_MIN <= zoom <= sauim.ZOOM_MAX
    assert janela.text_edit.width() * zoom <= janela.visao.viewport().width() + 1
