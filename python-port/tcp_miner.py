import json
import os
import socket
import sys
import threading

import blockchain as bc_module
from block import Block
from transaction import Transaction
from miner import Miner
from fake_net import FakeNet


# replaces FakeNet for real network communication
class TcpNet(FakeNet):
    """
    Extends FakeNet so that send_message() opens a real TCP connection
    instead of calling the target client's emit() in memory.
    """

    def send_message(self, address, msg, o):
        """
        Serializes {msg, o} to JSON and sends it over TCP to the client
        registered at `address`.

        The connection dict stored on each registered client must have
        'host' and 'port' fields, e.g. {"host": "localhost", "port": 9000}.
        """
        client_info = self.clients.get(address)
        if client_info is None:
            return

        # Serialize the payload — blocks have to_json(), transactions have
        # to_dict(), plain dicts pass through unchanged.
        if hasattr(o, 'to_json'):
            payload = o.to_json()
        elif hasattr(o, 'to_dict'):
            payload = o.to_dict()
        else:
            payload = o

        data = json.dumps({'msg': msg, 'o': payload})

        # mirroring JS's non-blocking net.connect callback pattern.
        def _send():
            try:
                conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                conn.settimeout(5)
                host = client_info.get('connection', {}).get('host', 'localhost')
                port = client_info.get('connection', {}).get('port')
                conn.connect((host, int(port)))
                conn.sendall(data.encode('utf-8'))
                conn.close()
            except Exception as e:
                pass  # Drop the message on failed delivery, like FakeNet's chance_message_fails

        threading.Thread(target=_send, daemon=True).start()

#  extends Miner with real TCP server + peer registration
class TcpMiner(Miner):
    # Message type constant for peer registration handshake.
    REGISTER = "REGISTER"

    def __init__(self, obj=None):
        if obj is None:
            obj = {}

        # Use TcpNet instead of FakeNet so send_message goes over the wire.
        obj['net'] = TcpNet()
        super().__init__(obj)

        self.connection = obj.get('connection', {'host': 'localhost', 'port': 9000})

        # False while the CLI menu is open; find_proof() returns immediately
        # when this is False and does not reschedule itself.
        self._mining_active = True

        # Set up the TCP server socket.
        # JS: this.srvr = net.createServer();
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # Accept incoming connections in a background daemon thread so the
        # server loop doesn't block the mining loop.
        # JS: this.srvr.on('connection', (client) => { ... });
        self._server_thread = threading.Thread(target=self._accept_loop, daemon=True)

    def pause_mining(self):
        self._mining_active = False

    def resume_mining(self):
        self._mining_active = True
        threading.Timer(0, lambda: self.emit(bc_module.Blockchain.START_MINING)).start()

    def find_proof(self, one_and_done=False):
        # When the CLI menu is open, drop the call and do not reschedule.
        # The current in-flight round (if any) finishes its iterations and
        # then stops naturally because this guard blocks the next emission.
        if not self._mining_active:
            return
        super().find_proof(one_and_done)

    def _accept_loop(self):
        while True:
            try:
                conn, _ = self._server.accept()
                threading.Thread(target=self._handle_connection, args=(conn,), daemon=True).start()
            except Exception:
                break  # Server was closed

    def _handle_connection(self, conn):
        try:
            chunks = []
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
                # if it succeeds we have the full message.
                try:
                    data = json.loads(b''.join(chunks).decode('utf-8'))
                    break
                except json.JSONDecodeError:
                    continue  # Keep reading

            msg = data.get('msg')
            o   = data.get('o')

            if msg == TcpMiner.REGISTER:
                # Peer announcement add them to our network map.
                # If we don't already know them, register back with themso they also have us in their routing table.
                # JS: if (!this.net.recognizes(o)) this.registerWith(o.connection)
                if o.get('address') not in self.net.clients:
                    self.register_with(o.get('connection'))
                self.log(f"Registering peer {o.get('name')} at {o.get('connection')}")
                # Store enough info in TcpNet's client map to route future messages.
                self.net.clients[o['address']] = o
            else:
                # Any other message (PROOF_FOUND, POST_TRANSACTION, MISSING_BLOCK)
                # is fed into the existing Miner event system unchanged
                self.emit(msg, o)

        except Exception as e:
            self.log(f"Connection error: {e}")
        finally:
            conn.close()

    def register_with(self, connection):
        if connection is None:
            return

        data = json.dumps({
            'msg': TcpMiner.REGISTER,
            'o': {
                'name':       self.name,
                'address':    self.address,
                'connection': self.connection,
            }
        })

        def _send():
            try:
                conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                conn.settimeout(5)
                host = connection.get('host', 'localhost')
                port = int(connection.get('port'))
                conn.connect((host, port))
                conn.sendall(data.encode('utf-8'))
                conn.close()
                self.log(f"Registered with miner at {host}:{port}")
            except Exception as e:
                self.log(f"Could not connect to {connection}: {e}")

        threading.Thread(target=_send, daemon=True).start()

    def initialize(self, known_miner_connections=None):

        if known_miner_connections is None:
            known_miner_connections = []

        self.known_miners = known_miner_connections

        # Start the TCP server before calling super().initialize() so we
        # are ready to receive blocks the moment we announce ourselves.
        host = self.connection.get('host', 'localhost')
        port = int(self.connection.get('port'))
        self._server.bind((host, port))
        self._server.listen(10)
        self._server_thread.start()
        self.log(f"Listening on {host}:{port}")

        # Start mining via the base Miner class.
        super().initialize()

        # Register with all known peers.
        for conn in known_miner_connections:
            self.register_with(conn)

    def show_pending_out(self):
        lines = []
        for tx in self.pending_outgoing_transactions.values():
            lines.append(f"    id:{tx.id} nonce:{tx.nonce} totalOutput:{tx.total_output()}")
        return '\n'.join(lines) if lines else '    (none)'

    def save_json(self, file_name):
        state = {
            'name':        self.name,
            'connection':  self.connection,
            'keyPair':     self.key_pair,
            'knownMiners': getattr(self, 'known_miners', []),
        }
        with open(file_name, 'w') as f:
            json.dump(state, f, indent=2)
        self.log(f"State saved to {file_name}")

    @classmethod
    def load_json(cls, file_name):
        with open(file_name, 'r') as f:
            return json.load(f)


