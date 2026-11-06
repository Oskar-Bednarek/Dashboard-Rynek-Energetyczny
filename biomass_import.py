"""Validate and merge separate ChatGPT answers without losing source units."""
from datetime import date, datetime
import json
import re
from zoneinfo import ZoneInfo
from biomass_data import (BiomassValidation, _number, _text, _url, canonical_record_key, tender_key,
                          validate_response as validate_legacy)
from exchange_rates import as_date

WARSAW = ZoneInfo('Europe/Warsaw')
PRICE_UNITS = {'PLN/t':'t', 'PLN/Mg':'t', 'PLN/mp':'mp', 'PLN/m3':'m3', 'PLN/m³':'m3', 'PLN/GJ':'GJ'}
UNITS = {'t':'t','Mg':'t','mp':'mp','m3':'m3','m³':'m3','GJ':'GJ'}
STATUSES = {'offer_selected','contract_awarded','contract_signed','transaction_completed','price_amendment'}


def current_time():
    return datetime.now(WARSAW)


def deadline_is_open(value, *, now=None):
    """A date without a time cannot confirm a still-open deadline today."""
    if not value:
        return False
    now = (now or current_time()).astimezone(WARSAW)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value > now.date()
    text = str(value)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return date.fromisoformat(text) > now.date()
    deadline = datetime.fromisoformat(text.replace('Z','+00:00'))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=WARSAW)
    return deadline > now


