"""Exercise the actual portable Python and Chromium in a clean Windows folder."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

source = Path(sys.argv[1]).resolve()
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from test_json_validator import valid_payload, SOURCE_DATES, SESSION_DATE, WINDOW

with TemporaryDirectory(prefix='Raport test ł ') as temporary:
    root = Path(temporary) / 'Aplikacja ze spacją'
    shutil.copytree(source, root)
    python = root / 'runtime' / 'python.exe'
    environment = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(root / 'runtime' / 'browsers'),
                       PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    subprocess.run([str(python), str(root / 'launcher.py'), '--smoke-test'],
                   check=True, timeout=150, env=environment, cwd=root)
    workbook = root / 'data' / 'DataMaster.xlsx'
    if not workbook.is_file():
        raise AssertionError('Missing external DataMaster')
    # User data must survive updates and repeated starts byte-for-byte.
    workbook.write_bytes(workbook.read_bytes() + b'USER-DATA-SENTINEL')
    before = hashlib.sha256(workbook.read_bytes()).hexdigest()
    subprocess.run([str(python), str(root / 'launcher.py'), '--smoke-test'],
                   check=True, timeout=150, env=environment, cwd=root)
    assert hashlib.sha256(workbook.read_bytes()).hexdigest() == before
    response = valid_payload()
    response['status'] = 'partial'
    (root/'response.json').write_text(json.dumps({
        'payload':response,
        'source_dates':{key:[day.isoformat() for day in days] for key,days in SOURCE_DATES.items()},
        'session':SESSION_DATE.isoformat(), 'window':[day.isoformat() for day in WINDOW]
    }),encoding='utf-8')
    # PDF and validation must use the portable runtime, not the build machine Python.
    code = '''
import streamlit, openpyxl, biomass_stage, biomass_import, app_paths
from pathlib import Path
from report_pdf import generate_report_pdf
from json_validator import validate_response
from biomass_data import ensure_biomass_sheets
ensure_biomass_sheets(Path('data/DataMaster.xlsx'))
workbook=openpyxl.load_workbook('data/DataMaster.xlsx',read_only=True)
assert {'ZREBKI','ZREBKI_PRZETARGI'}.issubset(workbook.sheetnames)
workbook.close()
from datetime import date
import json
fixture=json.loads(Path('response.json').read_text(encoding='utf-8'))
report=validate_response(json.dumps(fixture['payload']),
    {key:[date.fromisoformat(day) for day in days] for key,days in fixture['source_dates'].items()},
    date.fromisoformat(fixture['session']),tuple(map(date.fromisoformat,fixture['window'])),tuple(map(date.fromisoformat,fixture['window'])))
assert report.is_valid,report.issues
assert report.data['status']=='success'
html = '<html><head><style>@page {size:A4 landscape;margin:0}</style></head><body><div id="dashboard"><div class="market-card">Raport — test PDF</div></div></body></html>'
data = generate_report_pdf(html)
assert data.startswith(b'%PDF-')
Path('test.pdf').write_bytes(data)
'''
    subprocess.run([str(python), '-c', code], check=True, timeout=120,
                   env=environment, cwd=root)
    assert (root / 'test.pdf').stat().st_size > 1000
    assert not (source / 'data').exists(), 'Build artifact must not include smoke-test user data'
print('PASS: portable Windows Python, Streamlit, Chromium PDF, Unicode paths, preserved Excel')
