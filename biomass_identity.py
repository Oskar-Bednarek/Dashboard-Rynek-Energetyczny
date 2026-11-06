"""Conservative wood-chip identity matching across source and naming variants."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata
from urllib.parse import urlsplit, parse_qsl, urlencode


def text(value):
    value=str(value or '').casefold().replace('ł','l')
    return ''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))


def entity(value):
    value=text(value)
    for pattern,replacement in [
        (r'miejskie\s+przedsiebiorstwo\s+energetyki\s+cieplnej','mpec'),
        (r'przedsiebiorstwo\s+energetyki\s+cieplnej','pec'),
        (r'przedsiebiorstwo\s+gospodarki\s+komunalnej\s+i\s+mieszkaniowej','pgkim'),
        (r'zaklad\s+uslug\s+komunalnych','zuk'),
        (r'spolka\s+z\s+ograniczona\s+odpowiedzialnoscia',''),
        (r'\bsp\.?\s*z\.?\s*o\.?\s*o\.?','')]:
        value=re.sub(pattern,replacement,value)
    value=re.sub(r'\b(w|we)\b',' ',value)
    return re.sub(r'[^a-z0-9]','',value)


def references(row):
    raw=text(row.get('reference'))
    bzp={f'bzp:{year}:{int(number)}' for year,number in re.findall(r'(20\d{2})\W*bzp\W*(\d{6,})',raw)}
    bzp|={f'bzp:{year}:{int(number)}' for year,number in re.findall(r'bzp\W*(20\d{2})\W*(\d{6,})',raw)}
    raw=re.sub(r'(?:20\d{2}\W*bzp|bzp\W*20\d{2})\W*\d{6,}(?:/\d{2})?',' ',raw)
    raw=re.sub(r'(?:czesc|cz\.|lot)\s*[:.\-]?\s*\d+',' ',raw)
    parts=set()
    for segment in re.split(r'[;|\n]',raw):
        for match in re.findall(r'\b[a-z][a-z0-9]*(?:[. /_-]+[a-z0-9]+)*[. /_-]+20\d{2}\b',segment):
            parts.add('ref:'+re.sub(r'[^a-z0-9]','',match))
    return bzp|parts


def lot(row):
    match=re.search(r'(?:czesc|cz\.|lot)\s*[:.\-]?\s*(\d+)',text(row.get('reference')))
    return match[1] if match else None


def urls(row):
    values=[row.get('source_url')]
    try:
        extra=row.get('source_urls') or []
        values+=json.loads(extra) if isinstance(extra,str) else extra
    except (ValueError,TypeError):
        pass
    result=set()
    for value in values:
        if not isinstance(value,str):continue
        parsed=urlsplit(value)
        query=[(k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True)
               if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid'}]
        result.add((parsed.hostname or '').lower().removeprefix('www.')+parsed.path.rstrip('/')+'?'+urlencode(sorted(query)))
    return result


def amount(row,kind):
    fields=('unit_price','price_pln_t') if kind=='price' else ('quantity','volume_t')
    value=next((row.get(k) for k in fields if row.get(k) is not None),None)
    try:return Decimal(str(value)).normalize() if value is not None else None
    except InvalidOperation:return None


def product(row):
    raw=text(row.get('kind'))
    # Different products or lots in one proceeding must remain separate.
    category=next((name for name in ('lesn','tartac','wierz','sad') if name in raw),None)
    return category or re.sub(r'\b(zrebka|zrebki|drzewna|drzewne|energetyczna|energetyczne|opalowa)\b','',raw).strip()


def same_entity(a,b):
    left,right=entity(a),entity(b)
    return bool(left and right and (left==right or (min(len(left),len(right))>=8 and (left==right+'u' or right==left+'u'))))


def same_tender(a,b):
    if product(a) and product(b) and product(a)!=product(b):return False
    if lot(a) and lot(b) and lot(a)!=lot(b):return False
    ra,rb=references(a),references(b)
    shared=ra&rb
    shared_url=bool(urls(a)&urls(b))
    ea,eb=entity(a.get('buyer')),entity(b.get('buyer'))
    entities_match=same_entity(a.get("buyer"),b.get("buyer"))
    if shared:
        # A BZP identifier is global; internal numbers need a matching entity.
        return any(token.startswith('bzp:') for token in shared) or entities_match or (shared_url and (not ea or not eb))
    if shared_url and (entities_match or not ea or not eb):
        if ra and rb and all(token.startswith('ref:') for token in ra|rb):return False
        return True
    if ra and rb:return False
    if not entities_match or product(a)!=product(b):return False
    qa,qb=amount(a,'quantity'),amount(b,'quantity')
    return qa is not None and qa==qb and a.get('deadline')==b.get('deadline') and a.get('published_date')==b.get('published_date')


def same_transaction(a,b):
    pa,pb=amount(a,'price'),amount(b,'price')
    if pa is None or pa!=pb:return False
    if (a.get('price_unit') or 'PLN/t')!=(b.get('price_unit') or 'PLN/t'):return False
    ta,tb=a.get('price_basis','unknown'),b.get('price_basis','unknown')
    if ta!='unknown' and tb!='unknown' and ta!=tb:return False
    if product(a) and product(b) and product(a)!=product(b):return False
    if lot(a) and lot(b) and lot(a)!=lot(b):return False
    qa,qb=amount(a,'quantity'),amount(b,'quantity')
    if qa is not None and qb is not None and qa!=qb:return False
    ua=a.get('quantity_unit') or ('t' if a.get('volume_t') is not None else None)
    ub=b.get('quantity_unit') or ('t' if b.get('volume_t') is not None else None)
    if ua and ub and ua!=ub:return False
    da,db=str(a.get('date'))[:10],str(b.get('date'))[:10]
    sa,sb=a.get('transaction_status'),b.get('transaction_status')
    if da!=db:
        if sa in {'price_amendment','transaction_completed'} or sb in {'price_amendment','transaction_completed'}:return False
        if not same_tender(a,b) or not (references(a)&references(b)):return False
        try:
            if abs((date.fromisoformat(da)-date.fromisoformat(db)).days)>31:return False
        except ValueError:return False
    if same_tender(a,b):return True
    if references(a) and references(b):return False
    ea,eb=entity(a.get('buyer') or a.get('seller')),entity(b.get('buyer') or b.get('seller'))
    if not ea or ea!=eb:return False
    return da==db and product(a)==product(b) and qa is not None and qa==qb


def merge_transaction(a,b):
    row=deepcopy(a)
    for field,value in b.items():
        if row.get(field) in (None,'','unknown') and value not in (None,'','unknown'):
            row[field]=value
    row['date']=min(str(a['date'])[:10],str(b['date'])[:10])
    methods={'calculated_indicative':0,'calculated':1,'source':2}
    if methods.get(b.get('price_method'),-1)>methods.get(a.get('price_method'),-1):
        row['price_method']=b['price_method']
    statuses={'offer_selected':0,'contract_awarded':1,'contract_signed':2,'transaction_completed':3,'price_amendment':4}
    if statuses.get(b.get('transaction_status'),-1)>statuses.get(a.get('transaction_status'),-1):
        row['transaction_status']=b['transaction_status']
    links=[]
    for source in (a,b):
        if source.get('source_url'):links.append(source['source_url'])
        extra=source.get('source_urls') or []
        try:links+=json.loads(extra) if isinstance(extra,str) else extra
        except (ValueError,TypeError):pass
    row['source_urls']=json.dumps(list(dict.fromkeys(links)),ensure_ascii=False)
    return row


def deduplicate_transactions(rows):
    merged=[]
    for row in rows:
        index=next((i for i,old in enumerate(merged) if same_transaction(old,row)),None)
        if index is None:merged.append(row)
        else:merged[index]=merge_transaction(merged[index],row)
    return merged
