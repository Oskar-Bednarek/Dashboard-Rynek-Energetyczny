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
- RDN obejmuje brakujace dni kalendarzowe, maksymalnie z ostatnich 7 dni do
  wczoraj. Dla OTF ekran pokazuje piec ostatnich dat przypadajacych w dni
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
- Przycisk `Sprawdz odpowiedz` kontroluje wklejone dane, ale nie zapisuje ich
  do Excela. Zapis nastepuje dopiero po kontroli brakow i wybraniu przycisku
  zapisu na ekranie podgladu.
