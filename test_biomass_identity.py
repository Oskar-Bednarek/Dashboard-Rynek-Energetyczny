from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from openpyxl import Workbook,load_workbook
from biomass_data import save_biomass_data,read_transactions,read_tenders,FIELDS
from biomass_identity import same_transaction,same_tender
from biomass_import import merge_responses
from test_biomass_import import answer,NOW,END


class BiomassIdentityTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'DataMaster.xlsx'
        workbook=Workbook();workbook.save(self.path);workbook.close()

    def variants(self):
        a=answer();b=deepcopy(a)
        a['settled'][0].update(buyer='MPEC Morąg sp. z o.o.',procedure_id='ZP.271.5.2026; 2026/BZP 00425890/01',date='2026-11-03',status='offer_selected')
        b['settled'][0].update(buyer='Miejskie Przedsiębiorstwo Energetyki Cieplnej w Morągu Spółka z ograniczoną odpowiedzialnością',procedure_id='ZP 271/5/2026',date='2026-11-04',tax_basis='net',price_method='source')
        b['settled'][0]['source_urls']=['https://another.example.org/wynik']
        a['ongoing'][0].update(entity='MPEC Morąg Sp. z o.o.',procedure_id='2026/BZP 00499999/01')
        b['ongoing'][0].update(entity='Miejskie Przedsiębiorstwo Energetyki Cieplnej w Morągu',procedure_id='2026-BZP-00499999')
        return a,b

    def merge(self,*payloads,known=()):
        return merge_responses([json.dumps(p) for p in payloads],END,known,now=NOW)

    def test_aliases_references_and_event_dates_merge_with_provenance(self):
        a,b=self.variants();result=self.merge(a,b)
        self.assertTrue(result.is_valid,result.errors)
        self.assertEqual((len(result.records),len(result.tenders)),(1,1))
        self.assertEqual(result.records[0]['date'],'2026-11-03')
        self.assertEqual(result.records[0]['price_basis'],'net')
        self.assertEqual(result.records[0]['price_method'],'source')
        self.assertEqual(result.records[0]['transaction_status'],'contract_signed')
        self.assertEqual(len(json.loads(result.records[0]['source_urls'])),2)
        self.assertTrue(any('Połączono' in warning for warning in result.warnings))

    def test_reimport_aliases_matches_workbook_and_tender_history(self):
        a,b=self.variants();first=self.merge(a)
        save_biomass_data(self.path,first.records,first.tenders)
        second=self.merge(b,known=read_tenders(self.path))
        added,_=save_biomass_data(self.path,second.records,second.tenders)
        self.assertEqual(added,0)
        self.assertEqual(len(read_transactions(self.path)),1)
        self.assertEqual(len(read_tenders(self.path)),1)
        self.assertEqual(read_transactions(self.path)[0]['price_basis'],'net')

    def test_tracking_links_do_not_create_another_record_without_reference(self):
        a=answer();b=deepcopy(a)
        a['settled'][0].update(procedure_id=None,source_urls=['https://www.example.org/wynik/?utm_source=chat'])
        b['settled'][0].update(procedure_id=None,source_urls=['http://example.org/wynik#section'])
        self.assertEqual(len(self.merge(a,b).records),1)

    def test_real_different_prices_tax_products_quantities_lots_and_amendments_remain_separate(self):
        base=answer();base['ongoing']=[]
        variants=[('unit_price',180),('tax_basis','net'),('product','Zrębka tartaczna'),('quantity',4800),('procedure_id','ZP.1.2026 część 2'),('status','price_amendment')]
        for field,value in variants:
            with self.subTest(field=field):
                a=deepcopy(base);b=deepcopy(base)
                if field=='tax_basis':a['settled'][0]['tax_basis']='gross'
                if field=='procedure_id':a['settled'][0]['procedure_id']='ZP.1.2026 część 1'
                if field=='status':b['settled'][0]['date']='2026-11-05'
                b['settled'][0][field]=value
                result=self.merge(a,b)
                self.assertTrue(result.is_valid,result.errors)
                self.assertEqual(len(result.records),2)

    def test_existing_duplicate_rows_are_hidden_without_deleting_raw_history(self):
        a,b=self.variants();first=self.merge(a).records[0];second=self.merge(b).records[0]
        save_biomass_data(self.path,[first],[])
        workbook=load_workbook(self.path)
        workbook['ZREBKI'].append([('old-second-id' if field=='record_id' else second.get(field)) for field in FIELDS])
        workbook.save(self.path);workbook.close()
        self.assertEqual(len(read_transactions(self.path)),1)
        workbook=load_workbook(self.path);self.assertEqual(workbook['ZREBKI'].max_row,3);workbook.close()

    def test_separate_buyers_with_same_local_reference_do_not_merge(self):
        a=answer();b=deepcopy(a);b['settled'][0]['buyer']='Inny PEC'
        b['ongoing'][0]['entity']='Inny zamawiający'
        result=self.merge(a,b)
        self.assertEqual((len(result.records),len(result.tenders)),(2,2))

    def test_two_products_in_same_ongoing_procurement_remain_separate(self):
        a=answer();b=deepcopy(a);b['ongoing'][0]['product']='Zrębka leśna'
        result=self.merge(a,b)
        self.assertEqual(len(result.tenders),2)
