import socket
import threading
from typing import List, Optional

captured_emails: List[str] = []
_running = False


def run_sink(host: str = "127.0.0.1", port: int = 1025):
    global _running
    _running = True
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(10)
    server.settimeout(1.0)
    print(f"[SMTP Sink] Listening on {host}:{port}", flush=True)

    while _running:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue
        except Exception:
            break

        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

    server.close()
    print("[SMTP Sink] Stopped", flush=True)


def handle_client(conn: socket.socket):
    try:
        rfile = conn.makefile("rb")
        wfile = conn.makefile("wb")
        wfile.write(b"220 alert-buster-smtp-sink Service Ready\r\n")
        wfile.flush()
        in_data = False
        data_buffer = []

        while True:
            line = rfile.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="replace")

            if in_data:
                if line_str.rstrip("\r\n") == ".":
                    in_data = False
                    captured = "".join(data_buffer)
                    captured_emails.append(captured)
                    print(f"[SMTP Sink] Successfully received email ({len(captured)} bytes)", flush=True)
                    wfile.write(b"250 2.0.0 Ok: queued\r\n")
                    wfile.flush()
                else:
                    data_buffer.append(line_str)
            else:
                cmd = line_str[:4].upper()
                if cmd in ["HELO", "EHLO"]:
                    wfile.write(b"250-alert-buster-smtp-sink\r\n250 HELP\r\n")
                    wfile.flush()
                elif cmd == "MAIL":
                    wfile.write(b"250 2.1.0 Sender ok\r\n")
                    wfile.flush()
                elif cmd == "RCPT":
                    wfile.write(b"250 2.1.5 Recipient ok\r\n")
                    wfile.flush()
                elif cmd == "DATA":
                    in_data = True
                    data_buffer = []
                    wfile.write(b"354 Start mail input; end with <CRLF>.<CRLF>\r\n")
                    wfile.flush()
                elif cmd == "QUIT":
                    wfile.write(b"221 2.0.0 Bye\r\n")
                    wfile.flush()
                    break
                elif cmd in ["RSET", "NOOP"]:
                    wfile.write(b"250 2.0.0 Ok\r\n")
                    wfile.flush()
                else:
                    wfile.write(b"502 5.5.2 Command not implemented\r\n")
                    wfile.flush()
    except Exception as e:
        print(f"[SMTP Sink] Client handler error: {e}", flush=True)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_sink()
