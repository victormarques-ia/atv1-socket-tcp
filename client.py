import socket
import os
import sys

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 9000


class Client:

    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))

    def _send(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.sock.sendall(data)

    def _readline(self):
        buf = b''
        while True:
            ch = self.sock.recv(1)
            if not ch:
                raise ConnectionError('servidor desconectado')
            if ch == b'\n':
                return buf.decode('utf-8').strip()
            buf += ch

    def _recvall(self, n):
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError('servidor desconectou durante transferência')
            data += chunk
        return data

    def do_dir(self):
        self._send('DIR\n')
        resp = self._readline()
        if not resp.startswith('OK'):
            print(f'Erro: {resp}')
            return
        count = int(resp.split()[1])
        if count == 0:
            print('Nenhum arquivo no servidor.')
        else:
            print(f'{count} arquivo(s) no servidor:')
            for _ in range(count):
                print(f'  {self._readline()}')

    def do_put(self, local_path):
        if not os.path.isfile(local_path):
            print(f'Arquivo não encontrado localmente: {local_path}')
            return
        filename = os.path.basename(local_path)
        with open(local_path, 'rb') as f:
            content = f.read()
        self._send(f'PUT {filename} {len(content)}\n')
        self._send(content)
        resp = self._readline()
        if resp == 'OK':
            print(f'Upload concluído: {filename} ({len(content)} bytes)')
        else:
            print(f'Erro: {resp}')

    def do_get(self, filename, dest=None):
        self._send(f'GET {filename}\n')
        resp = self._readline()
        if not resp.startswith('OK'):
            print(f'Erro: {resp}')
            return
        size = int(resp.split()[1])
        content = self._recvall(size)
        dest = dest or filename
        with open(dest, 'wb') as f:
            f.write(content)
        print(f'Download concluído: {filename} → {dest} ({size} bytes)')

    def run(self):
        print('Gestor de Documentos Normativos — Cliente')
        print('Comandos: dir | put <arquivo> | get <nome> [destino] | quit')
        try:
            while True:
                try:
                    line = input('\n> ').strip()
                except EOFError:
                    break
                if not line:
                    continue
                parts = line.split()
                cmd = parts[0].lower()

                if cmd == 'quit':
                    break
                elif cmd == 'dir':
                    self.do_dir()
                elif cmd == 'put':
                    if len(parts) < 2:
                        print('Uso: put <arquivo_local>')
                    else:
                        self.do_put(parts[1])
                elif cmd == 'get':
                    if len(parts) < 2:
                        print('Uso: get <nome> [destino]')
                    else:
                        dest = parts[2] if len(parts) >= 3 else None
                        self.do_get(parts[1], dest)
                else:
                    print(f'Comando não reconhecido: {cmd}')
        finally:
            self.sock.close()


if __name__ == '__main__':
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    try:
        Client(host, port).run()
    except ConnectionRefusedError:
        print(f'Não foi possível conectar em {host}:{port}. O servidor está rodando?')
