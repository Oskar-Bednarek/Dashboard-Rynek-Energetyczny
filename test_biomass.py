from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook, load_workbook
from biomass_data import read_transactions, save_transactions, search_context, validate_response
from biomass_stage import build_biomass_prompt


def valid_response():
    return {"schema_version":"biomass-data-1.0","status":"success","retrieved_at":"2026-11-05T12:00:00+01:00",
            "data":{"biomass":{"transactions":[{
                "date":"2026-11-02","date_basis":"award_publication","record_type":"tender_award",
                "buyer":"Odbiorca A","kind":"Zrębka energetyczna","price_pln_t":150,
                "price_basis":"net","transport":"unknown","volume_t":None,
                "source_name":"Źródło","source_url":"https://example.org/wynik","reference":"123",
                "evidence":"Wynik przetargu: wybrano ofertę na zrębkę po 150 PLN/t netto."
            }]}},"errors":[]}


class BiomassTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'DataMaster.xlsx'
        w=Workbook();w.active.title='WEGIEL';w.active.append(['preserved',42]);w.save(self.path);w.close()
        self.start=date(2026,10,7);self.end=date(2026,11,5)

    def validate(self,payload):
        return validate_response(json.dumps(payload),self.start,self.end)

    def test_first_import_inclusive_context_and_duplicate_imports(self):
        prompt,start=build_biomass_prompt(self.path,self.end)
        self.assertEqual(start,self.start)
        self.assertNotIn('{{',prompt)
        report=self.validate(valid_response())
        self.assertTrue(report.is_valid,report.errors)
        self.assertEqual(save_transactions(self.path,report.records),1)
        self.assertEqual(save_transactions(self.path,report.records),0)
        other=dict(report.records[0],source_url='https://other.example.org/wynik')
        self.assertEqual(save_transactions(self.path,[other]),0)
        rows=read_transactions(self.path)
        start,existing=search_context(rows,self.end)
        self.assertEqual(start,date(2026,11,2));self.assertEqual(len(existing),1)
        prompt,_=build_biomass_prompt(self.path,self.end)
        self.assertIn('Odbiorca A',prompt)
        self.assertIn('2026-11-02',prompt)
        w=load_workbook(self.path);self.assertEqual(w['WEGIEL']['B1'].value,42);w.close()

    def test_reject_invalid_prices_dates_types_and_excel_formulas(self):
        for field,value in [('date','2026-11-06'),('record_type','offer'),('price_pln_t',-1),('price_pln_t',True),('price_pln_t','150 zł/t'),('source_url','javascript:alert(1)'),('buyer','=SUM(1,2)'),('price_basis','unknown-tax')]:
            with self.subTest(field=field,value=value):
                payload=valid_response();payload['data']['biomass']['transactions'][0][field]=value
                self.assertFalse(self.validate(payload).is_valid)
        self.assertFalse(validate_response('{"price": NaN}',self.start,self.end).is_valid)

    def test_valid_empty_response_and_error_response_distinct(self):
        payload=valid_response();payload['data']['biomass']['transactions']=[]
        self.assertTrue(self.validate(payload).is_valid)
        payload['status']='error'
        self.assertFalse(self.validate(payload).is_valid)
        payload['status']='partial';payload['errors']=[{'message':'Źródło niedostępne'}]
        self.assertFalse(self.validate(payload).is_valid)

    def test_historical_report_ignores_future_transactions(self):
        report=self.validate(valid_response());save_transactions(self.path,report.records)
        start,existing=search_context(read_transactions(self.path),date(2026,10,31))
        self.assertEqual(start,date(2026,10,2));self.assertEqual(existing,[])

    def test_invalid_batch_does_not_modify_workbook(self):
        original=self.path.read_bytes()
        payload=valid_response();payload['data']['biomass']['transactions'].append({'date':'bad'})
        report=self.validate(payload)
        self.assertFalse(report.is_valid)
        self.assertEqual(original,self.path.read_bytes())

    def test_partial_success_preserves_source_warnings(self):
        payload=valid_response();payload['status']='partial';payload['errors']=[{'message':'Jedno źródło niedostępne'}]
        report=self.validate(payload)
        self.assertTrue(report.is_valid,report.errors)
        self.assertEqual(report.warnings,['Jedno źródło niedostępne'])


if __name__=='__main__':unittest.main()
