"""Portal STUB: read step_events and show case progress. Placeholder HTTP server so the chart's Deployment starts."""
from http.server import BaseHTTPRequestHandler, HTTPServer


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"fraudagent portal stub")


if __name__ == "__main__":
    HTTPServer(("", 8080), H).serve_forever()
