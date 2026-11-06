## Najważniejsze komendy venv — Window
# Aktywuje środowisko w PowerShell
    & "$HOME\venvs\dashboard-engine\Scripts\Activate.ps1"
# Dezaktywuje środowisko
    deactivate
# Sprawdza wersję Pythona
    python --version
# Sprawdza wersję pip
    python -m pip --version
# Instaluje paczkę
    python -m pip install pandas
# Instaluje paczki z pliku
    python -m pip install -r requirements.txt
# Wyświetla zainstalowane paczki
    python -m pip list
# Zapisuje wersje paczek do pliku
    python -m pip freeze > requirements.txt
# Usuwa paczkę
    python -m pip uninstall pandas
# Aktualizuje pip
    python -m pip install --upgrade pip
# Pokazuje ścieżki do Pythona
    where.exe python

## Uruchomienie aplikacji Streamlit
# Instalacja zależności projektu
    python -m pip install -r requirements.txt
# Uruchomienie aplikacji
    streamlit run app.py

## Podzial aplikacji
- `app.py` inicjalizuje sesje i przełącza miedzy etapami.
- `date_stage.py` odczytuje osobno arkusze `GAZ_RDN` i `EE_RDN`, a nastepnie
  obsluguje zakres historii RDN oraz reczny wybor daty sesji OTF.
- `contract_selection.py` wylicza nazwy kontraktow OTF z konfigurowalnych
  przesuniec tygodni, miesiecy, kwartalow i lat.
- `json_validator.py` parsuje odpowiedz, sprawdza schemat JSON 1.0 oraz
  porownuje rekordy z wybrana data, kontraktami i zakresami.
- `prompt_stage.py` przygotowuje prompt i obsluguje wklejona odpowiedz.
- RDN sprawdza wyłącznie ostatnie 7 dni kalendarzowych do wybranej daty
  raportu i pobiera brakujące daty dla każdego rynku, również luki wewnątrz
  tego tygodnia. Starsze luki nie są pobierane. Wykresy pokazują wszystkie dostępne dane z 30 dni. Dla OTF ekran pokazuje piec ostatnich dat przypadajacych w dni
  powszednie. Uzytkownik
  recznie wybiera date; aplikacja przekazuje tylko ja do promptu i walidatora
  dla obu rynkow.
- Jesli arkusz RDN jest pusty, pierwszy import obejmuje 7 zakonczonych dni
  kalendarzowych do wczoraj wlacznie.
- Wegiel i EUA korzystaja z ruchomego okna 30 dni, od dzisiaj minus 29 dni
  do dzisiaj wlacznie.
- Aplikacja korzysta z `prompt_market_data.txt`. Szablon otrzymuje osobne listy
  linkow RDN, URL-e OTF i kontrakty dla recznie wybranej daty oraz zakresy
  30 dni dla wegla i EUA. Odpowiedz zawiera `otf_session_date`; walidator
  sprawdza, czy odpowiada wybranej dacie i czy rekordy OTF oraz ich linki
  wskazuja te sama date.
- Nowy, samodzielny dashboard HTML generuje `python generate_market_dashboard.py`.
  Skrypt odczytuje arkusze z `DataMaster.xlsx` i tworzy `market_dashboard.html`;
  raport mozna filtrowac data w przegladarce i drukowac w formacie A4.
  Dane i biblioteka Chart.js sa osadzone w HTML, wiec otwarcie raportu nie
  wymaga polaczenia z siecia. Kontrakty terminowe gazu i energii sa
  prezentowane w dwoch polowach tabeli z jednostkami w naglowkach.
- Przycisk `Sprawdz odpowiedz` kontroluje dane. Po poprawnej walidacji zapis
  następuje automatycznie; brakujące wartości uzupełnia się we wspólnym formularzu.
  TGeBase można uzupełnić dla wszystkich żądanych dat, pozostałe indeksy
  energii dla najnowszej żądanej daty. Zapis zachowuje ich historię.

## Kursy NBP i ceny PLN

Aplikacja przy inicjalizacji sesji oraz generator HTML automatycznie uzupełniają
arkusz `KURSY_NBP` w `DataMaster.xlsx`: EUR i USD z tabeli A, dla każdego dnia
kalendarzowego od najstarszego notowania do dzisiaj (Europe/Warsaw). Uzupełniane
są luki, a kurs na dzisiaj jest sprawdzany ponownie, jeśli używa poprzedniej publikacji.
W weekendy i święta stosowany jest ostatni kurs opublikowany nie później niż data
notowania. Arkusz przechowuje datę publikacji, numer tabeli i czas pobrania.

