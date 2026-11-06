"""Shared checks for workbook records and imported market values."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import math
import re
from contract_selection import build_contract_set

RDN_INSTRUMENTS = {'tge_gas_da':'TGEgasDA', 'tge_power_da_base':'TGeBase',
                   'tge_power_da_peak':'TGePeak', 'tge_power_da_offpeak':'TGeOffpeak', 'tge_power_da_24':'TGe24'}
INVESTING_INSTRUMENTS = {'coal':('coal_rotterdam_futures','Rotterdam Coal Futures'),
                         'emissions':('eua_year_futures','European Union Allowance (EUA) Year Futures')}


def number(value, *, volume=False, percent=False):
    if value is None or isinstance(value, bool):
        raise ValueError('Brak poprawnej liczby.')
    if isinstance(value, (int, float, Decimal)):
        try:
            result = Decimal(str(value))
            if not result.is_finite() or not math.isfinite(float(result)) or (volume and result < 0):
                raise ValueError('Nieprawidłowa liczba lub ujemny wolumen.')
            return result
        except (InvalidOperation, OverflowError) as error:
            raise ValueError('Nieprawidłowa liczba.') from error
    text = str(value).strip().replace(' ', '').replace('\xa0','')
    multiplier = 1
    if volume and text.lower().endswith(('k','m')):
        multiplier = 1000 if text[-1].lower()=='k' else 1000000
        text = text[:-1]
    if percent and text.endswith('%'):
        text = text[:-1]
    if not re.fullmatch(r'[+-]?\d+(?:[.,]\d+)*', text):
        raise ValueError('Nieprawidłowy format liczby.')
    if '.' in text and ',' in text:
        if re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+\.\d+',text):
            text=text.replace(',','')
        elif re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+,\d+',text):
            text=text.replace('.','').replace(',','.')
        else:
            raise ValueError('Nieprawidłowe separatory liczby.')
    elif text.count(',')>1:
        if not re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+',text):
            raise ValueError('Nieprawidłowe separatory liczby.')
        text=text.replace(',','')
    else:
        text=text.replace(',','.')
    try:
        result=Decimal(text)*multiplier
        if not result.is_finite() or not math.isfinite(float(result)):
            raise ValueError('Liczba musi być skończona.')
    except (InvalidOperation, OverflowError) as error:
        raise ValueError('Nieprawidłowa liczba.') from error
    if volume and result<0:
        raise ValueError('Wolumen nie może być ujemny.')
    return result


def valid_values(record, price_field, optional_fields):
    try:
        number(record.get(price_field))
        for field in optional_fields:
            if record.get(field) is not None:
                number(record[field], volume=field in {'volume','volume_mwh'}, percent=field=='change_pct')
    except ValueError:
        return False
    return True


def contract_map(session_date, market):
    contracts=build_contract_set(session_date,gas=market=='gas')
    prefix='gas_base' if market=='gas' else 'power_base'
    return {f'{prefix}_{group}_{index}':name
            for group in ('week','month','quarter','year')
            for index,name in enumerate(getattr(contracts,group+'s'),1)}


def valid_tge_record(record, market, collection):
    try:
        raw=record.get('trading_date')
        day=raw.date() if isinstance(raw,datetime) else raw if isinstance(raw,date) else date.fromisoformat(str(raw)[:10])
        expected=contract_map(day,market) if collection=='futures' else {
            key:value for key,value in RDN_INSTRUMENTS.items() if (key=='tge_gas_da')==(market=='gas')}
        if record.get('data_id') not in expected or record.get('instrument')!=expected[record['data_id']]:
            return False
        price='dkr_pln_mwh' if collection=='futures' else 'price_pln_mwh'
        optional=('max_pln_mwh','volume_mwh') if collection=='futures' else ('volume_mwh','change_pct')
        return valid_values(record,price,optional)
    except (ValueError,TypeError):
        return False
