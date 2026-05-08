# Equipe 08 — Gestor de Documentos Normativos

**CIN0143 — Introdução aos Sistemas Distribuídos e Redes de Computadores**
Universidade Federal de Pernambuco — Centro de Informática

**Integrantes:**
- Gabriel Albertin Vieira
- Ithalo Rannieri Araujo Soares
- Talisson Mendes
- Tiago Ferreira
- Victor Silva Marques de Oliveira

---

Sistema cliente-servidor via **Socket TCP** para upload, download e listagem de arquivos de texto.

## Pré-requisitos

- Python 3.8 ou superior
- Sem dependências externas (apenas biblioteca padrão)

## Como rodar

### 1. Iniciar o servidor

```bash
python server.py
```

O servidor escuta na porta **9000** e cria a pasta `storage/` automaticamente. Ele aceita múltiplas conexões simultâneas.

### 2. Iniciar o cliente (em outro terminal)

```bash
python client.py                    # conecta em localhost:9000
python client.py <host>             # host remoto, porta padrão 9000
python client.py <host> <porta>     # host e porta customizados
```

## Comandos disponíveis no cliente

| Comando | Descrição |
|---|---|
| `dir` | Lista todos os arquivos armazenados no servidor |
| `put <arquivo>` | Envia um arquivo local para o servidor |
| `get <nome> [destino]` | Baixa um arquivo do servidor |
| `quit` | Encerra o cliente |

### Exemplo de sessão

```
> dir
Nenhum arquivo no servidor.

> put regulamento.txt
Upload concluído: regulamento.txt (1024 bytes)

> dir
1 arquivo(s) no servidor:
  regulamento.txt

> get regulamento.txt copia.txt
Download concluído: regulamento.txt → copia.txt (1024 bytes)

> quit
```

## Protocolo

Comunicação via texto sobre TCP, delimitada por `\n`:

| Ação | Cliente envia | Servidor responde |
|---|---|---|
| Listar | `DIR\n` | `OK <n>\n<nome1>\n...<nomeN>\n` |
| Upload | `PUT <nome> <bytes>\n<conteúdo>` | `OK\n` |
| Download | `GET <nome>\n` | `OK <bytes>\n<conteúdo>` |
| Erro | — | `ERR <mensagem>\n` |

## Concorrência

Cada cliente é atendido em uma thread separada. Para controle de acesso aos arquivos, o servidor usa um **RWLock** (readers-writer lock) por arquivo:

- **Leitura (GET):** vários clientes podem baixar o mesmo arquivo ao mesmo tempo.
- **Escrita (PUT):** exclusiva — aguarda leitores ativos terminarem antes de gravar.
