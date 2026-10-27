"""Abrir, salvar, extensão do Salvar como e arquivo recebido por argumento."""
import json
import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox

import editor
from ajudas import formato_do_caractere, pagina_valida

F = editor.FILTROS_ARQUIVO     # [ .saui , .html , .txt ]


def _dialogo_de_salvar(monkeypatch, caminho, filtro, chamadas=None):
    def _get(*args, **kwargs):
        if chamadas is not None:
            chamadas.append(1)
        return (str(caminho), filtro)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_get))


# ---------- extensão escolhida no Salvar como ----------
# Regressão: a extensão era descoberta procurando pedaços de texto no nome do
# filtro ("saui" aparece dentro de "Sauim"!). Agora vem de uma tabela.

@pytest.mark.parametrize("nome, filtro, esperado", [
    ("doc",            F[0], "doc.saui"),
    ("doc",            F[1], "doc.html"),
    ("doc",            F[2], "doc.txt"),
    ("doc.txt",        F[0], "doc.txt"),            # vale a extensão digitada
    ("DOC.SAUI",       F[1], "DOC.SAUI"),           # maiúsculas
    ("doc.docx",       F[1], "doc.docx.html"),      # extensão desconhecida
    ("doc",            "",   "doc.saui"),           # diálogo sem filtro: formato nativo
    ("doc",            "Texto qualquer (*.xyz)", "doc.saui"),
    ("relatório v1.2", F[0], "relatório v1.2.saui"),
])
def test_salvar_como_define_a_extensao(janela, tmp_path, monkeypatch,
                                       nome, filtro, esperado):
    _dialogo_de_salvar(monkeypatch, tmp_path / nome, filtro)
    janela.salvar_como()
    assert (tmp_path / esperado).exists()


def test_cancelar_o_salvar_como_nao_salva_nada(janela, tmp_path, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    janela.salvar_como()
    assert list(tmp_path.iterdir()) == []
    assert janela.current_path is None


def test_salvar_depois_de_salvar_como_nao_pergunta_de_novo(janela, tmp_path, monkeypatch):
    chamadas = []
    _dialogo_de_salvar(monkeypatch, tmp_path / "a", F[0], chamadas)
    janela.salvar_como()
    janela.salvar_arquivo()
    assert len(chamadas) == 1


# ---------- conteúdo gravado em cada formato ----------

def test_saui_e_json_com_html_e_pagina(janela, tmp_path):
    janela.text_edit.setPlainText("Olá")
    caminho = tmp_path / "a.saui"
    janela._salvar_em(str(caminho))
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["formato"] == "sauim"
    assert dados["versao"] == editor.VERSAO_FORMATO
    assert "Olá" in dados["conteudo_html"]
    assert set(dados["pagina"]) == {"largura_mm", "altura_mm", "margem_mm"}


def test_txt_grava_texto_puro(janela, tmp_path):
    janela.text_edit.setPlainText("linha um\nlinha dois")
    caminho = tmp_path / "a.txt"
    janela._salvar_em(str(caminho))
    assert caminho.read_text(encoding="utf-8") == "linha um\nlinha dois"


def test_html_grava_html(janela, tmp_path):
    janela.text_edit.setPlainText("Olá")
    caminho = tmp_path / "a.html"
    janela._salvar_em(str(caminho))
    assert "<html" in caminho.read_text(encoding="utf-8").lower()


def test_formatacao_sobrevive_a_salvar_e_abrir(janela, tmp_path):
    ed = janela.text_edit
    ed.setHtml('<p align="center"><b>Titulo</b></p><p>texto normal</p>')
    caminho = str(tmp_path / "f.saui")
    janela._salvar_em(caminho)

    janela.novo_arquivo()
    janela.abrir_caminho(caminho)

    assert ed.toPlainText() == "Titulo\ntexto normal"
    assert formato_do_caractere(ed, 0).font().bold()
    assert ed.document().firstBlock().blockFormat().alignment() & Qt.AlignHCenter


# ---------- abrir_caminho ----------

def test_abrir_caminho_carrega_conteudo_e_pagina(janela, criar_saui, qtbot):
    arquivo = criar_saui(html="<p>Olá mundo</p>", largura=215.9, altura=279.4, margem=20.0)
    janela.abrir_caminho(str(arquivo))
    qtbot.waitUntil(lambda: pagina_valida(janela.text_edit), timeout=2000)

    ed = janela.text_edit
    assert ed.toPlainText() == "Olá mundo"
    assert (ed.largura_mm, ed.altura_mm, ed.margem_mm) == (215.9, 279.4, 20.0)
    assert janela.current_path == str(arquivo)
    assert str(arquivo) in janela.windowTitle()
    assert not ed.document().isModified()


def test_abrir_html_e_txt(janela, tmp_path):
    (tmp_path / "a.html").write_text("<p><b>oi</b> html</p>", encoding="utf-8")
    (tmp_path / "b.txt").write_text("só texto", encoding="utf-8")
    janela.abrir_caminho(str(tmp_path / "a.html"))
    assert janela.text_edit.toPlainText() == "oi html"
    janela.abrir_caminho(str(tmp_path / "b.txt"))
    assert janela.text_edit.toPlainText() == "só texto"


def test_arquivo_inexistente_mostra_erro_e_nao_muda_nada(janela, tmp_path, monkeypatch):
    erros = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: erros.append(a)))
    janela.abrir_caminho(str(tmp_path / "nao_existe.saui"))
    assert len(erros) == 1
    assert janela.current_path is None


def test_json_invalido_mostra_erro(janela, tmp_path, monkeypatch):
    erros = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *a, **k: erros.append(a)))
    ruim = tmp_path / "ruim.saui"
    ruim.write_text("isto não é json", encoding="utf-8")
    janela.abrir_caminho(str(ruim))
    assert len(erros) == 1


# ---------- duplo clique no arquivo (argumento da linha de comando) ----------
# Regressão: o programa abria vazio, porque ignorava o argumento.

def test_argumentos_sem_arquivo():
    assert editor.arquivo_dos_argumentos(["sauim.exe"]) is None


def test_argumentos_ignoram_opcoes_e_pegam_o_primeiro_arquivo(tmp_path):
    a = tmp_path / "com espaço.saui"
    b = tmp_path / "outro.saui"
    a.write_text("x")
    b.write_text("x")
    argumentos = ["sauim.exe", "-platform", "windows", str(a), str(b)]
    assert editor.arquivo_dos_argumentos(argumentos) == str(a)


def test_argumentos_pulam_arquivo_inexistente(tmp_path):
    existente = tmp_path / "ok.saui"
    existente.write_text("x")
    argumentos = ["sauim.exe", str(tmp_path / "fantasma.saui"), str(existente)]
    assert editor.arquivo_dos_argumentos(argumentos) == str(existente)


def test_argumento_relativo_vira_caminho_absoluto(tmp_path, monkeypatch):
    (tmp_path / "rel.saui").write_text("x")
    monkeypatch.chdir(tmp_path)
    resultado = editor.arquivo_dos_argumentos(["sauim.exe", "rel.saui"])
    assert os.path.isabs(resultado)
    assert os.path.samefile(resultado, tmp_path / "rel.saui")
