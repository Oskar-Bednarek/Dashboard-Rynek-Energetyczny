"""Portable launcher: no global Python installation or administrator rights."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
STATE = DATA / 'running.json'
LOCAL_HTTP = build_opener(ProxyHandler({}))  # Health requests only reach loopback.


def initialize_data(root: Path) -> Path:
    directory = root / 'data'
    directory.mkdir(exist_ok=True)
    workbook = directory / 'DataMaster.xlsx'
    if not workbook.exists():
        # Exclusive creation also protects against a simultaneous first start.
        created = False
        try:
            with (root / 'app' / 'DataMaster.start.xlsx').open('rb') as source, workbook.open('xb') as target:
                created = True
                shutil.copyfileobj(source, target)
        except FileExistsError:
            if created:
                workbook.unlink(missing_ok=True)
                raise
        except BaseException:
            if created:
                workbook.unlink(missing_ok=True)
            raise
    (directory / 'logs').mkdir(exist_ok=True)
    return workbook


def healthy(port: int) -> bool:
    try:
        with LOCAL_HTTP.open(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
            return response.status == 200 and response.read().strip() == b'ok'
    except (OSError, ValueError):
        return False


@contextmanager
def single_instance(directory: Path):
    with (directory / 'launcher.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        acquired = False
        try:
            if os.name == 'nt':
                import msvcrt
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except BlockingIOError:
                    pass
            yield acquired
        finally:
            if acquired:
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)


def free_port() -> int:
    with socket.socket() as address:
        address.bind(('127.0.0.1', 0))
        return address.getsockname()[1]


def main(smoke_test=False) -> int:
    DATA.mkdir(exist_ok=True)
    with single_instance(DATA) as acquired:
        if not acquired:
            for _ in range(40):
                try:
                    port = int(json.loads(STATE.read_text(encoding='utf-8'))['port'])
                    if healthy(port):
                        if not smoke_test:
                            webbrowser.open(f'http://127.0.0.1:{port}')
                        return 0
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                time.sleep(.25)
            print('Aplikacja już się uruchamia. Poczekaj na otwarcie przeglądarki.')
            return 0
        initialize_data(ROOT)
        runtime = ROOT / 'runtime' / 'python.exe'
        if not runtime.is_file():
            raise FileNotFoundError('Brakuje runtime/python.exe. Rozpakuj całą paczkę ZIP.')
        environment = dict(os.environ, ENERGY_REPORT_DATA_DIR=str(DATA),
                           PLAYWRIGHT_BROWSERS_PATH=str(ROOT / 'runtime' / 'browsers'),
                           PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        port = free_port()
        url = f'http://127.0.0.1:{port}'
        command = [str(runtime), '-m', 'streamlit', 'run', str(ROOT / 'app' / 'app.py'),
                   '--server.address=127.0.0.1', f'--server.port={port}',
                   '--server.headless=true', '--server.fileWatcherType=none',
                   '--browser.gatherUsageStats=false']
        print('Uruchamiam Raport rynków energetycznych...')
        print('To okno pozostaw otwarte podczas pracy. Aby zakończyć, naciśnij Ctrl+C.')
        child = None
        try:
            with (DATA / 'logs' / 'app.log').open('a', encoding='utf-8') as log:
                child = subprocess.Popen(command, cwd=ROOT / 'app', env=environment,
                                         stdout=log, stderr=subprocess.STDOUT)
                STATE.write_text(json.dumps({'port':port, 'pid':os.getpid()}), encoding='utf-8')
                for _ in range(240):
                    if child.poll() is not None:
                        raise RuntimeError('Aplikacja zakończyła pracę podczas uruchamiania.')
                    if healthy(port):
                        break
                    time.sleep(.5)
                else:
                    raise RuntimeError('Przekroczono czas uruchamiania aplikacji.')
                if smoke_test:
                    print('SMOKE OK: serwer działa, dane są poza plikami aplikacji.')
                    return 0
                webbrowser.open(url)
                print(f'Aplikacja jest gotowa: {url}')
                return child.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            STATE.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main(smoke_test='--smoke-test' in sys.argv))
    except (OSError, RuntimeError) as error:
        print(f'Nie udało się uruchomić aplikacji: {error}')
        print('Szczegóły: data/logs/app.log. Sprawdź, czy rozpakowano całą paczkę.')
        raise SystemExit(1)