# Interactive CLI
#
# JS equivalent: the readUserInput() function using readline.createInterface.
# PY: plain input() loop — simpler but functionally identical.

def run_cli(miner):
    while True:
        print(f"""
            Funds: {miner.available_gold}
            Address: {miner.address}
            Pending transactions: {miner.show_pending_out()}
            What would you like to do?
            *(c)onnect to miner?
            *(t)ransfer funds?
            *(r)esend pending transactions?
            *show (b)alances?
            *show blocks for (d)ebugging and exit?
            *(s)ave your state?
            *e(x)it without saving?
            """)
        try:
            sys.stdout.flush()
            answer = input("  Your choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down.")
            os._exit(0)

        if answer == 'x':
            print("Shutting down. Have a nice day.")
            os._exit(0)

        elif answer == 'b':
            miner.show_all_balances()

        elif answer == 'c':
            port = input("  port: ").strip()
            miner.register_with({'host': 'localhost', 'port': int(port)})
            print(f"Registering with miner at port {port}")

        elif answer == 't':
            amt_str = input("  amount: ").strip()
            try:
                amt = int(amt_str)
            except ValueError:
                print("  Invalid amount.")
                continue
            if amt > miner.available_gold:
                print(f"  ***Insufficient gold. You only have {miner.available_gold}.")
            else:
                addr = input("  address: ").strip()
                print(f"  Transferring {amt} gold to {addr}.")
                miner.post_transaction([{'amount': amt, 'address': addr}])

        elif answer == 'r':
            miner.resend_pending_transactions()
            print("  Pending transactions resent.")

        elif answer == 's':
            fname = input("  file name: ").strip()
            miner.save_json(fname)

        elif answer == 'd':
            for block_id, block in miner.blocks.items():
                tx_ids = ' '.join(block.transactions.keys())
                if tx_ids:
                    print(f"{block.id} transactions: {tx_ids}")
            print()
            miner.show_blockchain()
            os._exit(0)

        else:
            print(f"  Unrecognized choice: {answer}")

# Entry point
# Usage: python tcp_miner.py
if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <config.json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        config = json.load(f)

    # Build the genesis block from starting balances in the config.
    starting_balances = config.get('genesis', {}).get('startingBalances', {})
    bc = bc_module.Blockchain.create_instance({
        'blockClass':       Block,
        'transactionClass': Transaction,
        'startingBalances': starting_balances,
        'net': TcpNet(),
    })

    os.system('cls' if os.name == 'nt' else 'clear')

    name = config.get('name', 'Miner')
    print(f"Starting {name}")

    key_pair   = config.get('keyPair')
    connection = config.get('connection', {'host': 'localhost', 'port': 9000})

    miner = TcpMiner({
        'name':          name,
        'keyPair':       key_pair,
        'connection':    connection,
        'startingBlock': bc.genesis,
    })

    # Route mining output to stderr so it never interferes with input() on stdout.
    # On Windows, background threads writing to stdout corrupt the terminal line
    # buffer and cause Enter keystrokes to be swallowed by input().
    _miner_name = miner.name or name
    miner.log = lambda msg: print(f"{_miner_name}: {msg}", file=sys.stderr, flush=True) \
        if 'Registering' in msg else None

    known_miners = config.get('knownMiners', [])
    miner.initialize(known_miners)

    run_cli(miner)