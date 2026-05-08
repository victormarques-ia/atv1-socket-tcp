"""
CIN0143 — Sistemas Distribuídos | Equipe 08 — Gestor de Documentos Normativos
Integrantes: Gabriel Albertin Vieira, Ithalo Rannieri Araujo Soares,
             Talisson Mendes, Tiago Ferreira, Victor Silva Marques de Oliveira

Testes do Gestor de Documentos Normativos.

Cobre os requisitos do enunciado:
  - Comandos GET, PUT e DIR via Socket TCP
  - Múltiplas conexões simultâneas
  - Concorrência de leitura (vários GET no mesmo arquivo ao mesmo tempo)
  - Tratamento de erros (arquivo inexistente, nome inválido, comando desconhecido)

Execução:
    python3 test_server.py
"""

import unittest
import threading
import socket
import pathlib
import tempfile
import shutil
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from server import FileServer

TEST_HOST = 'localhost'
TEST_PORT = 19000  # porta separada para não conflitar com o servidor real


# ------------------------------------------------------------------ #
# Helpers de socket (espelham a lógica do client.py)                  #
# ------------------------------------------------------------------ #

def tcp_send(sock, data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    sock.sendall(data)


def tcp_readline(sock):
    buf = b''
    while True:
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError('servidor fechou a conexão')
        if ch == b'\n':
            return buf.decode('utf-8').strip()
        buf += ch


def tcp_recvall(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError('conexão encerrada antes de receber tudo')
        data += chunk
    return data


def connect():
    s = socket.create_connection((TEST_HOST, TEST_PORT))
    return s


def do_put(sock, filename, content):
    if isinstance(content, str):
        content = content.encode('utf-8')
    tcp_send(sock, f'PUT {filename} {len(content)}\n')
    tcp_send(sock, content)
    return tcp_readline(sock)


def do_get(sock, filename):
    tcp_send(sock, f'GET {filename}\n')
    resp = tcp_readline(sock)
    if not resp.startswith('OK'):
        return resp, None
    size = int(resp.split()[1])
    content = tcp_recvall(sock, size)
    return resp, content


def do_dir(sock):
    tcp_send(sock, 'DIR\n')
    resp = tcp_readline(sock)
    count = int(resp.split()[1])
    files = [tcp_readline(sock) for _ in range(count)]
    return files

class TestGestorDocumentos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = pathlib.Path(tempfile.mkdtemp())
        cls.server = FileServer(host='0.0.0.0', port=TEST_PORT, storage=cls.tmpdir)
        t = threading.Thread(target=cls.server.run, daemon=True)
        t.start()
        time.sleep(0.2)  # aguarda o servidor ficar pronto

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # ---------------------------------------------------------------- #

    def test_01_dir_vazio(self):
        """DIR em servidor sem arquivos retorna lista vazia."""
        with connect() as s:
            files = do_dir(s)
        self.assertEqual(files, [])

    def test_02_put_novo_arquivo(self):
        """PUT de um arquivo novo retorna OK."""
        with connect() as s:
            resp = do_put(s, 'norma01.txt', 'Conteúdo da Norma 01.')
        self.assertEqual(resp, 'OK')

    def test_03_dir_lista_arquivo_enviado(self):
        """DIR após PUT mostra o arquivo recém-enviado."""
        with connect() as s:
            do_put(s, 'norma02.txt', 'Norma 02.')
            files = do_dir(s)
        self.assertIn('norma02.txt', files)

    def test_04_get_recupera_conteudo_correto(self):
        """GET devolve exatamente o conteúdo enviado pelo PUT."""
        conteudo = 'Regulamento Interno v1.0 — texto de referência.'
        with connect() as s:
            do_put(s, 'regulamento.txt', conteudo)
        with connect() as s:
            _, recebido = do_get(s, 'regulamento.txt')
        self.assertEqual(recebido.decode('utf-8'), conteudo)

    def test_05_get_arquivo_inexistente(self):
        """GET de arquivo que não existe retorna ERR."""
        with connect() as s:
            resp, _ = do_get(s, 'nao_existe.txt')
        self.assertTrue(resp.startswith('ERR'))

    def test_06_put_sobrescreve_arquivo(self):
        """Segundo PUT no mesmo arquivo substitui o conteúdo."""
        with connect() as s:
            do_put(s, 'manual.txt', 'versão 1')
            do_put(s, 'manual.txt', 'versão 2')
        with connect() as s:
            _, recebido = do_get(s, 'manual.txt')
        self.assertEqual(recebido.decode('utf-8'), 'versão 2')

    def test_07_put_nome_invalido_com_barra(self):
        """PUT com nome contendo '/' é rejeitado com ERR."""
        with connect() as s:
            tcp_send(s, 'PUT ../malicioso.txt 3\n')
            tcp_send(s, b'abc')
            resp = tcp_readline(s)
        self.assertTrue(resp.startswith('ERR'))

    def test_08_comando_desconhecido(self):
        """Comando não reconhecido retorna ERR."""
        with connect() as s:
            tcp_send(s, 'DELETAR tudo.txt\n')
            resp = tcp_readline(s)
        self.assertTrue(resp.startswith('ERR'))

    def test_09_multiplas_conexoes_simultaneas(self):
        """Servidor aceita várias conexões ao mesmo tempo sem travar."""
        resultados = []
        erros = []

        def cliente(i):
            try:
                with connect() as s:
                    resp = do_put(s, f'doc_{i:02d}.txt', f'documento {i}')
                    resultados.append(resp)
            except Exception as e:
                erros.append(str(e))

        threads = [threading.Thread(target=cliente, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(erros, [], msg=f'Erros nos clientes: {erros}')
        self.assertEqual(resultados.count('OK'), 10)

    def test_10_leituras_concorrentes_mesmo_arquivo(self):
        """Vários clientes fazem GET do mesmo arquivo simultaneamente sem corrupção."""
        conteudo = ('A' * 512 + 'B' * 512) * 4  # 4 KB de conteúdo reconhecível
        with connect() as s:
            do_put(s, 'manual_grande.txt', conteudo)

        resultados = []
        erros = []

        def leitor():
            try:
                with connect() as s:
                    _, recebido = do_get(s, 'manual_grande.txt')
                    resultados.append(recebido.decode('utf-8'))
            except Exception as e:
                erros.append(str(e))

        threads = [threading.Thread(target=leitor) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(erros, [], msg=f'Erros nas leituras: {erros}')
        for r in resultados:
            self.assertEqual(r, conteudo, msg='Conteúdo corrompido em leitura concorrente')

    def test_11_put_e_get_em_sequencia_na_mesma_conexao(self):
        """Conexão persistente: múltiplos comandos em série funcionam."""
        with connect() as s:
            do_put(s, 'seq.txt', 'linha 1\nlinha 2\n')
            files = do_dir(s)
            _, recebido = do_get(s, 'seq.txt')
        self.assertIn('seq.txt', files)
        self.assertEqual(recebido.decode('utf-8'), 'linha 1\nlinha 2\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
