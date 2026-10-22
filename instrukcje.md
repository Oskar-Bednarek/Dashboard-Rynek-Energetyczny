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
  obsluguje zakres historii RDN oraz wybor ostatniej zamknietej sesji OTF.
- `contract_selection.py` wylicza nazwy kontraktow OTF z konfigurowalnych
  przesuniec tygodni, miesiecy, kwartalow i lat.
- `json_validator.py` parsuje odpowiedz, sprawdza schemat JSON 2.0 oraz
  porownuje rekordy z datami, kontraktami i zakresami biezacej sesji.
- `prompt_stage.py` przygotowuje prompt i obsluguje wklejona odpowiedz.
- RDN obejmuje wszystkie dni kalendarzowe od ostatniej zapisanej daty do
  wczoraj. OTF pobierany jest tylko dla ostatniej zamknietej sesji: aplikacja
  pomija weekendy i swieta wskazane przez uzytkownika.
- Jesli arkusz RDN jest pusty, pierwszy import obejmuje 30 zakonczonych dni
  kalendarzowych: od dzisiaj minus 30 dni do wczoraj wlacznie.
- Wegiel i EUA korzystaja z ruchomego okna 30 dni, od dzisiaj minus 29 dni
  do dzisiaj wlacznie.
- Aplikacja korzysta z `prompt_template.txt`. Szablon otrzymuje osobne listy
  linkow RDN, jedna date sesji OTF, wyliczone kontrakty gazu i energii oraz
  zakresy 30 dni dla wegla i EUA. Jest to rozbudowana wersja pierwotnego
  promptu, zachowujaca jego szczegolowe zasady pobierania i kontroli jakosci.
- Przycisk `Waliduj JSON` nie zapisuje danych do Excela. Poprawny obiekt oraz
  raport sekcji sa przechowywane tylko w biezacej sesji Streamlit.
