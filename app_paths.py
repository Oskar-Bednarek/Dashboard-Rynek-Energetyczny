"""Keep writable user data outside the replaceable portable application files."""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def workbook_path(default_directory: Path = APP_DIR) -> Path:
    directory = os.environ.get('ENERGY_REPORT_DATA_DIR')
    return (Path(directory).expanduser().resolve() if directory else Path(default_directory)) / 'DataMaster.xlsx'
