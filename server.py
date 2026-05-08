import socket
import threading
import pathlib

HOST = '0.0.0.0'
PORT = 9000
STORAGE = pathlib.Path('./storage')


class RWLock:
    """Permite múltiplos leitores simultâneos ou um único escritor por vez."""

    def __init__(self):
        self._cond = threading.Condition(threading.Lock())
        self._readers = 0

    def acquire_read(self):
        with self._cond:
            self._readers += 1

    def release_read(self):
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_write(self):
        # Adquire o lock interno e aguarda até não haver leitores ativos
        self._cond.acquire()
        while self._readers > 0:
            self._cond.wait()

    def release_write(self):
        self._cond.release()


class FileServer:

    def __init__(self, host=HOST, port=PORT, storage=STORAGE):
        self.host = host
        self.port = port
        self.storage = pathlib.Path(storage)
        self.storage.mkdir(exist_ok=True)
        self._locks = {}            # filename -> RWLock
        self._meta_lock = threading.Lock()  # protege o dict de locks

    def _get_lock(self, filename):
        with self._meta_lock:
            if filename not in self._locks:
                self._locks[filename] = RWLock()
            return self._locks[filename]

    def _safe_path(self, filename):
        """Rejeita nomes com separadores de diretório ou ponto inicial."""
        if not filename or '/' in filename or '\\' in filename or filename.startswith('.'):
            return None
        return self.storage / filename

    def _readline(self, conn):
        """Lê bytes do socket até encontrar newline."""
        buf = b''
        while True:
            ch = conn.recv(1)
            if not ch:
                raise ConnectionError('cliente desconectado')
            if ch == b'\n':
                return buf.decode('utf-8').strip()
            buf += ch

    def _recvall(self, conn, n):
        """Recebe exatamente n bytes do socket."""
        data = b''
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                raise ConnectionError('cliente desconectou durante transferência')
            data += chunk
        return data

    def _send(self, conn, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        conn.sendall(data)

    # ------------------------------------------------------------------ #
    # Handlers de comando                                                  #
    # ------------------------------------------------------------------ #

    def cmd_dir(self, conn):
        files = sorted(f.name for f in self.storage.iterdir() if f.is_file())
        body = ''.join(f'{name}\n' for name in files)
        self._send(conn, f'OK {len(files)}\n{body}')

    def cmd_put(self, filename, size, conn):
        path = self._safe_path(filename)
        if path is None:
            self._send(conn, 'ERR nome de arquivo inválido\n')
            return

        content = self._recvall(conn, size)

        lock = self._get_lock(filename)
        lock.acquire_write()
        try:
            path.write_bytes(content)
        finally:
            lock.release_write()

        self._send(conn, 'OK\n')
        print(f'  PUT {filename} ({size} bytes)')

    def cmd_get(self, filename, conn):
        path = self._safe_path(filename)
        if path is None:
            self._send(conn, 'ERR nome de arquivo inválido\n')
            return
        if not path.exists():
            self._send(conn, f'ERR arquivo não encontrado: {filename}\n')
            return

        lock = self._get_lock(filename)
        lock.acquire_read()
        try:
            content = path.read_bytes()
        finally:
            lock.release_read()

        self._send(conn, f'OK {len(content)}\n')
        self._send(conn, content)
        print(f'  GET {filename} ({len(content)} bytes)')

    def handle_client(self, conn, addr):
        print(f'[+] {addr} conectado')
        try:
            while True:
                line = self._readline(conn)
                if not line:
                    continue

                parts = line.split()
                cmd = parts[0].upper()

                if cmd == 'DIR':
                    self.cmd_dir(conn)

                elif cmd == 'PUT':
                    if len(parts) != 3:
                        self._send(conn, 'ERR uso: PUT <nome> <tamanho>\n')
                        continue
                    try:
                        size = int(parts[2])
                        if size < 0:
                            raise ValueError
                    except ValueError:
                        self._send(conn, 'ERR tamanho inválido\n')
                        continue
                    self.cmd_put(parts[1], size, conn)

                elif cmd == 'GET':
                    if len(parts) != 2:
                        self._send(conn, 'ERR uso: GET <nome>\n')
                        continue
                    self.cmd_get(parts[1], conn)

                else:
                    self._send(conn, f'ERR comando desconhecido: {cmd}\n')

        except ConnectionError:
            pass
        except Exception as e:
            print(f'Erro inesperado com {addr}: {e}')
        finally:
            conn.close()
            print(f'[-] {addr} desconectado')

    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, self.port))
            srv.listen()
            print(f'Servidor rodando em {self.host}:{self.port}')
            while True:
                conn, addr = srv.accept()
                t = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                t.start()


if __name__ == '__main__':
    FileServer().run()
