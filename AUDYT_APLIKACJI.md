# Audyt aplikacji — 4 listopada 2026

## Wynik

Aplikacja nie jest jeszcze gotowa do bezpiecznego, codziennego przygotowywania raportów. Zwykłe scenariusze działają, ale testy dodatkowych ścieżek wykazały problemy z aktualnością danych, zachowaniem stanu sesji oraz przejściem od zapisu do raportu. Najpilniejszy problem może prowadzić do usunięcia notowań z Excela.

Audyt obejmował kod Pythona, powiązanie z szablonem HTML, pełny istniejący zestaw testów oraz scenariusze Streamlit AppTest na tymczasowych kopiach skoroszytu. Ceny i dane użytkownika nie były zmieniane. W trakcie audytu nie poprawiano kodu aplikacji. Pobieranie danych o zrębkach pozostaje poza zakresem.

## Potwierdzone problemy

### 1. Pilne: zapis starej odpowiedzi po zmianie dat może usuwać nowsze dane

Miejsca: `date_stage.py:362`, `prompt_stage.py:385`, `excel_writer.py:111`.

Potwierdzenie nowych dat nie usuwa `validation_report`, `response` ani poprzedniego zweryfikowanego payloadu. Na stronie promptu istnieje drugi mechanizm zapisu, który ufa temu staremu raportowi. Użytkownik może więc zapisać odpowiedź z poprzedniego raportu do nowego zakresu. Zapis węgla i EUA najpierw usuwa bieżące okno historii.

Reprodukcja w AppTest: poprawna odpowiedź → zapis → powrót do dat → zatwierdzenie nowego zakresu → nadal aktywny przycisk zapisu starej odpowiedzi na ekranie promptu. Na kopii pliku zniknęły daty węgla: 23, 26, 27, 28, 29, 30 października i 2 listopada 2026.

Naprawa: unieważniać wszystkie wyniki walidacji po zmianie parametrów; ponownie walidować przed zapisem; pozostawić jeden mechanizm zapisu; powiązać odpowiedź z konkretną datą i zakresem.

### 2. Pilne: nowy cache NBP może trwale zachować nieaktualny kurs zastępczy

Miejsce: `exchange_rates.py:162`.

Kurs zastępczy jest odświeżany tylko wtedy, gdy jego data kalendarzowa jest dzisiejsza. Jeśli aplikacja pobierze kurs przed publikacją poniedziałkowej tabeli, zapisze piątkowy kurs dla poniedziałku. We wtorek ten poniedziałkowy wpis nie jest już traktowany jako luka.

Reprodukcja: synchronizacja 2 listopada przed publikacją → synchronizacja 3 listopada z odpowiedzią zawierającą obie publikacje. Dla 2 listopada nadal pozostała data kursu 30 października.

Naprawa: rozróżnić publikacje NBP i przyporządkowanie do dni kalendarzowych; przy pobieraniu nowszych publikacji przeliczać także wcześniejsze wpisy zastępcze. Ten problem dotyczy modułu dodanego w poprzednim etapie pracy.

### 3. Pilne: awaria NBP blokuje całą aplikację

Miejsce: `app.py:30`.

Synchronizacja kursów jest wykonywana przed udostępnieniem wyboru dat. Błąd sieci kończy inicjalizację przez `st.stop()`. Nie można nawet przygotować promptu ani uzupełnić danych rynkowych. Komunikat mówi o problemie z listą dat/promptem, mimo że przyczyną jest NBP.

Reprodukcja w AppTest: wymuszenie błędu NBP → komunikat błędu i zero kontrolek wyboru dat.

Naprawa: umożliwić pracę nad danymi rynkowymi podczas awarii; używać poprawnego cache; blokować wyłącznie raport wymagający brakujących kursów, z precyzyjną informacją o przyczynie.

### 4. Pilne: pobierany raport nie respektuje wybranej daty i sesji OTF

Miejsca: `ready_stage.py:61`, `generate_market_dashboard.py:98`, `market_dashboard_template.html` — ustawienie `dateInput.value=DATA.max_date` i wybór `sessionDate`.

Do generatora nie są przekazywane wybrana data raportu ani wybrana sesja OTF. HTML domyślnie otwiera najnowszą datę ze wszystkich zapisanych rekordów, a dla kontraktów wybiera najnowszą sesję dostępną do tej daty. Wybór starszego raportu w aplikacji nie staje się domyślnym wyborem pobranego raportu.

Naprawa: przekazać do generatora datę raportu i wybraną sesję; stosować je do inicjalizacji i filtrów HTML.

### 5. Istotne: wykrywanie luk RDN pomija dziury wewnątrz historii

Miejsca: `date_stage.py:157`, `date_stage.py:190`.

Lista dat jest budowana dopiero po najnowszej zapisanej dacie. Odejmowanie istniejących dat nie pomoże wykryć luki wcześniejszej od tego maksimum. Obecność dowolnego indeksu danego dnia jest ponadto traktowana jak obecność całego dnia energii.

Reprodukcja: zapisane 1 i 3 listopada, brak 2 listopada, raport do 3 listopada → brak dat do pobrania w obu rynkach.

Naprawa: porównywać pełne oczekiwane okno siedmiu dni z kluczami data + indeks i wymaganymi wartościami.

### 6. Istotne: komunikat „dane kompletne” nie gwarantuje kompletnych cen

Miejsca: `data_coverage.py:110`, `data_coverage.py:131`.

OTF sprawdza liczbę identyfikatorów, bez cen i nazw kontraktów. Dla węgla/EUA wystarcza dowolna jedna data w oknie. Nie jest sprawdzana rzeczywista kompletność historii ani dostępność cen.

