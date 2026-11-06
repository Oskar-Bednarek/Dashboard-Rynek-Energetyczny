from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from openpyxl import Workbook,load_workbook
from biomass_data import validate_response,save_biomass_data,read_tenders,read_transactions,save_transactions,LEGACY_FIELDS
from biomass_stage import build_biomass_prompt
from test_biomass import valid_response


def payload(status='open', tender_id=None):
    value=valid_response();value['schema_version']='biomass-data-2.0'
    value['data']['biomass']={'transactions':[],'tenders':[{
        'tender_id':tender_id,'published_date':'2026-10-01','buyer':'Odbiorca A','kind':'Zrębka energetyczna',
        'reference':'123','source_name':'BIP','source_url':'https://example.org/postepowanie',
        'status':status,'status_date':'2026-10-01' if status=='open' else '2026-11-03',
        'deadline':'2026-11-20','volume_t':None,'evidence':'Potwierdzenie statusu na stronie BIP',
    }]}
    return value


class TenderTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'DataMaster.xlsx'
        w=Workbook();w.active.title='WEGIEL';w.active.append(['preserved']);w.save(self.path);w.close()
        self.start=date(2026,10,7);self.end=date(2026,11,5)

    def validate(self,value,known=None):
        return validate_response(json.dumps(value),self.start,self.end,known)

    def test_open_tender_needs_no_price_and_goes_into_next_prompt(self):
        report=self.validate(payload());self.assertTrue(report.is_valid,report.errors)
        self.assertEqual(save_biomass_data(self.path,report.records,report.tenders),(0,1))
        self.assertEqual(read_transactions(self.path),[])
        known=read_tenders(self.path,self.end,open_only=True)
        self.assertEqual(len(known),1)
        prompt,_=build_biomass_prompt(self.path,self.end)
        self.assertIn(known[0]['tender_id'],prompt)
        self.assertIn('2026-11-20',prompt)
        self.assertNotIn('{{open_tenders}}',prompt)
        self.assertEqual(save_biomass_data(self.path,report.records,report.tenders),(0,0))

    def test_resolution_keeps_history_and_links_price(self):
        opened=self.validate(payload());save_biomass_data(self.path,[],opened.tenders)
        known=read_tenders(self.path,self.end,open_only=True);tid=known[0]['tender_id']
        value=payload('awarded',tid)
        value['data']['biomass']['tenders'][0]['source_url']='https://example.org/wynik'
        transaction=valid_response()['data']['biomass']['transactions'][0]
        transaction.update(date='2026-11-03',tender_id=tid)
        value['data']['biomass']['transactions']=[transaction]
        report=self.validate(value,known);self.assertTrue(report.is_valid,report.errors)
        # Resolve the following report day, retaining the original open snapshot.
        for tender in report.tenders:tender['checked_as_of']='2026-11-06'
        self.assertEqual(save_biomass_data(self.path,report.records,report.tenders),(1,1))
        self.assertEqual(read_tenders(self.path,date(2026,11,5))[0]['status'],'open')
        self.assertEqual(read_tenders(self.path,date(2026,11,6))[0]['status'],'awarded')
        self.assertEqual(read_tenders(self.path,date(2026,11,6),open_only=True),[])
        self.assertEqual(read_transactions(self.path)[0]['tender_id'],tid)

    def test_new_award_can_link_by_buyer_reference(self):
        value=payload('awarded')
        transaction=valid_response()['data']['biomass']['transactions'][0];transaction['date']='2026-11-03'
        value['data']['biomass']['transactions']=[transaction]
        report=self.validate(value);self.assertTrue(report.is_valid,report.errors)
        self.assertEqual(report.records[0]['tender_id'],report.tenders[0]['tender_id'])

    def test_reject_unknown_updates_future_results_and_open_tender_price(self):
        value=payload(tender_id='made-up');self.assertFalse(self.validate(value).is_valid)
        value=payload('awarded');value['data']['biomass']['tenders'][0]['status_date']='2026-11-06'
        self.assertFalse(self.validate(value).is_valid)
        opened=self.validate(payload());save_biomass_data(self.path,[],opened.tenders)
        known=read_tenders(self.path,self.end,open_only=True)
        value=payload(tender_id=known[0]['tender_id'])
        transaction=valid_response()['data']['biomass']['transactions'][0];transaction['tender_id']=known[0]['tender_id']
        value['data']['biomass']['transactions']=[transaction]
        self.assertFalse(self.validate(value,known).is_valid)

    def test_legacy_transaction_sheet_is_readable_and_migrated(self):
        w=load_workbook(self.path);sh=w.create_sheet('ZREBKI');sh.append(LEGACY_FIELDS);w.save(self.path);w.close()
        self.assertEqual(read_transactions(self.path),[])
        value=valid_response();report=self.validate(value);save_transactions(self.path,report.records)
        self.assertEqual(len(read_transactions(self.path)),1)
        w=load_workbook(self.path);self.assertEqual(w['ZREBKI'].cell(1,len(LEGACY_FIELDS)+1).value,'tender_id');w.close()

    def test_duplicate_tender_updates_are_rejected(self):
        value=payload();value["data"]["biomass"]["tenders"]*=2
        self.assertFalse(self.validate(value).is_valid)

    def test_stale_notice_does_not_reopen_resolved_tender(self):
        report=self.validate(payload("awarded"));save_biomass_data(self.path,[],report.tenders)
        reopened=self.validate(payload())
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):save_biomass_data(self.path,[],reopened.tenders)
        self.assertEqual(before,self.path.read_bytes())

    def test_atomic_save_rejects_broken_tender_sheet_without_saving_transaction(self):
        w=load_workbook(self.path);w.create_sheet('ZREBKI_PRZETARGI').append(['invalid']);w.save(self.path);w.close()
        before=self.path.read_bytes()
        report=self.validate(payload('awarded'))
        transaction=self.validate(valid_response()).records
        with self.assertRaises(ValueError):save_biomass_data(self.path,transaction,report.tenders)
        self.assertEqual(before,self.path.read_bytes())


if __name__=='__main__':unittest.main()
