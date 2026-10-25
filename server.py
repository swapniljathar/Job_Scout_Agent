import http.server
import socketserver
import os

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'job-hunt-dashboard.html')
FAVICON_FILE = os.path.join(BASE_DIR, 'favicon.svg')

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def _serve_file(self, file_path, content_type, is_cached=False, include_body=True):
        try:
            with open(file_path, 'rb') as file:
                content = file.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            if is_cached:
                self.send_header('Cache-Control', 'public, max-age=86400')
            else:
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            if include_body:
                self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
        except OSError as err:
            self.send_response(500)
            self.end_headers()
            if include_body:
                self.wfile.write(str(err).encode('utf-8'))

    def do_GET(self):
        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]
        if clean_path in ('/favicon.ico', '/favicon.svg'):
            self._serve_file(FAVICON_FILE, 'image/svg+xml', is_cached=True, include_body=True)
        else:
            self._serve_file(HTML_FILE, 'text/html; charset=utf-8', is_cached=False, include_body=True)

    def do_HEAD(self):
        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]
        if clean_path in ('/favicon.ico', '/favicon.svg'):
            self._serve_file(FAVICON_FILE, 'image/svg+xml', is_cached=True, include_body=False)
        else:
            self._serve_file(HTML_FILE, 'text/html; charset=utf-8', is_cached=False, include_body=False)

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Job Scout Agent is live at: http://localhost:{PORT}")
        httpd.serve_forever()
