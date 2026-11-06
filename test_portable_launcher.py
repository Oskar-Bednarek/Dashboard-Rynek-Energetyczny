import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from app_paths import APP_DIR, workbook_path

_spec = importlib.util.spec_from_file_location('portable_launcher', Path(__file__).parent/'packaging'/'launcher.py')
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)


class PortableLauncherTests(unittest.TestCase):
    def test_first_start_seeds_external_excel_and_update_preserves_it(self):
        with TemporaryDirectory(prefix='Raport ł ') as directory:
            root=Path(directory);(root/'app').mkdir()
            seed=root/'app'/'DataMaster.start.xlsx';seed.write_bytes(b'initial workbook')
            workbook=launcher.initialize_data(root)
            self.assertEqual(workbook,root/'data'/'DataMaster.xlsx')
            self.assertEqual(workbook.read_bytes(),b'initial workbook')
            workbook.write_bytes(b'user history')
            seed.write_bytes(b'new release seed')
            self.assertEqual(launcher.initialize_data(root).read_bytes(),b'user history')
            self.assertTrue((root/'data'/'logs').is_dir())

    def test_missing_seed_does_not_create_an_empty_excel(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(FileNotFoundError):launcher.initialize_data(root)
            self.assertFalse((root/'data'/'DataMaster.xlsx').exists())

    def test_only_one_launcher_can_hold_the_instance_lock(self):
        with TemporaryDirectory() as directory:
            with launcher.single_instance(Path(directory)) as first:
                self.assertTrue(first)
                with launcher.single_instance(Path(directory)) as second:
                    self.assertFalse(second)
            with launcher.single_instance(Path(directory)) as reopened:
                self.assertTrue(reopened)

    def test_default_and_portable_paths(self):
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('ENERGY_REPORT_DATA_DIR',None)
            self.assertEqual(workbook_path(),APP_DIR/'DataMaster.xlsx')
            self.assertEqual(workbook_path(Path('/tmp/example')),Path('/tmp/example')/'DataMaster.xlsx')
        with TemporaryDirectory(prefix='dane ł ') as directory:
            with patch.dict(os.environ,{'ENERGY_REPORT_DATA_DIR':directory}):
                self.assertEqual(workbook_path(),Path(directory).resolve()/'DataMaster.xlsx')
