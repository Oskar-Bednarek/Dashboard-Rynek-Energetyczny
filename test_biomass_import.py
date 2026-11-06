from copy import deepcopy
from datetime import date,datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from openpyxl import Workbook,load_workbook
from biomass_data import (save_biomass_data,read_transactions,read_tenders,PREVIOUS_FIELDS,
                          PREVIOUS_TENDER_FIELDS,save_transactions,validate_response)
from biomass_import import merge_responses,deadline_is_open,WARSAW
from test_biomass import valid_response

NOW=datetime(2026,11,6,12,tzinfo=WARSAW)
END=date(2026,11,5)


def answer():
    return {'settled':[{'date':'2026-11-04','buyer':'PEC Test','seller':'Dostawca','product':'Zrębka leśna',
        'quantity':4700,'quantity_unit':'mp','unit_price':172.2,'price_unit':'PLN/mp',
        'tax_basis':'unknown','price_method':'calculated_indicative','status':'contract_signed',
        'procedure_id':'ZP.1.2026','source_urls':['https://example.org/wynik']}],
        'ongoing':[{'entity':'PEC Nowy','product':'Zrębka tartaczna','quantity':3000,'quantity_unit':'mp',
        'offer_deadline':'2026-11-20','published_or_updated_date':'2026-11-03',
        'procedure_id':'ZP.2.2026','source_url':'https://example.org/przetarg'}]}


class BiomassImportTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'DataMaster.xlsx'
        workbook=Workbook();workbook.active['A1']='preserved';workbook.save(self.path);workbook.close()

    def merge(self,*payloads,known=()):
        return merge_responses([json.dumps(p) for p in payloads],END,known,now=NOW)

    def test_sources_and_units_are_preserved_when_deduplicating_answers(self):
        first=answer();second=deepcopy(first)
        second['settled'][0]['source_urls']=['https://other.example.org/wynik']
        second['ongoing'][0]['source_url']='https://other.example.org/przetarg'
        result=self.merge(first,second)
        self.assertTrue(result.is_valid,result.errors)
        self.assertEqual((len(result.records),len(result.tenders)),(1,1))
        self.assertEqual(result.records[0]['price_unit'],'PLN/mp')
        self.assertIsNone(result.records[0]['price_pln_t'])
        self.assertEqual(len(json.loads(result.records[0]['source_urls'])),2)
        self.assertEqual(save_biomass_data(self.path,result.records,result.tenders),(1,1))
        again=self.merge(second)
        self.assertEqual(save_biomass_data(self.path,again.records,again.tenders)[0],0)
        self.assertEqual(len(read_transactions(self.path)),1)
        self.assertEqual(read_transactions(self.path)[0]['quantity_unit'],'mp')
        self.assertEqual(read_tenders(self.path)[0]['quantity_unit'],'mp')
        workbook=load_workbook(self.path);self.assertEqual(workbook.active['A1'].value,'preserved');workbook.close()

    def test_expired_and_today_without_time_are_skipped_not_saved(self):
        for deadline in ['2026-11-05','2026-11-06','2026-11-06T11:59:00+01:00']:
            payload=answer();payload['ongoing'][0]['offer_deadline']=deadline
            result=self.merge(payload)
            self.assertTrue(result.is_valid,result.errors)
            self.assertEqual(result.tenders,[])
            self.assertTrue(result.warnings)
        self.assertTrue(deadline_is_open('2026-11-06T13:00:00+01:00',now=NOW))
        self.assertFalse(deadline_is_open('2026-11-06T10:00:00Z',now=NOW))

    def test_future_deadline_and_today_with_confirmed_time_are_accepted(self):
        payload=answer();payload['ongoing'][0]['offer_deadline']='2026-11-06T13:00:00+01:00'
        result=self.merge(payload)
        self.assertTrue(result.is_valid,result.errors)
        self.assertEqual(len(result.tenders),1)

    def test_bad_answer_blocks_batch_but_empty_extra_fields_are_ignored(self):
        result=merge_responses([json.dumps(answer()),'{bad',''],END,now=NOW)
        self.assertFalse(result.is_valid)
        self.assertIn('Odpowiedź 2',result.errors[0])
        self.assertTrue(merge_responses([json.dumps(answer()),''],END,now=NOW).is_valid)

    def test_ongoing_requires_all_four_values(self):
        for field in ['entity','product','quantity','quantity_unit','offer_deadline']:
            payload=answer();payload['ongoing'][0][field]=None
            self.assertFalse(self.merge(payload).is_valid,field)

    def test_invalid_price_or_units_and_future_events_are_rejected(self):
        for field,value in [('unit_price',0),('unit_price',True),('unit_price','100'),('price_unit','PLN'),
                             ('date','2026-11-06'),('quantity_unit','t'),('buyer','=FORMULA')]:
            payload=answer();payload['settled'][0][field]=value
            self.assertFalse(self.merge(payload).is_valid,(field,value))

    def test_gj_and_tonne_units_survive_without_conversion(self):
        for unit,quantity_unit in [('PLN/GJ','GJ'),('PLN/t','t'),('PLN/Mg','Mg')]:
            payload=answer();payload['settled'][0].update(price_unit=unit,quantity_unit=quantity_unit)
            result=self.merge(payload)
            self.assertTrue(result.is_valid,result.errors)
            self.assertEqual(result.records[0]['unit_price'],172.2)
            if unit=='PLN/GJ':self.assertIsNone(result.records[0]['price_pln_t'])

    def test_new_answer_does_not_duplicate_a_legacy_transaction(self):
        old=validate_response(json.dumps(valid_response()),date(2026,10,7),END)
        save_transactions(self.path,old.records)
        payload=answer();row=payload['settled'][0]
        row.update(date='2026-11-02',buyer='Odbiorca A',product='Zrębka energetyczna',quantity=None,
                   quantity_unit=None,unit_price=150,price_unit='PLN/t',tax_basis='net',price_method='source',procedure_id='123')
        result=self.merge(payload)
        self.assertEqual(save_biomass_data(self.path,result.records,[])[0],0)
        self.assertEqual(len(read_transactions(self.path)),1)

    def test_settled_result_closes_linked_ongoing_in_any_answer_order(self):
        payload=answer();payload['ongoing'][0].update(entity='PEC Test',procedure_id='ZP.1.2026',product=payload['settled'][0]['product'])
        for values in ([{'settled':payload['settled'],'ongoing':[]},{'settled':[],'ongoing':payload['ongoing']}],
                       [{'settled':[],'ongoing':payload['ongoing']},{'settled':payload['settled'],'ongoing':[]}]):
            result=self.merge(*values)
            self.assertTrue(result.is_valid,result.errors)
            self.assertEqual(result.tenders[0]['status'],'awarded')
        existing=self.merge({'settled':[],'ongoing':payload['ongoing']})
        save_biomass_data(self.path,[],existing.tenders)
        result=self.merge({'settled':payload['settled'],'ongoing':[]},known=read_tenders(self.path))
        save_biomass_data(self.path,result.records,result.tenders)
        self.assertEqual(read_tenders(self.path)[0]['status'],'awarded')

    def test_previous_sheet_headers_migrate_without_loss(self):
        workbook=load_workbook(self.path)
        workbook.create_sheet('ZREBKI').append(PREVIOUS_FIELDS)
        workbook.create_sheet('ZREBKI_PRZETARGI').append(PREVIOUS_TENDER_FIELDS)
        workbook.save(self.path);workbook.close()
        result=self.merge(answer())
        save_biomass_data(self.path,result.records,result.tenders)
        self.assertEqual(read_transactions(self.path)[0]['price_unit'],'PLN/mp')
        self.assertEqual(read_tenders(self.path)[0]['quantity'],3000)
