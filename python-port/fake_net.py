import json
import random
import threading

class _BlockEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'to_json'):
            return obj.to_json()
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        return super().default(obj)

def _deep_copy(obj):
    return json.loads(json.dumps(obj, cls = _BlockEncoder))

class FakeNet:
    def __init__(self, chance_message_fails = 0, message_delay = 0):
        self.clients = {}
        self.chance_message_fails = chance_message_fails
        self.message_delay_max = message_delay

    # Registers clients to the network.
    # Clients and Miners are registered by public key.
    def register(self, *client_list):
        for client in client_list:
            self.clients[client.address] = client

    # Broadcasts to all clients within this.clients the message msg and payload o.
    def broadcast(self, msg, o):
        for address in list(self.clients.keys()):
            self.send_message(address, msg, o)

    # Sends message msg and payload o directly to Client name.

    # The message may be lost or delayed, with the probability
    # defined for this instance.
    def send_message(self, address, msg, o):
        if not isinstance(o, (dict, list)) and not hasattr(o, 'to_json') and not hasattr(o, 'to_dict'):
            raise ValueError(f"Expected an object, got {type(o)}")

        o2 = _deep_copy(o)

        client = self.clients.get(address)
        if client is None:
            return

        delay_s = (random.random() * self.message_delay_max) / 1000.0

        if random.random() > self.chance_message_fails:
            threading.Timer(delay_s, lambda: client.emit(msg, o2)).start()

    # Tests whether a client is registered with the network.
    def recognizes(self, client):
        return client.address in self.clients