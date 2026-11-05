"""User-facing guidance for an Excel file locked or otherwise inaccessible."""
WORKBOOK_ACCESS_MESSAGE = (
    "Nie można uzyskać dostępu do pliku DataMaster.xlsx. "
    "Jeśli plik jest otwarty w Excelu, zamknij go (również na innym komputerze), "
    "a następnie spróbuj ponownie. Jeśli problem nie ustąpi, sprawdź uprawnienia do pliku."
)


def show_workbook_access_error() -> None:
    import streamlit as st
    st.error(WORKBOOK_ACCESS_MESSAGE)
