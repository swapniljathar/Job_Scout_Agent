import http.server
import socketserver
import os

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, 'job-hunt-dashboard.html')
FAVICON_FILE = os.path.join(BASE_DIR, 'favicon.svg')

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]
        
        # Favicon route
        if clean_path in ('/favicon.ico', '/favicon.svg'):
            try:
                with open(FAVICON_FILE, 'rb') as f:
                    icon_data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Content-Length', str(len(icon_data)))
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                self.wfile.write(icon_data)
                return
            except Exception as e:
                self.send_response(404)
                self.end_headers()
                return

        # Default dashboard HTML route
        try:
            with open(HTML_FILE, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def do_HEAD(self):
        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]
        if clean_path in ('/favicon.ico', '/favicon.svg'):
            try:
                with open(FAVICON_FILE, 'rb') as f:
                    icon_data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'image/svg+xml')
                self.send_header('Content-Length', str(len(icon_data)))
                self.end_headers()
                return
            except Exception:
                self.send_response(404)
                self.end_headers()
                return

        try:
            with open(HTML_FILE, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
        except Exception:
            self.send_response(500)
            self.end_headers()

if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Job Scout Agent is live at: http://localhost:{PORT}")
        httpd.serve_forever()
