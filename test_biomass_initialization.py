from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
from openpyxl import Workbook,load_workbook
from openpyxl.styles import PatternFill
from biomass_data import (ensure_biomass_sheets,save_biomass_data,read_transactions,read_tenders,
                          SHEET,TENDER_SHEET,FIELDS,TENDER_FIELDS,LEGACY_FIELDS)
from biomass_import import merge_responses
from test_biomass_import import answer,NOW,END


class BiomassInitializationTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'DataMaster.xlsx'
        workbook=Workbook();workbook.active.title='ZREBKA';workbook.active.append(['old_header','preserved'])
        workbook.active.append(['old_data',42]);workbook.save(self.path);workbook.close()

    def test_missing_sheets_are_created_without_touching_original_sheet(self):
        ensure_biomass_sheets(self.path)
        workbook=load_workbook(self.path,read_only=True)
        self.assertEqual(tuple(c.value for c in workbook[SHEET][1]),FIELDS)
        self.assertEqual(tuple(c.value for c in workbook[TENDER_SHEET][1]),TENDER_FIELDS)
        self.assertEqual(workbook['ZREBKA']['B2'].value,42)
        workbook.close()
        before=self.path.read_bytes()
        ensure_biomass_sheets(self.path)
        self.assertEqual(before,self.path.read_bytes())

    def test_legacy_columns_are_upgraded_without_losing_records(self):
        workbook=load_workbook(self.path)
        sheet=workbook.create_sheet(SHEET);sheet.append(LEGACY_FIELDS);sheet.append(['old-id','2026-10-01'])
        workbook.save(self.path);workbook.close()
        ensure_biomass_sheets(self.path)
        workbook=load_workbook(self.path,read_only=True)
        self.assertEqual(workbook[SHEET]['A2'].value,'old-id')
        self.assertEqual(tuple(c.value for c in workbook[SHEET][1]),FIELDS)
        workbook.close()

    def test_invalid_sheet_does_not_allow_partial_initialization(self):
        workbook=load_workbook(self.path);workbook.create_sheet(TENDER_SHEET).append(['invalid'])
        workbook.save(self.path);workbook.close()
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):ensure_biomass_sheets(self.path)
        self.assertEqual(before,self.path.read_bytes())

    def test_formatted_empty_rows_do_not_push_import_below_row_1000(self):
        ensure_biomass_sheets(self.path)
        workbook=load_workbook(self.path)
        for name in [SHEET,TENDER_SHEET]:
            workbook[name].cell(1000,1).fill=PatternFill('solid',fgColor='EEEEEE')
        workbook.save(self.path);workbook.close()
        report=merge_responses([json.dumps(answer())],END,now=NOW)
        self.assertTrue(report.is_valid,report.errors)
        self.assertEqual(save_biomass_data(self.path,report.records,report.tenders),(1,1))
        workbook=load_workbook(self.path,read_only=True,data_only=True)
        self.assertIsNotNone(workbook[SHEET]['A2'].value)
        self.assertIsNotNone(workbook[TENDER_SHEET]['A2'].value)
        workbook.close()
        self.assertEqual(len(read_transactions(self.path)),1)
        self.assertEqual(len(read_tenders(self.path)),1)
