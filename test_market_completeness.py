from copy import deepcopy
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from openpyxl import Workbook, load_workbook
from data_coverage import assess_coverage
from date_stage import load_date_plan
from excel_writer import SHEET_SPECS
from json_validator import validate_response
from manual_completion import find_missing_tge_records, apply_manual_records
from market_values import number
from test_json_validator import valid_payload, SOURCE_DATES, SESSION_DATE, WINDOW


class MarketCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'DataMaster.xlsx'
        workbook=Workbook();workbook.remove(workbook.active)
        payload=valid_payload()
        for section,(name,fields) in SHEET_SPECS.items():
            sheet=workbook.create_sheet(name)
            sheet.append(['trading_date','data_id','source_url','instrument',*fields,'retrieved_at'])
            market,collection=section.split('.')
            for record in payload['data'][market][collection]:
                sheet.append([record['trading_date'],record['data_id'],record['source_url'],record['instrument'],*[record['values'].get(field) for field in fields],payload['retrieved_at']])
        workbook.save(self.path);workbook.close()

    def coverage(self):
        return assess_coverage(self.path,{'gas_rdn':[],'electricity_rdn':[]},SESSION_DATE,WINDOW,WINDOW)

    def change(self,sheet,field,value,row=2):
        workbook=load_workbook(self.path)
        headers=[cell.value for cell in workbook[sheet][1]]
        workbook[sheet].cell(row,headers.index(field)+1).value=value
        workbook.save(self.path);workbook.close()

    def validate(self,payload):
        return validate_response(json.dumps(payload),SOURCE_DATES,SESSION_DATE,WINDOW,WINDOW)

    def test_valid_workbook_needs_no_30_history_records(self):
        self.assertTrue(self.coverage().complete)

    def test_otf_prices_and_matching_contract_names_are_required(self):
        for field,value in [('dkr_pln_mwh',None),('dkr_pln_mwh','garbage'),('instrument','BASE_M-01-99'),('volume_mwh',-1)]:
            with self.subTest(field=field,value=value):
                before=self.path.read_bytes()
                self.change('GAZ_OTF',field,value)
                self.assertFalse(self.coverage().section_complete['gas_otf'])
                self.path.write_bytes(before)

    def test_coal_and_eua_require_valid_prices_and_instruments(self):
        for name,key in [('WEGIEL','coal'),('EUA','emissions')]:
            for field,value in [('price',None),('price','NaN'),('instrument','incorrect'),('data_id','incorrect'),('volume','-1K')]:
                with self.subTest(sheet=name,field=field):
                    before=self.path.read_bytes();self.change(name,field,value)
                    self.assertFalse(self.coverage().section_complete[key]);self.path.write_bytes(before)

    def test_rdn_invalid_price_or_name_is_requested_again_zero_and_negative_are_valid(self):
        for field,value,valid in [('price_pln_mwh',None,False),('price_pln_mwh','garbage',False),('instrument','TGePeak',False),('volume_mwh',-1,False),('price_pln_mwh',0,True),('price_pln_mwh',-100,True)]:
            with self.subTest(field=field,value=value):
                before=self.path.read_bytes();self.change('EE_RDN',field,value)
                plan=load_date_plan(self.path,date(2026,10,21))
                self.assertEqual(date(2026,10,20) not in plan.rdn_dates['electricity_rdn'],valid)
                self.path.write_bytes(before)

    def test_optional_values_can_be_absent_but_prices_cannot(self):
        payload=valid_payload()
        for market,collections in payload['data'].items():
            for records in collections.values():
                for record in records:
                    record['values']={key:value for key,value in record['values'].items() if key in {'price','price_pln_mwh','dkr_pln_mwh'}}
        self.assertTrue(self.validate(payload).is_valid)
        for market,collection,field in [('gas','day_ahead','price_pln_mwh'),('gas','futures','dkr_pln_mwh'),('coal','futures','price')]:
            bad=deepcopy(payload);bad['data'][market][collection][0]['values'][field]=None
            self.assertFalse(self.validate(bad).is_valid)

    def test_negative_volumes_are_rejected_in_all_market_types(self):
        for market,collection,field,value in [('gas','day_ahead','volume_mwh',-1),('electricity','futures','volume_mwh',-1),('coal','futures','volume','-1.2K')]:
            payload=valid_payload();payload['data'][market][collection][0]['values'][field]=value
            self.assertFalse(self.validate(payload).is_valid)

    def test_manual_completion_replaces_invalid_rdn_and_otf_without_duplicates(self):
        payload=valid_payload()
        payload['data']['gas']['day_ahead'][0]['values']['price_pln_mwh']=None
        payload['data']['electricity']['futures'][0]['values']['dkr_pln_mwh']=None
        missing=find_missing_tge_records(payload,SOURCE_DATES,SESSION_DATE)
        self.assertEqual(len(missing),2)
        repaired=apply_manual_records(payload,[(record,{field:10 for field in record.value_fields}) for record in missing])
        self.assertTrue(self.validate(repaired).is_valid)
        self.assertEqual(len(repaired['data']['gas']['day_ahead']),1)
        self.assertEqual(len(repaired['data']['electricity']['futures']),len(payload['data']['electricity']['futures']))

    def test_source_formats_and_small_prices_are_supported(self):
        self.assertEqual(float(number('1,234.56')),1234.56)
        self.assertEqual(float(number('1.234,56')),1234.56)
        self.assertEqual(float(number('1.32K',volume=True)),1320)
        self.assertEqual(float(number(0.000001)),0.000001)
