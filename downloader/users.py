import threading
import time


class UserDirectory:
    def __init__(self, factory):
        self.factory = factory
        self.lock = threading.Lock()
        self.users = []
        self.expires = 0

    def all(self):
        with self.lock:
            if time.monotonic() >= self.expires:
                client = self.factory()
                try:
                    users = client.users()
                finally:
                    client.session.close()
                self.users = [dict(u, label=f"{u['name']} — {u['email']} ({u['id']})") for u in users]
                self.expires = time.monotonic() + 300
            return list(self.users)

    def resolve(self, label):
        if not label.strip():
            return ''
        match = next((u for u in self.all() if u['label'] == label), None)
        if not match:
            raise ValueError('Choose a sender from the populated list, or clear the sender field.')
        return match['id']
