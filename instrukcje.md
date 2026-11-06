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
- RDN sprawdza 30 dni kalendarzowych do wybranej daty raportu i pobiera
  maksymalnie 7 najnowszych brakujących dat dla każdego rynku, również luki
  przed ostatnią zapisaną datą. Wykresy pokazują wszystkie dostępne dane z 30 dni. Dla OTF ekran pokazuje piec ostatnich dat przypadajacych w dni
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

Po kompletnych danych energetycznych (z pliku albo po zapisie odpowiedzi) aplikacja
przechodzi do jednego ekranu „Dane o zrębkach”. Użytkownik kopiuje osobny prompt,
wkleja odpowiedź JSON i sprawdza ją na tym samym ekranie. Poprawne rekordy są
zapisywane automatycznie w arkuszu `ZREBKI`, po czym dostępne są HTML i PDF.
Przycisk „Model nie znalazł nowych transakcji” pozwala zakończyć etap bez wklejania
pustej odpowiedzi. Dotychczasowe transakcje nie są wówczas usuwane.

Szablon: `prompt_biomass.txt`. Edytowalna lista przykładowych źródeł:
`prompt_biomass_sources.txt`, jeden adres lub nazwa na wiersz. Źródła są wskazówkami;
model ma przeszukiwać również inne źródła. Zakres obejmuje ostatnią rzeczywistą
datę zapisu do daty raportu włącznie. Rekordy z dnia początkowego są zawarte wyłącznie
w prompcie jako lista wykluczeń; aplikacja dodatkowo deduplikuje zapis. Przy pierwszym
wyszukiwaniu zakres obejmuje ostatnie 30 dni. Dane demonstracyjne nie są historią.

Schemat `biomass-data-2.0` zawiera `status`, `retrieved_at`,
`data.biomass.transactions`, `data.biomass.tenders` oraz `errors`. Obsługiwane są rzeczywiste transakcje,
wyniki przetargów i opublikowane otwarte przetargi; nie zwykłe oferty sprzedaży. Cena to PLN/t, z osobnym statusem
VAT i transportu. Brak nabywcy/wolumenu zapisuje się jako null. Zachowane są link,
nazwa źródła, dowód oraz typ daty (transakcja/publikacja wyniku). Walidacja sprawdza
strukturę i poprawność wartości, ale nie zastępuje oceny prawdziwości źródła.

Raport pokazuje do 9 najnowszych rzeczywistych rekordów do wybranej daty i puste
wiersze dla brakujących pozycji. Ceny netto/brutto są oznaczone; gwiazdka oznacza
nieznaną podstawę VAT. Puste źródło danych nie jest zastępowane przykładami.

## Monitorowanie otwartych przetargów zrębków

Prompt otrzymuje także wcześniej zapisane otwarte przetargi i polecenie ponownego
sprawdzenia każdego z nich, niezależnie od zakresu nowych transakcji. Aktualizacje
zwracają zachowane `tender_id`. Nowe przetargi mają null; ID nadaje aplikacja.
Źródła przykładowe są inspiracją; konkretne przykładowe postępowania są wykluczone
z importu, a ogólne listy postępowań mogą prowadzić do nowych wyników.

Arkusz `ZREBKI_PRZETARGI` przechowuje statusy open/awarded/cancelled/closed_without_result,
termin ofert, datę publikacji, datę potwierdzonego statusu, dzień raportu, dowód
oraz źródło. Kolejne dni sprawdzenia tworzą historię, zamiast nadpisywać stare statusy.
Sam upływ terminu nie jest dowodem zakończenia; nadal otwarty przetarg pozostaje do
sprawdzenia. Nowy termin i brak dostępu do źródła nie mogą skutkować wymyśleniem wyniku.

Transakcje i statusy zapisują się atomowo w jednym skoroszycie. Otwarte postępowanie
nie musi mieć ceny. Potwierdzony wynik z ceną trafia do `ZREBKI` z powiązaniem
`tender_id`; wynik bez znanej ceny pozostaje statusem przetargu. Starsze arkusze
transakcji bez kolumny tender_id są odczytywane i uzupełniane przy zapisie.
Aplikacja przyjmuje także dotychczasowy schemat 1.0 z samymi transakcjami.

Ostatni ekran pokazuje monitorowane przetargi osobno od cen. Dashboard wyświetla
otwarte/zakończone postępowania z opisem statusu i bez ceny, a wynik powiązany
z transakcją nie jest liczony drugi raz. Zachowany limit wynosi 9 najnowszych pozycji.
Przycisk braku wyników dotyczy braku nowych danych ORAZ braku zmian statusów;
aktualizacje należy wkleić nawet wtedy, gdy nie znaleziono nowych transakcji.

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