Wymagany jest dostęp HTTPS do `api.nbp.pl`; klucze API nie są potrzebne.
Zapytania obejmują maksymalnie 93 dni. Kompletny historyczny cache jest używany
ponownie. Błąd pobierania nie nadpisuje skoroszytu. Brakujące kursy użytkownik
uzupełnia na ekranie „Sprawdź dane”, w tym samym formularzu co pozostałe braki.
Dotyczy to również przypadku, gdy dane rynkowe są już kompletne. Kursy ręczne
mają oznaczenie `MANUAL` w kolumnie `table_number` i nie są nadpisywane przez API.
Raport można wygenerować przy awarii NBP, jeśli wszystkie wymagane kursy są zapisane.

Oryginalne ceny w `WEGIEL` (USD) i `EUA` (EUR) pozostają bez zmian. Przy generowaniu
HTML mnożone są pola price/open/high/low przez kurs z daty notowania. Wolumeny
pozostają bez zmian. Dane HTML zachowują ceny źródłowe oraz informację o kursie;
zmiany procentowe dashboard oblicza na podstawie cen już wyrażonych w PLN.
Gotowy raport można pobrać na ostatnim ekranie aplikacji.

## Eksport PDF

Ostatni ekran udostępnia HTML i PDF z tego samego dashboardu. Nazwa plików:
`raport energetyczny RRRR-MM-DD`, według daty wybranej w aplikacji.
PDF powstaje w Chromium przez Playwright, z drukowaniem A4 poziomo i osadzonymi
wykresami. Wymagana instalacja `python -m pip install -r requirements.txt` oraz
Chromium: dostępny systemowo `chromium`/`chromium-browser`/`google-chrome` albo
`python -m playwright install chromium` (na nowym Linuksie ewentualnie
`python -m playwright install --with-deps chromium`). Brak przeglądarki nie blokuje
pobrania HTML. Eksport nie pobiera zewnętrznych zasobów.

## Oddzielny ekran danych o zrębkach

Po danych energetycznych aplikacja otwiera ekran „Dane o zrębkach” z linkiem
https://chatgpt.com/ i instrukcją rozpoczęcia nowego czatu z wyszukiwaniem.
Można uruchomić prompt w kilku niezależnych rozmowach, co może poprawić wyniki.
Przycisk „Dodaj kolejne pole na odpowiedź” dodaje osobne pole JSON bez utraty
wcześniej wpisanego tekstu. Puste dodatkowe pola są ignorowane. Wszystkie odpowiedzi
są sprawdzane przed wspólnym zapisem; błąd wskazuje numer odpowiedzi i rekordu.

Szablon `prompt_biomass.txt` szuka po 5 najnowszych nowych wyników do tabel
`settled` i `ongoing`, cofając się od ostatniego miesiąca bez stałego limitu dat,
w maksymalnie 5 rundach. Data raportu ogranicza daty zdarzeń. Przykładowe źródła
w `prompt_biomass_sources.txt` są inspiracją, a nie jedynymi miejscami wyszukiwania.
Prompt otrzymuje wcześniejsze transakcje i zapisane otwarte postępowania, aby
unikać powtórek i szukać ich wyników. Starsze schematy biomass-data-1.0/2.0
pozostają obsługiwane przy wklejaniu.

Odpowiedź ma postać `{"settled": [...], "ongoing": [...]}`. Settled zachowuje
kupującego, sprzedawcę, datę, rodzaj, cenę i jednostkę, VAT, sposób ustalenia
ceny, ilość i jej jednostkę, status, numer postępowania i linki. Obsługiwane
jednostki to t/Mg, mp, m3 i GJ; dane nie są samoczynnie przeliczane na tony.
Cena źródłowa, wyliczona i orientacyjna są rozróżniane.

Wspólny import usuwa duplikaty pomiędzy odpowiedziami oraz sprawdza zapisane
wcześniej dane. Dodatkowe źródła tej samej transakcji są zachowywane. Arkusze
`ZREBKI` i `ZREBKI_PRZETARGI` są rozszerzane bez kasowania poprzednich danych.
Wynik rozstrzygnięcia powiązany numerem i podmiotem z zapisanym otwartym
postępowaniem aktualizuje jego status na rozstrzygnięty.

