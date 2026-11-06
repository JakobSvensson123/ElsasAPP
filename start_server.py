import http.server
import socket
import socketserver
import os
import shutil

PORT = 8080
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def build_deploy_folder():
    """Create a lightweight deploy_drop folder (without .cache_pdfs) ready for Netlify Drop / GitHub Pages."""
    deploy_dir = os.path.join(ROOT_DIR, "deploy_drop")
    os.makedirs(os.path.join(deploy_dir, "data"), exist_ok=True)
    for fname in ["index.html", "styles.css", "app.js", "manifest.json", "sw.js", "icon.svg", "icon-192.png", "icon-512.png"]:
        src = os.path.join(ROOT_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(deploy_dir, fname))
    js_data = os.path.join(ROOT_DIR, "data", "eped_skane_data.js")
    if os.path.exists(js_data):
        shutil.copy2(js_data, os.path.join(deploy_dir, "data", "eped_skane_data.js"))


if __name__ == "__main__":
    os.chdir(ROOT_DIR)
    build_deploy_folder()
    local_ip = get_local_ip()
    Handler = http.server.SimpleHTTPRequestHandler
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print("=" * 60)
        print("  ePed Region Skåne – Webbapp & Doskalkylator är igång!")
        print(f"  På datorn:          http://localhost:{PORT}")
        print(f"  På Elsas telefon:   http://{local_ip}:{PORT}  (på samma Wi-Fi)")
        print("=" * 60)
        httpd.serve_forever()
