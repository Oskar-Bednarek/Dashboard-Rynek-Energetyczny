from copy import deepcopy
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from openpyxl import Workbook, load_workbook
from excel_writer import SHEET_SPECS, save_market_data
from test_json_validator import valid_payload, WINDOW


class HistoryMergeTests(unittest.TestCase):
    def test_partial_import_preserves_history_and_only_updates_changed_records(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'DataMaster.xlsx'
            workbook = Workbook();workbook.remove(workbook.active)
            for name,fields in SHEET_SPECS.values():
                workbook.create_sheet(name).append(['trading_date','data_id','source_url','instrument',*fields,'retrieved_at'])
            workbook.save(path);workbook.close()
            payload=valid_payload()
            for market in ['gas','electricity']:
                payload['data'][market]['day_ahead']=[]
                payload['data'][market]['futures']=[]
            for market in ['coal','emissions']:
                record=payload['data'][market]['futures'][0]
                record['trading_date']='2026-10-20';record['values']['price']='100'
                second=deepcopy(record);second['trading_date']='2026-10-21'
                payload['data'][market]['futures']=[record,second]
            save_market_data(path,payload,WINDOW,WINDOW)
            def snapshot():
                workbook=load_workbook(path,read_only=True)
                try:
                    return {name:{row[0]:row for row in workbook[name].iter_rows(min_row=2,values_only=True)} for name in ['WEGIEL','EUA']}
                finally:workbook.close()
            original=snapshot()
            for market in ['coal','emissions']:
                payload['data'][market]['futures']=payload['data'][market]['futures'][:1]
                payload['data'][market]['futures'][0]['values']['price']='100.00'
            payload['retrieved_at']='2026-10-23T12:00:00+02:00'
            before=path.read_bytes()
            save_market_data(path,payload,WINDOW,WINDOW)
            self.assertEqual(snapshot(),original)
            self.assertEqual(path.read_bytes(),before)
            for market in ['coal','emissions']:
                record=payload['data'][market]['futures'][0]
                record['values']['price']='101'
                new=deepcopy(record);new['trading_date']='2026-10-22'
                payload['data'][market]['futures'].append(new)
            save_market_data(path,payload,WINDOW,WINDOW)
            updated=snapshot()
            for name in ['WEGIEL','EUA']:
                self.assertEqual(updated[name]['2026-10-21'],original[name]['2026-10-21'])
                self.assertEqual(updated[name]['2026-10-20'][4],'101')
                self.assertEqual(updated[name]['2026-10-20'][-1],payload['retrieved_at'])
                self.assertIn('2026-10-22',updated[name])
