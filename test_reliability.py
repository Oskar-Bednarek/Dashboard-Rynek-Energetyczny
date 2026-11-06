"""Regression coverage for missing history, manual FX and recoverable writes."""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import shutil
import unittest
from openpyxl import Workbook, load_workbook
from date_stage import load_date_plan
from exchange_rates import (ExchangeRateError, ensure_exchange_rates, missing_exchange_rates,
                            read_exchange_rates, save_manual_exchange_rates)
from manual_completion import find_missing_tge_records
from json_validator import validate_response
from test_json_validator import valid_payload, SOURCE_DATES, SESSION_DATE, WINDOW
import test_exchange_rates as fx_tests
from workbook_storage import atomic_save, serialized_update


class ReliabilityTests(unittest.TestCase):
    def test_rdn_only_requests_internal_gaps_within_last_seven_days(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'DataMaster.xlsx'
            workbook = Workbook()
            workbook.remove(workbook.active)
            for name, data_id in [('GAZ_RDN','tge_gas_da'), ('EE_RDN','tge_power_da_base')]:
                sheet = workbook.create_sheet(name)
                sheet.append(['trading_date','data_id','instrument','price_pln_mwh'])
                for offset in range(30):
                    day = date(2026,11,5)-timedelta(days=offset)
                    if offset < 7:
                        sheet.append([day, data_id, 'TGEgasDA' if name=='GAZ_RDN' else 'TGeBase', 100])
                    else:
                        sheet.append([day, 'tge_power_da_peak'])
                sheet.append([date(2026,10,6), data_id, 'TGEgasDA' if name=='GAZ_RDN' else 'TGeBase', 100])
                if name == 'EE_RDN':
                    for data_id, instrument in [('tge_power_da_peak','TGePeak'),('tge_power_da_offpeak','TGeOffpeak'),('tge_power_da_24','TGe24')]:
                        sheet.append([date(2026,11,5),data_id,instrument,100])
            workbook.save(path); workbook.close()
            plan = load_date_plan(path, date(2026,11,6))
            self.assertEqual(plan.rdn_dates['gas_rdn'], [])
            self.assertEqual(plan.rdn_dates['electricity_rdn'], [])
            # Earlier history is incomplete, but only recent internal holes matter.
            workbook = load_workbook(path)
            for name, data_id in [('GAZ_RDN','tge_gas_da'), ('EE_RDN','tge_power_da_base')]:
                sheet = workbook[name]
                for index in range(sheet.max_row,1,-1):
                    if str(sheet.cell(index,1).value)[:10] in {'2026-10-31','2026-11-03'} and sheet.cell(index,2).value == data_id:
                        sheet.delete_rows(index)
            workbook.save(path);workbook.close()
            plan=load_date_plan(path,date(2026,11,6))
            self.assertEqual(plan.rdn_dates['gas_rdn'], [date(2026,10,31),date(2026,11,3)])
            self.assertEqual(plan.rdn_dates['electricity_rdn'], [date(2026,10,31),date(2026,11,3)])

    def test_manual_completion_includes_all_historical_base_dates(self):
        payload = valid_payload()
        payload['data']['electricity']['day_ahead'] = []
        dates = [date(2026,10,20), date(2026,10,21)]
        missing = find_missing_tge_records(payload, {**SOURCE_DATES,'electricity_rdn':dates}, SESSION_DATE)
        self.assertEqual([r.trading_date for r in missing if r.data_id=='tge_power_da_base'], ['2026-10-20','2026-10-21'])
        self.assertTrue(all(r.trading_date=='2026-10-21' for r in missing if r.section=='electricity.day_ahead' and r.data_id!='tge_power_da_base'))

    def test_nonfinite_and_garbage_numbers_rejected_negative_prices_allowed(self):
        for value in [float('nan'),float('inf'), 'abc']:
            payload = valid_payload()
            payload['data']['gas']['day_ahead'][0]['values']['price_pln_mwh'] = value
            self.assertFalse(validate_response(json.dumps(payload), SOURCE_DATES, SESSION_DATE, WINDOW, WINDOW).is_valid)
        payload = valid_payload()
        payload['data']['electricity']['day_ahead'][0]['values']['price_pln_mwh'] = -10
        self.assertTrue(validate_response(json.dumps(payload), SOURCE_DATES, SESSION_DATE, WINDOW, WINDOW).is_valid)
        for value in ['NaN', 'Infinity', 'abc', '1e999']:
            payload['data']['coal']['futures'][0]['values']['price'] = value
            self.assertFalse(validate_response(json.dumps(payload), SOURCE_DATES, SESSION_DATE, WINDOW, WINDOW).is_valid)

    def test_backup_retention_and_failed_replace_preserve_original(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'DataMaster.xlsx'
            workbook = Workbook(); workbook.save(path)
            for value in range(32):
                workbook.active['A1'] = value
                atomic_save(workbook,path)
            backups = sorted((path.parent/'backups').glob('*.xlsx'))
            self.assertEqual(len(backups),30)
            before = path.read_bytes()
            with patch('workbook_storage.os.replace',side_effect=PermissionError('Excel open')):
                with self.assertRaises(PermissionError):
                    atomic_save(workbook,path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len(list((path.parent/'backups').glob('*.xlsx'))),31)
            workbook.close()

    def test_serialized_updates_preserve_both_threads(self):
        from concurrent.futures import ThreadPoolExecutor
        with TemporaryDirectory() as directory:
            path = Path(directory)/'DataMaster.xlsx'
            workbook = Workbook(); workbook.active['A1']=0;workbook.save(path);workbook.close()
            @serialized_update
            def increment(path):
                workbook = load_workbook(path)
                try:
                    workbook.active['A1'] = workbook.active['A1'].value+1
                    atomic_save(workbook,path)
                finally:
                    workbook.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(increment,[path]*4))
            workbook = load_workbook(path)
            self.assertEqual(workbook.active['A1'].value,4)
            workbook.close()


class ManualFxTests(unittest.TestCase):
    setUp = fx_tests.ExchangeRateTests.setUp
    rates = staticmethod(fx_tests.ExchangeRateTests.rates)
    def test_missing_rates_can_be_filled_manually_without_api(self):
        gaps = missing_exchange_rates(self.path,today=date(2026,10,30))
        self.assertEqual(gaps,[(date(2026,10,30),'EUR'),(date(2026,10,30),'USD')])
        before=self.path.read_bytes()
        for value in [None,0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ExchangeRateError):
                save_manual_exchange_rates(self.path,[(date(2026,10,30),'EUR',value)])
            self.assertEqual(before,self.path.read_bytes())
        save_manual_exchange_rates(self.path,[(day,code,4) for day,code in gaps])
        self.assertFalse(missing_exchange_rates(self.path,today=date(2026,10,30)))
        with patch('exchange_rates.fetch_rates',side_effect=ExchangeRateError('offline')) as fetch:
            rates=ensure_exchange_rates(self.path,today=date(2026,10,30))
        fetch.assert_not_called()
        self.assertEqual(rates[(date(2026,10,30),'EUR')]['table_number'],'MANUAL')

    def test_yesterdays_provisional_rate_is_repaired(self):
        def early(currency,start,end):
            return [row for row in self.rates(currency,start,end) if row['effectiveDate']<'2026-11-02']
        with patch('exchange_rates.fetch_rates',side_effect=early):
            ensure_exchange_rates(self.path,today=date(2026,11,2))
        with patch('exchange_rates.fetch_rates',side_effect=self.rates):
            result=ensure_exchange_rates(self.path,today=date(2026,11,3))
        self.assertEqual(result[(date(2026,11,2),'EUR')]['effective_date'],date(2026,11,2))
