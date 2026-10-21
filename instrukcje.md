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
- `date_stage.py` odczytuje arkusz i obsluguje wybor oraz potwierdzenie dat.
- `prompt_stage.py` przygotowuje prompt i obsluguje wklejona odpowiedz.
- Do weryfikacji trafiaja tylko dni robocze.
- Linki RDN obejmuja wszystkie dni robocze w zakresie, a linki OTF tylko
  daty zatwierdzone przez uzytkownika; daty w prompcie maja format DD-MM-YYYY.
- W pliku `prompt_template.txt` mozna wstawic znaczniki:
  `{{linki RDN GAZ}}`, `{{linki OTF GAZ}}`, `{{linki RDN ENERGIA}}`,
  `{{linki OTF ENERGIA}}`, `{{data dzisiejsza}}` oraz `{{ostatnia data}}`.
  Znaczniki dat sa zastepowane datami w formacie DD-MM-YYYY.