def _date(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
        raise ValueError('Data musi mieć format YYYY-MM-DD')
    return date.fromisoformat(value)


def _quantity(raw):
    value = _number(raw.get('quantity'),optional=True)
    unit = raw.get('quantity_unit')
    if value is None:
        if unit is not None:
            raise ValueError('Jednostka ilości bez ilości')
        return None,None
    if unit not in UNITS:
        raise ValueError('Nieobsługiwana jednostka ilości')
    return value, UNITS[unit]


def _settled(raw, end, retrieved):
    if not isinstance(raw,dict):
        raise ValueError('Rekord musi być obiektem')
    day = _date(raw.get('date'))
    if day > end:
        raise ValueError('Data transakcji późniejsza niż data raportu')
    buyer,seller = _text(raw.get('buyer')),_text(raw.get('seller'))
    if not buyer and not seller:
        raise ValueError('Brak kupującego i sprzedającego')
    kind = _text(raw.get('product'),True)
    price = _number(raw.get('unit_price'))
    unit = raw.get('price_unit')
    if unit not in PRICE_UNITS:
        raise ValueError('Nieobsługiwana jednostka ceny; podaj PLN/t, PLN/mp, PLN/m3 lub PLN/GJ')
    price_unit = 'PLN/'+PRICE_UNITS[unit]
    quantity,quantity_unit = _quantity(raw)
    basis,method,status = raw.get('tax_basis'),raw.get('price_method'),raw.get('status')
    if basis not in {'net','gross','unknown'} or method not in {'source','calculated','calculated_indicative'} or status not in STATUSES:
        raise ValueError('Nieprawidłowa podstawa VAT, sposób ustalenia ceny lub status')
    if method != 'source' and (quantity is None or quantity_unit != PRICE_UNITS[unit]):
        raise ValueError('Cena wyliczona wymaga ilości zgodnej z jednostką ceny')
    urls = raw.get('source_urls')
    if not isinstance(urls,list) or not urls:
        raise ValueError('Brak listy źródeł')
    urls = list(dict.fromkeys(_url(value) for value in urls))
    reference = _text(raw.get('procedure_id'))
    row = dict(date=day.isoformat(),date_basis='transaction_date',record_type='transaction' if status=='transaction_completed' else 'tender_award',
        buyer=buyer,seller=seller,kind=kind,price_pln_t=price if price_unit=='PLN/t' else None,
        price_basis=basis,transport='unknown',volume_t=quantity if quantity_unit=='t' else None,
        source_name='Źródło',source_url=urls[0],reference=reference,evidence='',retrieved_at=retrieved,
        unit_price=price,price_unit=price_unit,quantity=quantity,quantity_unit=quantity_unit,
        price_method=method,transaction_status=status,source_urls=json.dumps(urls,ensure_ascii=False))
    row['tender_id'] = tender_key(dict(buyer=buyer,reference=reference,source_url=urls[0]))
    return row


def _ongoing(raw,end,retrieved,now):
    if not isinstance(raw,dict):
        raise ValueError('Rekord musi być obiektem')
    deadline = raw.get('offer_deadline')
    if not isinstance(deadline,str):
        raise ValueError('Brak terminu ofert')
    # Validate syntax even if already expired.
    deadline_day = as_date(deadline)
    is_open = deadline_is_open(deadline,now=now)
    published = _date(raw.get('published_or_updated_date'))
    if published > end or deadline_day < published:
        raise ValueError('Nieprawidłowe daty publikacji lub terminu ofert')
    quantity,unit = _quantity(raw)
    if quantity is None:
        raise ValueError('Brak wymaganej ilości')
    row=dict(published_date=published.isoformat(),buyer=_text(raw.get('entity'),True),kind=_text(raw.get('product'),True),
        reference=_text(raw.get('procedure_id')),source_name='Źródło',source_url=_url(raw.get('source_url')),
        status='open',status_date=published.isoformat(),deadline=deadline_day.isoformat(),
        volume_t=quantity if unit=='t' else None,quantity=quantity,quantity_unit=unit,
        deadline_at=deadline, evidence='',checked_as_of=end.isoformat(),retrieved_at=retrieved)
    row['tender_id']=tender_key(row)
    return row,is_open


def merge_responses(texts,end,known_tenders=(),*,now=None):
    """Validate all pasted answers before any workbook write; deduplicate the batch."""
    now = now or current_time()
    result=BiomassValidation()
    records,tenders={},{}
    known={row['tender_id']:row for row in known_tenders}
    for response_index,text in enumerate(texts,1):
        if not text.strip():
            continue
        try:
            stripped=text.strip()
            if stripped.startswith('```') and stripped.endswith('```'):
                stripped=re.sub(r'^```(?:json)?\s*','',stripped,flags=re.I)[:-3].strip()
            payload=json.loads(stripped,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nieprawidłowa liczba JSON')))
            if not isinstance(payload,dict):
                raise ValueError('Odpowiedź musi być obiektem JSON')
            if 'schema_version' in payload:
                legacy=validate_legacy(stripped,date(2002,1,2),end,list(known.values()))
                result.errors.extend(f'Odpowiedź {response_index}: {error}' for error in legacy.errors)
                result.warnings.extend(legacy.warnings)
                incoming_records,incoming_tenders=legacy.records,legacy.tenders
            else:
                if set(payload) != {'settled','ongoing'} or not all(isinstance(payload[k],list) for k in ['settled','ongoing']):
                    raise ValueError('Wymagane są dwie listy: settled i ongoing')
                retrieved=now.isoformat()
                incoming_records,incoming_tenders=[],[]
                for index,raw in enumerate(payload['settled'],1):
                    try:
                        incoming_records.append(_settled(raw,end,retrieved))
                    except (ValueError,TypeError) as error:
                        result.errors.append(f'Odpowiedź {response_index}, settled {index}: {error}')
                for index,raw in enumerate(payload['ongoing'],1):
                    try:
                        row,is_open=_ongoing(raw,end,retrieved,now)
                        if is_open:
                            incoming_tenders.append(row)
                        else:
                            result.warnings.append(f'Pominięto {row["buyer"]}: termin ofert upłynął lub przypada dzisiaj bez potwierdzonej godziny.')
                    except (ValueError,TypeError) as error:
                        result.errors.append(f'Odpowiedź {response_index}, ongoing {index}: {error}')
            for row in incoming_records:
                key=canonical_record_key(row)
                if key in records:
                    if row.get('source_urls'):
                        old=records[key]
                        urls=json.loads(old.get('source_urls') or '[]')+json.loads(row['source_urls'])
                        provenance = {'calculated_indicative':0,'calculated':1,'source':2}
                        if provenance.get(row.get('price_method'),-1)>provenance.get(old.get('price_method'),-1):
                            old.update(price_method=row['price_method'])
                        old['source_urls']=json.dumps(list(dict.fromkeys(urls)),ensure_ascii=False)
                    continue
                records[key]=row
            for row in incoming_tenders:
                if row['status']=='open' and not deadline_is_open(row.get('deadline_at') or row.get('deadline'),now=now):
                    result.warnings.append(f'Pominięto nieaktualny nabór: {row["buyer"]}.')
                    continue
                key=row['tender_id']
                old=tenders.get(key)
                if old and old['status']!='open' and row['status']=='open':
                    continue
                if not old or row['status']!='open' or row.get('published_date','')>=old.get('published_date',''):
                    tenders[key]=row
        except (ValueError,TypeError,KeyError) as error:
            result.errors.append(f'Odpowiedź {response_index}: {error}')
    for row in records.values():
        tender_id=row.get('tender_id')
        if not tender_id:
            continue
        old=tenders.get(tender_id) or known.get(tender_id)
        if old and old['status']=='open':
            tenders[tender_id]=dict(old,status='awarded',status_date=row['date'],checked_as_of=end.isoformat(),retrieved_at=now.isoformat())
    result.records=list(records.values())
    result.tenders=list(tenders.values())
    return result