Reprodukcja: wiersze zawierające wyłącznie wymagane daty i identyfikatory, bez wartości cen → `complete=True`.

Naprawa: kontrolować poprawność wymaganych rekordów i wartości. Jeśli pełna historia jest nieznana, komunikować „dostępne notowania”, a nie pełną kompletność.

### 7. Istotne: walidator dopuszcza wartości nienadające się do raportu

Miejsca: `json_validator.py:99`, `json_validator.py:422`.

Dla danych Investing sprawdzany jest typ string, ale nie jego zawartość. Wartość `price="garbage"` przechodzi walidację, a potem konwersja PLN kończy się błędem. Dla TGE nie są odrzucane nieskończoności i NaN; parser JSON Pythona także je dopuszcza. Poprawność typów nie wystarcza do bezpiecznego zapisu.

Reprodukcja: cena węgla `garbage` i cena gazu NaN zostały zaakceptowane jako poprawny payload.

Naprawa: wspólna walidacja skończonych liczb i obsługiwanych formatów tekstowych już przed zapisem; odrzucać niestandardowe stałe JSON.

### 8. Istotne dla użytkownika: po zapisaniu nowych danych nie ma pobrania dashboardu

Miejsca: `review_stage.py:295`, `ready_stage.py:66`.

Po zapisie ustawiane jest `data_saved`, ale strona pozostaje `review`. Pobranie HTML jest tylko na `ready`, do którego prowadzi ścieżka „dane były już kompletne”. Użytkownik kończący pobieranie nowych danych otrzymuje sukces, ale nie przycisk raportu.

Reprodukcja w AppTest: po zapisie `page='review'`, `data_saved=True`, liczba przycisków pobrania: 0.

Naprawa: po poprawnym zapisie prowadzić do ekranu raportu lub udostępnić bezpośredni przycisk przejścia.

### 9. Istotne: ręczne uzupełnianie pomija starsze braki TGeBase

Miejsce: `manual_completion.py:59`.

Dla energii lista dat jest redukowana do ostatniej dla wszystkich indeksów. Jest to właściwe dla dodatkowych indeksów, ale nie dla TGeBase, którego historia jest wymagana przez walidator.

Reprodukcja: brak TGeBase z 19 października przy zakresie 19–20 października nie pojawia się w formularzu uzupełniania.

Naprawa: pełny zakres dla TGeBase, tylko najnowszy dzień dla Peak/Offpeak/24.

### 10. Ograniczenie raportów historycznych i niezależny niezaliczony test

Miejsce: `excel_writer.py:97`; test `test_completion_and_writer.py:120`.

Zapis usuwa historyczne TGePeak/TGeOffpeak/TGe24, zachowując je tylko dla najnowszego TGeBase. Raport wybrany dla starszej daty nie odtworzy później tych indeksów. Istniejący test oczekuje zachowania rekordu z 21 października, ale plik zawiera już nowsze TGeBase — rekord jest usuwany i test kończy się `StopIteration`.

Naprawa: ustalić i ujednolicić zasady przechowywania historii oraz aktualne dane testowe. Wspieranie wyboru dawnych dat przemawia za zachowaniem historycznych indeksów.

## Stan rzeczywistego NBP i aktualnego HTML

Dostęp sieciowy do `api.nbp.pl` w bieżącym środowisku nadal nie jest aktywny. Domena jest zapisana w szkicu konfiguracji, ale polityka działającego środowiska nadal nie zawiera jej na liście dozwolonych domen.

W prawdziwym `DataMaster.xlsx` nie ma jeszcze arkusza `KURSY_NBP`. Istniejący `market_dashboard.html` pochodzi sprzed wdrożenia przeliczania: przykładowa ostatnia cena węgla to nadal źródłowe 142,50, mimo etykiety PLN/t, i brak metadanych FX. Nie należy traktować tego starego pliku jako przeliczonego raportu PLN. Po udostępnieniu NBP trzeba odtworzyć cache, naprawić problemy opisane wyżej i ponownie wygenerować raport.

## Co potwierdzono jako działające

- Pełny zestaw istniejących testów: 51 uruchomionych, 50 zaliczonych, 1 błąd opisany w punkcie 10.
- Start aplikacji, wybór dat i przejście do promptu działają przy dostępnych kursach testowych.
- Walidacja poprawnego payloadu i zapis Excela działają na kopii danych.
- Nowy moduł NBP przelicza pola cenowe, pozostawiając wolumeny i źródłowe ceny bez zmian; zapisuje pochodzenie kursu.
- Zapis NBP używa pliku tymczasowego i atomowej podmiany. Symulowana awaria pobierania nie zmieniła skoroszytu.
- Uzupełnianie rzeczywiście brakujących wpisów FX i ponowne użycie kompletnego cache historycznego przechodzą testy.
- Ekran `ready` potrafi przygotować pobranie HTML przy dostępnych kursach testowych.
- Układ HTML i eksport A4 były sprawdzane w Chromium podczas pracy nad dashboardem. Sam wygląd nie potwierdza poprawności danych.

## Sugerowana kolejność dalszych prac

1. Zablokować zapis starego payloadu i zabezpieczyć zachowanie historii.
2. Poprawić cache NBP i oddzielić błędy sieci od pracy nad danymi.
3. Powiązać datę raportu i sesję OTF z pobieranym HTML.
4. Naprawić wykrywanie luk, ocenę kompletności i walidację liczb.
5. Uporządkować drogę użytkownika po zapisie i ręczne uzupełnianie.
6. Uruchomić rzeczywistą synchronizację NBP po aktywowaniu dostępu; sprawdzić końcowy raport PLN.
