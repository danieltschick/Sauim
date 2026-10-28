"""Infraestrutura comum dos testes do Sauim.

Rodar:  python -m pytest            (tudo)
        python -m pytest -k lista   (só os testes que têm "lista" no nome)
        python -m pytest -x         (para no primeiro que falhar)
"""
import json
import os

# Qt sem janela de verdade: precisa ser definido ANTES de importar o PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

import Sauim as sauim  # o Sauim.py fica na raiz do projeto


@pytest.fixture(autouse=True)
def sem_dialogos_inesperados(monkeypatch):
    """Por padrão, qualquer caixa de diálogo FALHA o teste.

    Um diálogo modal de verdade ficaria esperando um clique para sempre e
    travaria a execução. Um teste que espera um diálogo troca este guarda
    pelo seu próprio (veja os testes de estado "modificado").
    """
    def proibido(nome):
        def _funcao(*args, **kwargs):
            raise AssertionError(f"Diálogo inesperado: {nome}")
        return staticmethod(_funcao)

    for nome in ("question", "warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, nome, proibido(f"QMessageBox.{nome}"))
    for nome in ("getOpenFileName", "getSaveFileName"):
        monkeypatch.setattr(QFileDialog, nome, proibido(f"QFileDialog.{nome}"))


def _marcar_como_salvo(janela):
    """Evita o diálogo "salvar alterações?" quando o qtbot fecha a janela."""
    janela.text_edit.document().setModified(False)


@pytest.fixture
def janela(qtbot):
    """Uma janela do Sauim já aberta, como logo depois de iniciar o programa."""
    j = sauim.Editor()
    # O pytest-qt fecha as janelas no COMEÇO do teardown, antes do cleanup
    # desta fixture; por isso o "marcar como salvo" vai em before_close_func.
    qtbot.addWidget(j, before_close_func=_marcar_como_salvo)
    j.show()
    j.grab()            # força a primeira pintura (o editor se autocorrige nela)
    qtbot.wait(60)      # deixa rodar os QTimer.singleShot(0) do início
    return j


@pytest.fixture
def criar_saui(tmp_path):
    """Fábrica de arquivos .saui, escritos à mão (sem passar pelo editor)."""
    def _criar(nome="doc.saui", html="<p>conteudo</p>", largura=210.0,
               altura=297.0, margem=25.0):
        caminho = tmp_path / nome
        dados = {
            "formato": "sauim",
            "versao": sauim.VERSAO_FORMATO,
            "conteudo_html": html,
            "pagina": {"largura_mm": largura, "altura_mm": altura, "margem_mm": margem},
        }
        caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return caminho
    return _criar