Terminy ofert są sprawdzane względem rzeczywistego czasu Europe/Warsaw, a nie
wyłącznie wybranej daty raportu. Wygasłe nabory są pomijane z komunikatem.
Termin przypadający dzisiaj wymaga potwierdzonej przyszłej godziny w ISO 8601;
sama data nie wystarcza do uznania naboru za otwarty. Brak wyniku postępowania
nie jest dowodem otwartego naboru. Upływ terminu nie zmienia archiwalnego statusu
na rozstrzygnięty — wyłącza jedynie wpis z aktualnej tabeli naborów.

Dashboard pokazuje osobne tabele po maksymalnie 5 rekordów. Tabela postępowań
w toku (łącznie z nagłówkiem) jest ukrywana, gdy nie ma aktualnych naborów.
Po ukryciu naborów tabela transakcji pokazuje do 8 rekordów (zamiast 5) i
rozciąga się na dostępną wysokość. Zachowuje puste wiersze, jeśli danych jest mniej. W postępowaniach w toku widoczne są tylko:
podmiot, rodzaj zrębki, planowana ilość z jednostką i termin ofert. W transakcjach
zachowane są jednostki cen i ilości oraz oznaczenia VAT i sposobu ustalenia ceny.
Przycisk „Model nie znalazł nowych danych ani zmian” pozwala przejść dalej bez
wklejania pustego JSON-u; wcześniejsze dane nie są usuwane.

## Kopie zapasowe DataMaster

Przed każdym zastąpieniem Excela aplikacja zachowuje jego poprzednią wersję
w katalogu `backups` obok skoroszytu. Po udanym zapisie pozostaje 30 najnowszych
kopii. Nieudany zapis nie usuwa wcześniejszych kopii i nie zastępuje oryginału.
W celu przywrócenia danych zamknij aplikację i Excel, zachowaj obecny plik
pod inną nazwą, a wybraną kopię skopiuj jako `DataMaster.xlsx`.
Aktualizacje kursów, danych rynkowych oraz zrębków korzystają ze wspólnej
blokady zapisu, także pomiędzy kartami aplikacji. Nie otwieraj Excela podczas zapisu.

## Sprawdzanie kompletności danych

Obecność daty lub identyfikatora nie wystarcza do uznania danych za gotowe.
RDN wymaga właściwego indeksu, nazwy i skończonej ceny. Energia wymaga także
indeksów Peak/Offpeak/24 dla najnowszej daty raportu. Cena może wynosić zero
lub być ujemna. OTF sprawdza wybraną sesję, zgodność nazwy kontraktu z jego
identyfikatorem oraz DKR; minima grup pozostają bez zmian. Węgiel i EUA
wymagają poprawnego instrumentu, ceny oraz daty w wybranym zakresie; nie
wymagamy 30 sesji. Wolumen, zmiana procentowa i pozostałe opcjonalne wartości
mogą być puste; podane wartości muszą być liczbami, a wolumen nie może być
ujemny. Niepoprawne rekordy TGE można zastąpić we wspólnym formularzu ręcznym.
Węgiel i EUA są dopisywane lub aktualizowane po dacie i identyfikatorze;
krótsza odpowiedź modelu nie usuwa starszych danych, a identyczne wpisy
zachowują dotychczasową datę pobrania.

Duplikaty zrębki są porównywane również po znormalizowanych nazwach podmiotów,
identyfikatorach BZP i numerach postępowań oraz linkach bez parametrów śledzących.
Skrót nazwy i pełna nazwa mogą wskazywać to samo postępowanie. Wybór oferty
i późniejsza umowa z tą samą ceną mogą zostać połączone; zachowywane są źródła,
wcześniejsza data ustalenia ceny oraz pełniejsze dane. Różne ceny, jednostki,
znane podstawy VAT, produkty, ilości i części zamówienia pozostają rozdzielone.
Aneksy z innymi datami również nie są łączone z pierwotną umową. Porównanie
działa pomiędzy odpowiedziami i przy zapisie; odczyt ukrywa także rozpoznane
powtórzenia już obecne w archiwum, bez usuwania jego surowych wierszy.

Na ekranie „Gotowe” sekcja „Aktualny plik danych — DataMaster.xlsx” pokazuje
pełną ścieżkę pliku używanego przez aplikację i pozwala pobrać jego aktualną
kopię. Transakcje zrębki są zapisywane w `ZREBKI`, przetargi w
`ZREBKI_PRZETARGI`. Dawny pusty arkusz `ZREBKA` jest zachowywany, ale nowe
importy go nie zapełniają. Aplikacja uruchomiona na serwerze aktualizuje plik
na serwerze, a nie wcześniej pobrany Excel na komputerze użytkownika.
