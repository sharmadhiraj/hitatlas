import http.server
import logging
import queue
import threading

logger = logging.getLogger(__name__)

subscribers: list["queue.Queue[str]"] = []
subscribers_lock = threading.Lock()


def broadcast(payload: str) -> None:
    with subscribers_lock:
        for subscriber in subscribers:
            subscriber.put(payload)


class SSEHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/events":
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        client_queue: "queue.Queue[str]" = queue.Queue()
        with subscribers_lock:
            subscribers.append(client_queue)
        logger.info("SSE client connected (%d total)", len(subscribers))

        try:
            while True:
                payload = client_queue.get()
                self.wfile.write(f"data: {payload}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with subscribers_lock:
                subscribers.remove(client_queue)
            logger.info("SSE client disconnected (%d total)", len(subscribers))

    def log_message(self, format: str, *args: object) -> None:
        pass
